"""Continuous vision-DB mapping daemon — SEPARATE from the rally loop.

Maps the shared frame every ~45s so the vision DB explores + refreshes as the bot
plays. Deliberately its OWN process: if a map is slow or stalls it CANNOT hang the
rally loop (that mistake was made once and reverted). No extra adb capture, no taps,
no writes anywhere the rally loop touches (only vision.db)."""
import sys
import time

sys.path.insert(0, ".")

import game_mapper
import shared_capture

DEV = "127.0.0.1:5555"
INTERVAL = 45


def main():
    n = 0
    while True:
        n += 1
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            frame = shared_capture.grab(DEV)
            if frame is None:
                print(f"[{stamp}] map #{n}: no frame", flush=True)
            else:
                result = game_mapper.map_current(img=frame, log=None)
                sid = result.get("screen_id") if isinstance(result, dict) else "?"
                print(f"[{stamp}] map #{n}: {sid}", flush=True)
        except Exception as exc:  # noqa: BLE001 — a bad map must never kill the mapper
            print(f"[{stamp}] map #{n} ERROR: {exc!r}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
