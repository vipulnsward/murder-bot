import os
import time

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
TDIR = os.path.join(HERE, "templates")

# Action coordinates (1080x1920 BlueStacks), shared with train_to_1b.
CAP_CONFIRM = (714, 1134)
CANCEL_TAP = (360, 1134)
CLOSE_X = (1010, 594)
VIEW_FALLBACK = (355, 690)

# Screen anchors, checked in this order (most-critical / most-specific first).
# The first anchor whose best match >= its threshold names the screen. The city
# anchor (barracks_bldg) is camera-zoom sensitive, so it gets a lower threshold;
# it's checked last, after every distinct screen, so the loose match is safe.
ANCHOR_ORDER = [
    ("disconnect", "disconnect_popup", 0.85),
    ("speedup_modal", "modal_speedup_title", 0.85),
    ("cap_popup", "cap_popup", 0.85),
    ("exit_dialog", "exit_dialog", 0.85),
    ("resources", "food_1m_label", 0.85),
    ("training_idle", "train_btn_idle", 0.85),
    ("training_busy", "speedup_btn", 0.85),
    ("barracks_radial", "radial_speedup", 0.80),
    ("barracks_radial", "radial_train", 0.80),
    ("city", "barracks_bldg", 0.60),
]

# Screens the training loop can act on directly (no further nav needed).
READY = {"training_idle", "training_busy", "cap_popup"}
FINISH_ALL = (280, 1840)  # "Finish All" in the Training Speedup modal (verified)


class DisconnectError(Exception):
    """The 'someone login with your account' screen — never auto-tapped."""


def _match(img, name):
    t = cv2.imread(os.path.join(TDIR, name + ".png"))
    if t is None or img is None:
        return 0.0, (0, 0)
    if img.shape[0] < t.shape[0] or img.shape[1] < t.shape[1]:
        return 0.0, (0, 0)
    r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    _, s, _, loc = cv2.minMaxLoc(r)
    th, tw = t.shape[:2]
    return float(s), (loc[0] + tw // 2, loc[1] + th // 2)


def is_disconnect(img, min_score=0.85):
    """Cheap single-template check for the account-disconnect popup (hot path)."""
    return img is not None and _match(img, "disconnect_popup")[0] >= min_score


def identify(img):
    if img is None:
        return "unknown"
    for name, tpl, thr in ANCHOR_ORDER:
        if _match(img, tpl)[0] >= thr:
            return name
    return "unknown"


def ensure_training(screencap, tap, back, tries=14, min_score=0.85):
    """Drive the game to a state the training loop can act on.

    Returns (screen, img) once on a READY screen. Raises DisconnectError the
    moment the disconnect popup is seen (caller decides — we never tap it).
    Returns ("unknown", img) if it can't get there within `tries`.
    """
    for _ in range(tries):
        img = screencap()
        s = identify(img)
        if s == "disconnect":
            raise DisconnectError()
        if s in READY:
            return s, img
        if s == "speedup_modal":
            # GEM-SAFE: never auto-tap "Finish All" (it spends gems on oversized/stacked
            # batches). Close the modal and reach the training screen, where the normal
            # loop clears a normal batch with speedup ITEMS.
            tap(*CLOSE_X, d=0.5)
        elif s == "exit_dialog":
            tap(*CANCEL_TAP, d=0.7)
        elif s == "resources":
            tap(*CLOSE_X, d=0.5)
            back(0.8)
        elif s == "barracks_radial":
            # Go to the training screen (View/Train). Never auto-open Speed Up -> Finish
            # All from recovery (gem risk); the training loop handles a busy barracks.
            _, c = _match(img, "radial_train")
            tap(*c, d=1.4) if c != (0, 0) else tap(*VIEW_FALLBACK, d=1.4)
        elif s == "city":
            sc, c = _match(img, "barracks_bldg")
            tap(*c, d=1.4)          # open the barracks radial
        else:  # unknown / loading
            back(1.0)
    return "unknown", screencap()


def try_ensure_training(screencap, tap, back, tries=14, min_score=0.85):
    """Non-raising ensure_training for in-loop recovery: returns the screen
    string, or 'disconnect' instead of raising (caller's next cycle handles it)."""
    try:
        return ensure_training(screencap, tap, back, tries, min_score)[0]
    except DisconnectError:
        return "disconnect"


if __name__ == "__main__":
    import sys

    # 1) identify() on saved frames (offline, deterministic)
    cases = [
        ("_cur.png", "training_idle"),
        ("status_s.png", "city"),
        ("status_r2.png", "disconnect"),
        ("status_fa.png", "disconnect"),
    ]
    ok = True
    for f, expect in cases:
        if not os.path.exists(f):
            print(f"  (skip {f}: missing)")
            continue
        got = identify(cv2.imread(f))
        mark = "ok" if got == expect else "FAIL"
        ok &= got == expect
        print(f"  identify({f}) = {got}  (expect {expect}) [{mark}]")

    # 2) disconnect safety: ensure_training must RAISE, never tap
    taps = {"n": 0}
    def fake_tap(*a, **k): taps["n"] += 1
    def fake_back(*a, **k): pass
    def dis_cap():
        return cv2.imread("status_r2.png")
    try:
        ensure_training(dis_cap, fake_tap, fake_back, tries=3)
        print("  disconnect safety: FAIL (did not raise)")
        ok = False
    except DisconnectError:
        print(f"  disconnect safety: raised DisconnectError, taps={taps['n']} (expect 0) [{'ok' if taps['n']==0 else 'FAIL'}]")
        ok &= taps["n"] == 0

    # 3) already-on-training short-circuits with zero taps
    taps["n"] = 0
    s, _ = ensure_training(lambda: cv2.imread("_cur.png"), fake_tap, fake_back, tries=3)
    print(f"  ensure_training on idle -> {s}, taps={taps['n']} (expect training_idle, 0) [{'ok' if s=='training_idle' and taps['n']==0 else 'FAIL'}]")
    ok &= s == "training_idle" and taps["n"] == 0

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
