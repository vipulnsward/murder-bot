"""FastAPI server for the local Keep Console."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from keep.bridge import ControlBridge
from keep.config import KeepConfig, default_config, load_config, save_config


class ControlRequest(BaseModel):
    action: str
    confirm: bool = False


def create_app(bridge: ControlBridge | None = None) -> FastAPI:
    active = bridge or ControlBridge()
    app = FastAPI(title="Keep Console")
    app.state.bridge = active
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return active.snapshot()

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return active.last_config.model_dump(mode="json")

    @app.put("/api/config")
    def put_config(body: dict[str, Any]) -> Any:
        try:
            cfg = KeepConfig.model_validate(body)
        except ValidationError as error:
            details = [
                {key: item[key] for key in ("loc", "msg", "type")}
                for item in error.errors(include_url=False)
            ]
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "validation_error",
                        "message": str(error),
                        "details": details,
                    }
                },
            )
        active.request_config_reload(cfg)
        save_config(cfg, active.config_path)
        return {"config": cfg.model_dump(mode="json"), "version_id": None, "reload": "queued"}

    @app.get("/api/tasks")
    def tasks() -> dict[str, Any]:
        return {"tasks": active.task_list()}

    @app.post("/api/tasks/{name}/toggle")
    def toggle_task(name: str) -> dict[str, Any]:
        try:
            return active.toggle_task(name)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown task") from None

    @app.post("/api/tasks/{name}/run-now", status_code=202)
    def run_task(name: str) -> dict[str, str]:
        try:
            return active.run_task(name)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown task") from None
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/api/control")
    def control(body: ControlRequest) -> dict[str, Any]:
        action = body.action.replace("-", "_")
        if action == "reclaim_session" and not body.confirm:
            raise HTTPException(status_code=400, detail="confirmation required")
        handlers = {
            "start": active.start,
            "pause": active.pause,
            "resume": active.resume,
            "panic_stop": active.panic_stop,
            "reclaim_session": lambda: active.reclaim_session(body.confirm),
        }
        if action not in handlers:
            raise HTTPException(status_code=400, detail="unknown action")
        try:
            result = handlers[action]()
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        return {"engine": result["status"], "action": body.action}

    @app.get("/api/logs")
    def logs(since: str | None = None) -> dict[str, Any]:
        return active.get_logs(since)

    @app.get("/api/events")
    def events() -> dict[str, Any]:
        return {"events": list(active.events)}

    @app.websocket("/ws/status")
    async def ws_status(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json(active.snapshot())
        await asyncio.sleep(0)
        await websocket.close()

    dist = ROOT / "keep" / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/")
        def root() -> dict[str, str]:
            return {"message": "Keep Console frontend is not built"}

    return app


app = create_app()


def _self_test() -> bool:
    from fastapi.testclient import TestClient

    ok = True
    with TemporaryDirectory() as directory:
        config_path = Path(directory) / "config.yaml"
        save_config(default_config(), config_path)
        fake = ControlBridge(runner=lambda **kwargs: "stopped", config_path=config_path)
        with TestClient(create_app(fake)) as client:
            response = client.get("/api/status")
            case = response.status_code == 200 and "status" in response.json()
            print(f"GET /api/status: {'PASS' if case else 'FAIL'}")
            ok &= case

            response = client.get("/api/config")
            config = response.json()
            case = response.status_code == 200 and config["safety"]["gem_spend"] is False
            print(f"GET /api/config gem-lock: {'PASS' if case else 'FAIL'}")
            ok &= case

            invalid = {**config, "safety": {**config["safety"], "gem_spend": True}}
            response = client.put("/api/config", json=invalid)
            persisted = load_config(config_path).safety.gem_spend
            case = response.status_code in {400, 422} and persisted is False
            print(f"PUT /api/config gem_spend=true rejected/not persisted: {'PASS' if case else 'FAIL'} ({response.status_code})")
            ok &= case

            response = client.get("/api/tasks")
            listed = response.json().get("tasks", [])
            case = response.status_code == 200 and len(listed) == 8
            print(f"GET /api/tasks lists 8 tasks: {'PASS' if case else 'FAIL'}")
            ok &= case

            before = next(task for task in listed if task["name"] == "gather")["enabled"]
            response = client.post("/api/tasks/gather/toggle")
            case = response.status_code == 200 and response.json()["enabled"] is not before
            print(f"POST /api/tasks/gather/toggle flips enabled: {'PASS' if case else 'FAIL'}")
            ok &= case

            missing = client.post("/api/control", json={"action": "reclaim-session"})
            confirmed = client.post(
                "/api/control", json={"action": "reclaim-session", "confirm": True}
            )
            case = missing.status_code == 400 and confirmed.status_code == 200
            print(f"POST /api/control reclaim confirmation: {'PASS' if case else 'FAIL'} ({missing.status_code}/{confirmed.status_code})")
            ok &= case

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if os.environ.get("KEEP_SELFTEST") == "1":
        raise SystemExit(0 if _self_test() else 1)
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
