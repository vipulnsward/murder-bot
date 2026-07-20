import cv2
import numpy as np

DEFAULT_SCALES = [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95,
                  1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4, 1.5]


def match_multiscale(img, tmpl, scales=DEFAULT_SCALES):
    """Best template match across scales. Returns (score, center, scale)."""
    if img is None or tmpl is None:
        return -1.0, None, None
    best = (-1.0, None, None)
    for s in scales:
        t = tmpl if s == 1.0 else cv2.resize(tmpl, None, fx=s, fy=s,
                                             interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        if t.shape[0] > img.shape[0] or t.shape[1] > img.shape[1]:
            continue
        r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx > best[0]:
            h, w = t.shape[:2]
            best = (float(mx), (loc[0] + w // 2, loc[1] + h // 2), s)
    return best


if __name__ == "__main__":
    import os
    import sys
    import time

    HERE = os.path.dirname(os.path.abspath(__file__))
    TDIR = os.path.join(HERE, "templates")

    def load(name):
        return cv2.imread(os.path.join(TDIR, name + ".png"))

    def single(img, tmpl):
        r = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        h, w = tmpl.shape[:2]
        return float(mx), (loc[0] + w // 2, loc[1] + h // 2)

    frames = sys.argv[1:] or ["_rl.png", "status_bar.png", "_cur.png"]
    tmpl = load("barracks_bldg")
    for f in frames:
        if not os.path.exists(f):
            print(f"(skip {f})"); continue
        img = cv2.imread(f)
        ss, sc = single(img, tmpl)
        t0 = time.perf_counter()
        ms, mc, msc = match_multiscale(img, tmpl)
        dt = (time.perf_counter() - t0) * 1000
        print(f"{f}: single={ss:.3f}@{sc}  multiscale={ms:.3f}@{mc} scale={msc}  ({dt:.0f}ms)")
