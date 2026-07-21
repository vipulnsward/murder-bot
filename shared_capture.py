"""Shared frame capture — read the JPEG the HLS stream's ffmpeg writes.

This lets the mapper consume the SAME single adb screenrecord that feeds the live
stream, instead of opening a SECOND adb capture (screencap) that would fight it.
One screenrecord -> ffmpeg -> {HLS for the browser, latest.jpg here}. Taps still go
over a separate adb-input channel, which never conflicts with capture.

grab(device) mirrors fast_screenshot.grab(device): returns a BGR numpy frame. If the
shared frame is missing or stale (stream not running), it falls back to adb screencap
so callers work whether or not the stream is up.
"""

import os
import time

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_PATH = os.path.join(HERE, "game_brain", "live", "latest.jpg")
STALE_S = 3.0


def stream_active(max_age_s=STALE_S):
    """True if the shared frame exists and was written within max_age_s seconds."""
    try:
        return os.path.isfile(FRAME_PATH) and (time.time() - os.path.getmtime(FRAME_PATH)) <= max_age_s
    except OSError:
        return False


def grab(device="127.0.0.1:5555", max_age_s=STALE_S, fallback=True):
    """Latest streamed frame (BGR ndarray). Falls back to adb screencap when the
    stream isn't producing frames. Returns None only if both are unavailable."""
    if stream_active(max_age_s):
        for _ in range(4):                 # retry a couple times on a torn/partial read
            img = cv2.imread(FRAME_PATH)
            if img is not None:
                return img
            time.sleep(0.05)
    if fallback:
        import fast_screenshot
        return fast_screenshot.grab(device)
    return None


def grab_wait(device="127.0.0.1:5555", timeout=6.0, poll=0.2):
    """Wait for a FRESH shared frame and return it — NEVER falls back to adb screencap
    (so it can't fight the stream's screenrecord). Tolerates the brief screenrecord
    175s-cycle gap. Returns None only if the stream stays down past `timeout`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if stream_active(1.5):
            img = cv2.imread(FRAME_PATH)
            if img is not None:
                return img
        time.sleep(poll)
    return None


if __name__ == "__main__":
    print("shared frame path:", FRAME_PATH)
    print("stream active:", stream_active())
    img = grab(fallback=True)
    print("grab ->", None if img is None else f"{img.shape} (source={'stream' if stream_active() else 'adb fallback'})")
