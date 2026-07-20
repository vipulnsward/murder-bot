import os
import subprocess
import time

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE = "127.0.0.1:5555"
PKG = "com.topgamesinc.evony.flexion"

# Any one of these matching means we're on a known, live game screen.
ANCHORS = ("train_btn_idle", "speedup_btn", "warriors_title", "barracks_bldg",
           "radial_train", "exit_dialog")


def _match(img, name, templates_dir):
    t = cv2.imread(os.path.join(templates_dir, name + ".png"))
    if t is None or img is None:
        return 0.0
    if img.shape[0] < t.shape[0] or img.shape[1] < t.shape[1]:
        return 0.0
    r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(r)[1])


def healthy(img, templates_dir=None, min_score=0.85):
    """True if the frame matches any known game-screen anchor."""
    templates_dir = templates_dir or os.path.join(HERE, "templates")
    if img is None:
        return False
    return any(_match(img, a, templates_dir) >= min_score for a in ANCHORS)


def is_app_running(device=DEVICE, pkg=PKG):
    out = subprocess.run(
        ["adb", "-s", device, "shell", "pidof", pkg], capture_output=True, text=True
    ).stdout.strip()
    return bool(out)


class Watchdog:
    """Detects a crashed / stuck / off-screen game and triggers recovery.

    Feed it frames (or let .tick() grab them). It recovers when EITHER the app
    process is gone, OR `fail_threshold` consecutive frames match no known
    anchor (crash, black screen, unexpected external screen). Recovery is
    injectable; the default lazily calls auto_refill.app_refresh (proven).
    """

    def __init__(self, device=DEVICE, pkg=PKG, fail_threshold=3,
                 recover_fn=None, grab_fn=None, templates_dir=None):
        self.device = device
        self.pkg = pkg
        self.fail_threshold = fail_threshold
        self.recover_fn = recover_fn
        self.grab_fn = grab_fn
        self.templates_dir = templates_dir or os.path.join(HERE, "templates")
        self.consecutive_unhealthy = 0
        self.recoveries = 0

    def _default_recover(self):
        import auto_refill
        return auto_refill.app_refresh()

    def recover(self):
        self.recoveries += 1
        fn = self.recover_fn or self._default_recover
        ok = fn()
        self.consecutive_unhealthy = 0
        return ok

    def observe(self, img, app_running=True):
        """Update state from one frame. Returns 'ok' | 'unhealthy' | 'RECOVER'."""
        if not app_running:
            self.consecutive_unhealthy = self.fail_threshold
            return "RECOVER"
        if healthy(img, self.templates_dir):
            self.consecutive_unhealthy = 0
            return "ok"
        self.consecutive_unhealthy += 1
        return "RECOVER" if self.consecutive_unhealthy >= self.fail_threshold else "unhealthy"

    def tick(self):
        """Grab a frame + check app, act on it. Returns the state string."""
        running = is_app_running(self.device, self.pkg)
        img = None if not running else (self.grab_fn() if self.grab_fn else None)
        state = self.observe(img, app_running=running)
        if state == "RECOVER":
            self.recover()
        return state


if __name__ == "__main__":
    import sys

    import numpy as np
    import fast_screenshot

    dev = sys.argv[1] if len(sys.argv) > 1 else DEVICE
    tdir = os.path.join(HERE, "templates")
    ok = True

    # 1) app-running detection: real package True, fake package False
    real = is_app_running(dev, PKG)
    fake = is_app_running(dev, "com.does.not.exist")
    print(f"is_app_running real={real} (expect True)  fake={fake} (expect False)")
    ok &= real and not fake

    # 2) health on a LIVE frame (game is up) -> healthy
    live = fast_screenshot.grab(dev)
    live_scores = {a: round(_match(live, a, tdir), 3) for a in ANCHORS}
    live_ok = healthy(live, tdir)
    print(f"live frame healthy={live_ok} (expect True)  scores={live_scores}")
    ok &= live_ok

    # 3) health on a black frame -> unhealthy
    black = np.zeros((1920, 1080, 3), np.uint8)
    black_ok = healthy(black, tdir)
    print(f"black frame healthy={black_ok} (expect False)")
    ok &= not black_ok

    # 4) Watchdog decision logic with a MOCK recover (no real force-stop)
    calls = {"n": 0}
    wd = Watchdog(dev, PKG, fail_threshold=3, recover_fn=lambda: calls.__setitem__("n", calls["n"] + 1) or True)
    seq = [wd.observe(black, True) for _ in range(2)]          # 2 unhealthy, not yet
    seq.append(wd.observe(black, True))                         # 3rd -> RECOVER (triggers via tick, but observe only reports)
    trig_via_observe = seq
    # simulate the tick loop deciding to recover
    wd2 = Watchdog(dev, PKG, fail_threshold=3, recover_fn=lambda: calls.__setitem__("n", calls["n"] + 1) or True)
    states = []
    for _ in range(4):
        s = wd2.observe(black, app_running=True)
        if s == "RECOVER":
            wd2.recover()
        states.append(s)
    print(f"consecutive-unhealthy states={states} (expect unhealthy,unhealthy,RECOVER,unhealthy) recover_calls={calls['n']}")
    ok &= states == ["unhealthy", "unhealthy", "RECOVER", "unhealthy"] and calls["n"] == 1

    # 5) app-gone short-circuits straight to RECOVER
    wd3 = Watchdog(dev, PKG, fail_threshold=3, recover_fn=lambda: True)
    gone = wd3.observe(live, app_running=False)
    print(f"app-not-running -> {gone} (expect RECOVER)")
    ok &= gone == "RECOVER"

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
