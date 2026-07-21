"""Run Keep Console locally with a LIVE emulator frame source.

Serves the full app (Dashboard/Tasks/Config/Generals/Knowledge/Live/...) on :8000
with the Live view streaming the real emulator via adb screencap -> JPEG. This is
the generic main dashboard (not the troop-only stream).

  python keep_live.py [--port 8000] [--jpeg-quality 70]
"""

import argparse
import sys

import cv2

sys.path.insert(0, "/Users/sward/work/scratch/evony-bot")
import fast_screenshot
from keep.bridge import ControlBridge
from keep.server import create_app

DEVICE = "127.0.0.1:5555"


def make_frame_source(device, quality):
    import shared_capture

    def frame():
        # Prefer the stream's shared JPEG (one capture, no adb conflict). Only fall
        # back to adb screencap when the stream is off.
        if shared_capture.stream_active(3):
            try:
                with open(shared_capture.FRAME_PATH, "rb") as fh:
                    data = fh.read()
                if data:
                    return data
            except OSError:
                pass
        img = fast_screenshot.grab(device)
        if img is None:
            return None
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None
    return frame


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--jpeg-quality", type=int, default=70)
    p.add_argument("--device", default=DEVICE)
    args = p.parse_args()

    bridge = ControlBridge(frame_source=make_frame_source(args.device, args.jpeg_quality))
    bridge.status = "running"
    bridge.screen = "live"
    app = create_app(bridge)

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
