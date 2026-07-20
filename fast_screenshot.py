import subprocess
import time

import cv2
import numpy as np

DEVICE = "127.0.0.1:5555"


def _adb_out(device, *args):
    return subprocess.run(
        ["adb", "-s", device, "exec-out", *args], capture_output=True
    ).stdout


def grab_png(device=DEVICE):
    raw = _adb_out(device, "screencap", "-p")
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def grab_raw(device=DEVICE):
    raw = _adb_out(device, "screencap")
    if len(raw) < 16:
        return None
    w = int.from_bytes(raw[0:4], "little")
    h = int.from_bytes(raw[4:8], "little")
    need = w * h * 4
    if w <= 0 or h <= 0 or len(raw) < need:
        return None
    px = np.frombuffer(raw[-need:], np.uint8).reshape(h, w, 4)
    return cv2.cvtColor(px, cv2.COLOR_RGBA2BGR)


def grab(device=DEVICE, method="raw"):
    if method == "raw":
        img = grab_raw(device)
        if img is not None:
            return img
    return grab_png(device)


def _bench(fn, device, n):
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        img = fn(device)
        ts.append(time.perf_counter() - t)
    ts.sort()
    return ts[len(ts) // 2], sum(ts) / len(ts), (None if img is None else img.shape)


if __name__ == "__main__":
    import sys

    dev = sys.argv[1] if len(sys.argv) > 1 else DEVICE
    n = 20
    # warm up
    grab_png(dev)
    grab_raw(dev)
    for name, fn in (("png (current)", grab_png), ("raw->numpy", grab_raw)):
        med, avg, shape = _bench(fn, dev, n)
        print(f"{name:16s} median={med*1000:6.1f}ms  avg={avg*1000:6.1f}ms  shape={shape}")

    a, b = grab_png(dev), grab_raw(dev)
    if a is not None and b is not None and a.shape == b.shape:
        diff = float(np.mean(cv2.absdiff(a, b)))
        print(f"pixel mean-abs-diff png vs raw = {diff:.3f} (0 = identical content)")
    else:
        print(f"shape mismatch: png={None if a is None else a.shape} raw={None if b is None else b.shape}")
