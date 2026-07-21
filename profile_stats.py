"""profile_stats — read-only player-state snapshots (kb/34).

Pure collectors turn injected field reads into a Snapshot. Live navigation and
screen grounding remain behind a loud [LIVE-CAPTURE] boundary, so this module
cannot tap a gem path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Optional


@dataclass
class Snapshot:
    """Optional values captured from the profile and related stat screens."""

    resources: Optional[dict] = None
    gems: Optional[int] = None
    gold: Optional[int] = None
    vip: Optional[int | dict] = None
    power: Optional[int | dict] = None
    monarch: Optional[dict] = None
    troops_by_tier: Optional[dict] = None
    research: Optional[dict] = None
    buffs: Optional[list | dict] = None
    ts: Optional[float] = None


def _not_wired(*_a, **_k):
    raise NotImplementedError(
        "[LIVE-CAPTURE] profile_stats perceive not wired — see kb/34."
    )


def _read(perceive, field):
    value = perceive.get(field) if isinstance(perceive, Mapping) else perceive(field)
    return value() if callable(value) else value


def collect_resources(perceive):
    return _read(perceive, "resources")


def collect_gems(perceive):
    return _read(perceive, "gems")


def collect_gold(perceive):
    return _read(perceive, "gold")


def collect_vip(perceive):
    return _read(perceive, "vip")


def collect_power(perceive):
    return _read(perceive, "power")


def collect_monarch(perceive):
    return _read(perceive, "monarch")


def collect_troops_by_tier(perceive):
    return _read(perceive, "troops_by_tier")


def collect_research(perceive):
    return _read(perceive, "research")


def collect_buffs(perceive):
    return _read(perceive, "buffs")


def collect_ts(perceive):
    return _read(perceive, "ts")


def collect(perceive=None) -> Snapshot:
    """Build a Snapshot from a mapping or callable that supplies field reads."""

    perceive = _not_wired if perceive is None else perceive
    return Snapshot(
        resources=collect_resources(perceive),
        gems=collect_gems(perceive),
        gold=collect_gold(perceive),
        vip=collect_vip(perceive),
        power=collect_power(perceive),
        monarch=collect_monarch(perceive),
        troops_by_tier=collect_troops_by_tier(perceive),
        research=collect_research(perceive),
        buffs=collect_buffs(perceive),
        ts=collect_ts(perceive),
    )


def make_task(perceive=None, store=None, clock=None, notify=None):
    """Return a read-only run(ctx) task with injectable perception and storage."""

    import time as _time

    perceive = _not_wired if perceive is None else perceive
    clock = _time.time if clock is None else clock

    def run(ctx):
        snapshot = replace(collect(perceive), ts=clock())
        if store is not None:
            store(snapshot) if callable(store) else store.append(snapshot)
        ctx.log("profile_stats: snapshot collected")
        if notify:
            notify("profile_stats: snapshot collected", "info")
        return snapshot

    return run


if __name__ == "__main__":
    ok = True
    NOW = 1_000_000.0
    canned = {
        "resources": lambda: {"food": 10, "lumber": 20, "stone": 30, "ore": 40},
        "gems": lambda: 500,
        "gold": lambda: 600,
        "vip": lambda: {"level": 12, "time_s": 3600},
        "power": lambda: 7_000_000,
        "monarch": lambda: {"name": "Tester", "level": 35, "alliance": "BOT"},
        "troops_by_tier": lambda: {"ground": {12: 1000}},
        "research": lambda: {"advancement": {"construction": 20}},
        "buffs": lambda: [{"name": "truce", "remaining_s": 1800}],
        "ts": lambda: NOW - 1,
    }

    snapshot = collect(canned)
    populated = (
        snapshot.resources["food"] == 10
        and snapshot.gems == 500
        and snapshot.monarch["name"] == "Tester"
        and snapshot.troops_by_tier["ground"][12] == 1000
        and snapshot.ts == NOW - 1
    )
    print(f"1 collect populated -> {populated}")
    ok &= populated

    raised = False
    try:
        collect()
    except NotImplementedError as error:
        raised = str(error) == (
            "[LIVE-CAPTURE] profile_stats perceive not wired — see kb/34."
        )
    print(f"2 unwired raises LIVE-CAPTURE = {raised}")
    ok &= raised

    stored = []

    class FakeCtx:
        def log(self, message):
            return None

    result = make_task(perceive=canned, store=stored, clock=lambda: NOW)(FakeCtx())
    task_stored = len(stored) == 1 and stored[0] is result and result.ts == NOW
    print(f"3 make_task stored snapshot -> {task_stored}")
    ok &= task_stored

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
