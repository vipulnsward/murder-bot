"""Thread-safe lifecycle bridge between Keep Console and the orchestrator."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
import threading
import time
from typing import Any, Callable

import orchestrator

from keep.config import KeepConfig, load_config, save_config


class ControlBridge:
    def __init__(
        self,
        runner: Callable[..., Any] = orchestrator.run,
        config_path: str | Path = "config.yaml",
        log_limit: int = 5000,
    ) -> None:
        self.runner = runner
        self.config_path = Path(config_path)
        self.status = "idle"
        self.current_task: str | None = None
        self.macro_state = "active"
        self.counters: dict[str, int | float] = {}
        self.logs: deque[dict[str, Any]] = deque(maxlen=log_limit)
        self.events: list[dict[str, Any]] = []
        self.last_config = load_config(self.config_path)
        self.reload_pending = False
        self._reload: KeepConfig | None = None
        self._run_now: Queue[str] = Queue()
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None
        self._registry = orchestrator.default_tasks()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @property
    def uptime(self) -> float:
        return 0.0 if self._started_at is None else time.monotonic() - self._started_at

    def snapshot(self) -> dict[str, Any]:
        cfg = self.last_config
        return {
            "status": self.status,
            "engine": self.status,
            "current_task": self.current_task,
            "macro_state": self.macro_state,
            "uptime_s": round(self.uptime, 3),
            "counters": dict(self.counters),
            "reload_pending": self.reload_pending,
            "safety": {
                "gem_spend": cfg.safety.gem_spend,
                "disconnect_safe": cfg.safety.disconnect_policy == "stop_only",
                "humanized": cfg.safety.humanize_required,
                "macro_on": cfg.safety.macro_required,
            },
        }

    def _configured_tasks(self) -> list[Any]:
        tasks = []
        for task in self._registry:
            configured = getattr(self.last_config.tasks, task.name)
            task.enabled = configured.enabled
            task.interval = configured.interval
            task.priority = configured.priority
            tasks.append(task)
        return tasks

    def _run_engine(self) -> None:
        cfg = self.last_config
        account = next(
            account
            for account in cfg.fleet.accounts
            if account.name == cfg.fleet.active_account
        )
        try:
            result = self.runner(
                device=account.adb_serial,
                tasks=self._configured_tasks(),
                logger=self.log,
                llm_fallback=cfg.vision.llm_fallback,
                stuck_threshold=cfg.engine.stuck_threshold,
                idle_cap_s=cfg.engine.idle_cap_s,
                watchdog=cfg.engine.watchdog,
                should_stop=lambda: self._stop.is_set() or self._pause.is_set(),
            )
            if result == "disconnect":
                self.status = "disconnected"
                self.add_event("Account disconnected", "alert")
            elif self._pause.is_set():
                self.status = "paused"
            else:
                self.status = "stopped"
        except Exception as error:
            self.log(f"engine failed: {error}", "alert")
            self.add_event(str(error), "alert")
            self.status = "stopped"

    def start(self) -> dict[str, Any]:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("engine already running")
        self._stop.clear()
        self._pause.clear()
        self.status = "running"
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run_engine, daemon=True)
        self._thread.start()
        return self.snapshot()

    def pause(self) -> dict[str, Any]:
        self._pause.set()
        self.status = "paused"
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        if self.status != "paused":
            raise RuntimeError("engine is not paused")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.1)
        self._pause.clear()
        return self.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        self.status = "stopped"
        return self.snapshot()

    def panic_stop(self) -> dict[str, Any]:
        return self.stop()

    def reclaim_session(self, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise ValueError("confirmation required")
        self.add_event("Session reclaim confirmed", "warn")
        self.status = "stopped"
        return self.snapshot()

    def request_config_reload(self, cfg: KeepConfig | dict[str, Any]) -> KeepConfig:
        validated = KeepConfig.model_validate(
            cfg.model_dump(mode="json") if isinstance(cfg, KeepConfig) else cfg
        )
        with self._lock:
            self._reload = validated
            self.last_config = validated
            self.reload_pending = True
        return validated

    def take_config_reload(self) -> KeepConfig | None:
        with self._lock:
            cfg, self._reload = self._reload, None
            self.reload_pending = False
            return cfg

    def task_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": task.name,
                "enabled": getattr(self.last_config.tasks, task.name).enabled,
                "interval": getattr(self.last_config.tasks, task.name).interval,
                "priority": getattr(self.last_config.tasks, task.name).priority,
            }
            for task in self._registry
        ]

    def toggle_task(self, name: str) -> dict[str, Any]:
        if not hasattr(self.last_config.tasks, name):
            raise KeyError(name)
        data = self.last_config.model_dump(mode="json")
        data["tasks"][name]["enabled"] = not data["tasks"][name]["enabled"]
        cfg = self.request_config_reload(data)
        save_config(cfg, self.config_path)
        return {"name": name, "enabled": getattr(cfg.tasks, name).enabled, "reload": "queued"}

    def run_task(self, name: str) -> dict[str, str]:
        if not hasattr(self.last_config.tasks, name):
            raise KeyError(name)
        if self.status in {"paused", "stopped"}:
            raise RuntimeError(f"engine {self.status}")
        self._run_now.put(name)
        return {"name": name, "scheduled_for": "next_tick"}

    def log(self, msg: str, level: str = "info") -> None:
        cursor = f"{time.time():.6f}"
        self.logs.append(
            {"ts": self._now(), "level": level, "task": self.current_task, "msg": msg, "cursor": cursor}
        )

    def get_logs(self, since: str | None = None) -> dict[str, Any]:
        lines = list(self.logs)
        if since:
            lines = [line for line in lines if line["cursor"] > since]
        cursor = lines[-1]["cursor"] if lines else (since or "0")
        return {"lines": lines, "cursor": cursor}

    def add_event(self, msg: str, level: str = "info") -> None:
        self.events.append({"ts": self._now(), "level": level, "channel_sent": [], "msg": msg})

