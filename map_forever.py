import sys, time, urllib.request
sys.path.insert(0, "/Users/sward/work/scratch/evony-bot")
import live_map, nav, orchestrator, screen_fsm, shared_capture, vision_db
try:
    import notify
except Exception:
    notify = None

DEV = "127.0.0.1:5555"
DB = "/Users/sward/work/scratch/evony-bot/game_brain/vision.db"
ctx = orchestrator.Ctx(DEV, logger=lambda m: None)
ctx.screencap = lambda: shared_capture.grab_wait(DEV)
n = nav.Nav(ctx)

def note(msg, level="info"):
    print(f"[forever] {msg}", flush=True)
    if notify:
        try: notify.notify(f"live-map: {msg}", level)
        except Exception: pass

def ensure_stream():
    """Keep the ONE shared capture alive by restarting the HLS stream via the app API
    (NEVER a screencap). The mapper depends entirely on the stream's shared frame."""
    if shared_capture.stream_active(8):
        return True
    note("shared frame stale -> restarting HLS stream (one capture, no screencap)")
    try:
        urllib.request.urlopen("http://localhost:8000/api/stream/start", data=b"", timeout=25).read()
    except Exception as e:
        note(f"stream start err {e!r}", "warn")
    for _ in range(25):
        if shared_capture.stream_active(3):
            note("stream fresh again")
            return True
        time.sleep(1)
    return shared_capture.stream_active(3)

passes = 0
consec_disc = 0
note("continuous city mapping started (shared-frame, parallel with 60fps stream)")
while True:
    if not ensure_stream():
        note("stream will not come up — waiting 30s", "warn"); time.sleep(30); continue
    img = shared_capture.grab_wait(DEV, timeout=6)
    if img is not None and screen_fsm.is_disconnect(img):
        consec_disc += 1
        note(f"disconnected (streak {consec_disc}) — reclaiming (Restart, never Quit)", "warn")
        note(f"reclaim -> {n.reclaim(confirm=True)}")
        if consec_disc >= 3:
            note("repeated disconnects — pausing 5min (something keeps logging in)", "alert")
            time.sleep(300); consec_disc = 0
        time.sleep(8); continue
    consec_disc = 0
    passes += 1
    note(f"=== pass {passes} start (vision_db {vision_db.VisionDB(DB).stats()}) ===")
    try:
        live_map.main()
    except Exception as e:
        note(f"pass error: {e!r}", "warn")
    note(f"=== pass {passes} done (vision_db {vision_db.VisionDB(DB).stats()}) ===")
    time.sleep(4)
