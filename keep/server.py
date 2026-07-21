"""FastAPI server for the local Murder Bot."""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from keep.bridge import ControlBridge
from keep.config import KeepConfig, default_config, load_config, save_config
from keep.stream import HLSStreamManager


NO_SIGNAL_SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360"><rect width="640" height="360" fill="#0b0f14"/><text x="320" y="180" fill="#9aa6b6" font-family="system-ui,sans-serif" font-size="22" text-anchor="middle">No signal</text></svg>'''


class ControlRequest(BaseModel):
    action: str
    confirm: bool = False


def create_app(bridge: ControlBridge | None = None) -> FastAPI:
    active = bridge or ControlBridge()
    stream = HLSStreamManager()
    frame_source = active.frame_source

    def stream_owned_frame() -> None:
        return None

    app = FastAPI(title="Murder Bot")
    app.state.bridge = active
    app.state.stream = stream
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

    @app.get("/api/schedule")
    def schedule() -> list[dict[str, str]]:
        return active.schedule()

    @app.get("/api/safety")
    def safety() -> dict[str, Any]:
        return active.safety()

    def _kb():
        import game_kb
        return game_kb.GameKB(str(ROOT / "game_brain" / "game_kb.db"))

    @app.get("/api/generals")
    def generals(q: str | None = None, gtype: str | None = None, limit: int = 320) -> dict[str, Any]:
        db = _kb()
        rows = db.search(q)["generals"] if q else db.list_generals(gtype=gtype)
        if gtype:
            rows = [r for r in rows if r.get("gtype") == gtype]
        return {"generals": rows[:limit], "total": len(rows)}

    @app.get("/api/generals/{name}")
    def general_detail(name: str) -> dict[str, Any]:
        db = _kb()
        g = db.get_general(name)
        if not g:
            raise HTTPException(status_code=404, detail="general not found")
        g["ratings"] = db.ratings(general=name)
        return g

    @app.get("/api/generals-recommend")
    def generals_recommend(role: str, n: int = 5, gtype: str | None = None) -> dict[str, Any]:
        import general_advisor
        adv = general_advisor.GeneralAdvisor(str(ROOT / "game_brain" / "game_kb.db"))
        return {"role": role, "recommendations": adv.recommend(role, n=n, gtype=gtype)}

    @app.get("/api/guides")
    def guides(q: str | None = None, category: str | None = None, limit: int = 200) -> dict[str, Any]:
        db = _kb()
        rows = db.search(q)["guides"] if q else db.guides(category=category)
        return {"guides": rows[:limit], "total": len(rows)}

    @app.get("/api/kb")
    def kb_list() -> dict[str, Any]:
        return {"docs": sorted(p.name for p in (ROOT / "kb").glob("*.md"))}

    @app.get("/api/kb/{name}")
    def kb_doc(name: str) -> dict[str, Any]:
        p = ROOT / "kb" / name
        if "/" in name or ".." in name or p.suffix != ".md" or not p.is_file():
            raise HTTPException(status_code=404, detail="kb doc not found")
        return {"name": name, "markdown": p.read_text()}

    @app.get("/api/screen.mjpeg")
    def screen_mjpeg() -> StreamingResponse:
        async def frames():
            while True:
                frame = active.latest_frame()
                content_type = b"image/jpeg" if frame else b"image/svg+xml"
                payload = frame or NO_SIGNAL_SVG
                yield b"--frame\r\nContent-Type: " + content_type + b"\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload + b"\r\n"
                await asyncio.sleep(1 / 3 if frame else 1)

        return StreamingResponse(
            frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.post("/api/stream/start")
    def start_stream() -> dict[str, Any]:
        result = stream.start_hls()
        if result["owns_adb"]:
            active.frame_source = stream_owned_frame
        return result

    @app.post("/api/stream/stop")
    def stop_stream() -> dict[str, Any]:
        result = stream.stop_hls()
        active.frame_source = frame_source
        return result

    @app.get("/api/stream/status")
    def stream_status() -> dict[str, Any]:
        result = stream.status()
        if not result["owns_adb"] and active.frame_source is stream_owned_frame:
            active.frame_source = frame_source
        return result

    @app.get("/hls/stream.m3u8")
    def hls_playlist() -> FileResponse:
        path = stream.output_dir / "stream.m3u8"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="stream is not ready")
        return FileResponse(
            path,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/hls/{segment}.ts")
    def hls_segment(segment: str) -> FileResponse:
        path = stream.output_dir / f"{segment}.ts"
        if not path.is_file() or path.parent != stream.output_dir:
            raise HTTPException(status_code=404, detail="segment not found")
        return FileResponse(
            path,
            media_type="video/mp2t",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.on_event("shutdown")
    def stop_stream_on_shutdown() -> None:
        stream.close()
        active.frame_source = frame_source

    @app.websocket("/ws/status")
    async def ws_status(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json(active.snapshot())
        await asyncio.sleep(0)
        await websocket.close()

    @app.websocket("/ws/logs")
    async def ws_logs(websocket: WebSocket) -> None:
        await websocket.accept()
        cursor: str | None = None
        try:
            while True:
                batch = active.get_logs(cursor)
                for line in batch["lines"]:
                    await websocket.send_json(line)
                    cursor = line["cursor"]
                await asyncio.sleep(0.2)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.websocket("/ws/screen")
    async def ws_screen(websocket: WebSocket) -> None:
        await websocket.accept()
        mode = websocket.query_params.get("mode", "frame")
        seq = 0
        try:
            while True:
                frame = active.latest_frame()
                seq += 1
                if mode == "mjpeg":
                    await websocket.send_bytes(frame or NO_SIGNAL_SVG)
                else:
                    await websocket.send_json({
                        "seq": seq,
                        "ts": active._now(),
                        "jpg_b64": base64.b64encode(frame).decode() if frame else None,
                        "screen": active.screen,
                        "no_signal": frame is None,
                    })
                await asyncio.sleep(1 / 3 if frame else 1)
        except (WebSocketDisconnect, RuntimeError):
            return

    dist = ROOT / "keep" / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/")
        def root() -> dict[str, str]:
            return {"message": "Murder Bot frontend is not built"}

    return app


app = create_app()


def _self_test() -> bool:
    from fastapi.testclient import TestClient

    ok = True
    with TemporaryDirectory() as directory:
        config_path = Path(directory) / "config.yaml"
        save_config(default_config(), config_path)
        fake = ControlBridge(
            runner=lambda **kwargs: "stopped",
            config_path=config_path,
            clock=lambda: 1_774_051_200.0,
            frame_source=lambda: None,
        )
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

            response = client.get("/api/schedule")
            schedule = response.json()
            case = response.status_code == 200 and bool(schedule) and all(
                {"start", "end", "state"} <= segment.keys() for segment in schedule
            )
            print(f"GET /api/schedule returns segments: {'PASS' if case else 'FAIL'} ({len(schedule)})")
            ok &= case

            response = client.get("/api/safety")
            safety = response.json()
            case = (
                response.status_code == 200
                and safety.get("gem_spend") is False
                and safety.get("locked") is True
            )
            print(f"GET /api/safety gem-lock is locked: {'PASS' if case else 'FAIL'}")
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

            response = client.get("/api/generals?limit=5")
            gdata = response.json()
            case = response.status_code == 200 and "generals" in gdata and "total" in gdata
            print(f"GET /api/generals responds ({gdata.get('total')} total): {'PASS' if case else 'FAIL'}")
            ok &= case

            case = (client.get("/api/kb").status_code == 200
                    and client.get("/api/kb/..%2f..%2fetc%2fpasswd").status_code == 404)
            print(f"GET /api/kb + path-traversal blocked: {'PASS' if case else 'FAIL'}")
            ok &= case

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if os.environ.get("KEEP_SELFTEST") == "1":
        raise SystemExit(0 if _self_test() else 1)
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
