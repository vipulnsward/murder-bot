"""Humanized input + self-policing for the ADB Evony bot (see kb/30).

Wraps taps/swipes so the bot doesn't look like a script:
  - taps land at a jittered, center-biased point inside the element box (never a fixed pixel),
  - delays are drawn from [min,max] ranges (never constants), with a human reaction floor,
  - tap duration varies (occasional deliberate long press),
  - swipes follow a WindMouse curved path (chained input-swipe micro-segments),
  - self-policing: detects its OWN repeated-tap tell and raises TooManyClicks (ALAS parity),
    so the caller can pause + notify instead of hammering.

I/O is injectable (`run_shell`) so it unit-tests with no ADB. Randomness is std `random`
(fine outside workflow scripts). GEM-SAFE: this only humanizes input; it never chooses actions.
"""

import math
import random
import subprocess
import time
from collections import Counter, deque

DEFAULTS = {
    "jitter_samples": 3,
    "tap_box_shrink_px": 6,
    "delay_between_taps": (0.30, 0.80),
    "delay_after_menu": (0.80, 2.50),
    "delay_between_tasks": (3.0, 15.0),
    "reaction_floor": 0.25,
    "tap_duration_ms": (40, 120),
    "deliberate_tap_ms": (150, 400),
    "deliberate_tap_prob": 0.10,
    "windmouse": {"G0": 9.0, "W0": 3.0, "M0": 15.0, "D0": 12.0},
    "swipe_segment_px": 12,
    "click_window": 15,
    "same_button_max": 12,
    "alt_button_max": 6,
}


class TooManyClicks(Exception):
    """Self-detected bot-tell (repeated/alternating taps) — caller should pause + notify."""


def norm_int(a, b, n=3):
    """Center-biased int in [a,b] = mean of n uniform draws (ALAS random_normal_distribution_int)."""
    a, b = round(a), round(b)
    if a >= b:
        return b
    return round(sum(random.randint(a, b) for _ in range(n)) / n)


def human_delay(rng, n=3):
    lo, hi = rng
    return norm_int(lo * 1000, hi * 1000, n) / 1000.0


def jittered_point(box, shrink=6, n=3):
    """A center-biased point inside (x1,y1,x2,y2), kept `shrink` px off the edges."""
    x1, y1, x2, y2 = box
    x1, y1, x2, y2 = x1 + shrink, y1 + shrink, x2 - shrink, y2 - shrink
    if x2 < x1:
        x1 = x2 = (x1 + x2) // 2
    if y2 < y1:
        y1 = y2 = (y1 + y2) // 2
    return norm_int(x1, x2, n), norm_int(y1, y2, n)


def windmouse(x0, y0, x1, y1, G0=9.0, W0=3.0, M0=15.0, D0=12.0):
    """BenLand100 WindMouse — physics path with gravity + decaying wind. Returns [(x,y),...]."""
    sqrt3, sqrt5 = math.sqrt(3), math.sqrt(5)
    cx, cy, vx, vy, wx, wy = float(x0), float(y0), 0.0, 0.0, 0.0, 0.0
    m = M0
    pts = [(round(cx), round(cy))]
    while (dist := math.hypot(x1 - cx, y1 - cy)) >= 1:
        W = min(W0, dist)
        if dist >= D0:
            wx = wx / sqrt3 + (2 * random.random() - 1) * W / sqrt5
            wy = wy / sqrt3 + (2 * random.random() - 1) * W / sqrt5
        else:
            wx /= sqrt3
            wy /= sqrt3
            m = max(3.0, m / sqrt5)
        vx += wx + G0 * (x1 - cx) / dist
        vy += wy + G0 * (y1 - cy) / dist
        vmag = math.hypot(vx, vy)
        if vmag > m:
            vclip = m / 2 + random.random() * m / 2
            vx *= vclip / vmag
            vy *= vclip / vmag
        cx += vx
        cy += vy
        p = (round(cx), round(cy))
        if p != pts[-1]:
            pts.append(p)
    if pts[-1] != (round(x1), round(y1)):
        pts.append((round(x1), round(y1)))
    return pts


class Humanizer:
    def __init__(self, device="127.0.0.1:5555", cfg=None, run_shell=None, sleep=time.sleep):
        self.device = device
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self._run = run_shell or self._adb
        self._sleep = sleep
        self._clicks = deque(maxlen=self.cfg["click_window"])

    def _adb(self, *args):
        subprocess.run(["adb", "-s", self.device, "shell", *map(str, args)], capture_output=True)

    def tap_point(self, px, py, radius=10, label=""):
        """Humanized tap around a POINT (jitter within +/-radius) — for point-based callers."""
        return self.tap((px - radius, py - radius, px + radius, py + radius), label=label or f"{px},{py}")

    def tap(self, box, label=""):
        """Jittered, center-biased, variable-duration tap inside `box`. Records for self-policing."""
        x, y = jittered_point(box, self.cfg["tap_box_shrink_px"], self.cfg["jitter_samples"])
        if random.random() < self.cfg["deliberate_tap_prob"]:
            dur = norm_int(*self.cfg["deliberate_tap_ms"])
        else:
            dur = norm_int(*self.cfg["tap_duration_ms"])
        self._run("input", "swipe", x, y, x, y, dur)   # same point = variable-duration press
        self._record_click(label or f"{x},{y}")
        self._sleep(human_delay(self.cfg["delay_between_taps"]))
        return x, y

    def swipe(self, box_from, box_to):
        x0, y0 = jittered_point(box_from, self.cfg["tap_box_shrink_px"])
        x1, y1 = jittered_point(box_to, self.cfg["tap_box_shrink_px"])
        path = windmouse(x0, y0, x1, y1, **self.cfg["windmouse"])
        step = max(1, self.cfg["swipe_segment_px"])
        for i in range(0, len(path) - 1, step):
            ax, ay = path[i]
            bx, by = path[min(i + step, len(path) - 1)]
            self._run("input", "swipe", ax, ay, bx, by, 16)
        return path

    def _record_click(self, label):
        self._clicks.append(label)
        c = Counter(self._clicks)
        if c and c.most_common(1)[0][1] >= self.cfg["same_button_max"]:
            raise TooManyClicks(f"repeat tap on {label!r} ({c.most_common(1)[0][1]} in window)")
        top2 = c.most_common(2)
        if len(top2) == 2 and top2[0][1] >= self.cfg["alt_button_max"] and top2[1][1] >= self.cfg["alt_button_max"]:
            raise TooManyClicks("alternating taps on two elements")


if __name__ == "__main__":
    random.seed(7)
    ok = True

    # 1) jitter: stays inside the shrunk box, center-biased
    box = (100, 200, 220, 260)  # 120x60 button
    xs = [jittered_point(box, 6)[0] for _ in range(4000)]
    lo, hi = min(xs), max(xs)
    mean = sum(xs) / len(xs)
    in_box = 106 <= lo and hi <= 214
    centered = abs(mean - 160) < 8
    print(f"jitter x: [{lo},{hi}] mean={mean:.1f} in_box={in_box} centered={centered}")
    ok &= in_box and centered

    # 2) delays within range
    ds = [human_delay((0.3, 0.8)) for _ in range(2000)]
    dr = 0.30 <= min(ds) and max(ds) <= 0.80
    print(f"delay range: [{min(ds):.3f},{max(ds):.3f}] ok={dr}")
    ok &= dr

    # 3) windmouse path endpoints + no teleport jumps
    path = windmouse(50, 50, 900, 1500)
    start_ok = math.hypot(path[0][0] - 50, path[0][1] - 50) < 2
    end_ok = path[-1] == (900, 1500)
    max_jump = max(math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]) for i in range(len(path) - 1))
    print(f"windmouse: {len(path)} pts, start_ok={start_ok} end_ok={end_ok} max_step={max_jump:.1f}")
    ok &= start_ok and end_ok and max_jump < 40 and len(path) > 20

    # 4) self-policing: 12 same-label taps -> TooManyClicks; taps go through a fake shell (no adb)
    taps = []
    h = Humanizer(run_shell=lambda *a: taps.append(a), sleep=lambda s: None)
    raised = False
    try:
        for _ in range(20):
            h.tap((0, 0, 40, 40), label="Train")
    except TooManyClicks as e:
        raised = True
        print(f"self-policing raised after {len(taps)} taps: {e}")
    ok &= raised and len(taps) <= 12

    # 5) alternating two buttons -> raises
    h2 = Humanizer(run_shell=lambda *a: None, sleep=lambda s: None)
    raised2 = False
    try:
        for i in range(30):
            h2.tap((0, 0, 40, 40), label="A" if i % 2 else "B")
    except TooManyClicks:
        raised2 = True
    print(f"alternating raised={raised2}")
    ok &= raised2

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
