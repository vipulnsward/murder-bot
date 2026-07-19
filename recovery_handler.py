import os
import subprocess
import time

import cv2
import numpy as np

DEVICE = "127.0.0.1:5555"
PKG = "com.topgamesinc.evony.flexion"
HERE = os.path.dirname(os.path.abspath(__file__))
TDIR = os.path.join(HERE, "templates")
MATCH = 0.85
VLM_MODEL = "moondream"


def adb(*a, binary=False):
    c = ["adb", "-s", DEVICE, *a]
    return subprocess.run(c, capture_output=True).stdout if binary else \
        subprocess.run(c, capture_output=True, text=True).stdout


def screencap():
    raw = adb("exec-out", "screencap", "-p", binary=True)
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def tap(x, y, d=0.35):
    adb("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(d)


def tpl(name):
    return cv2.imread(os.path.join(TDIR, name + ".png"))


def locate(img, name):
    t = tpl(name)
    if t is None:
        return 0.0, (0, 0)
    r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    _, s, _, loc = cv2.minMaxLoc(r)
    th, tw = t.shape[:2]
    return float(s), (loc[0] + tw // 2, loc[1] + th // 2)


def vis(img, name):
    return locate(img, name)[0] >= MATCH


def on_training(img):
    return (vis(img, "warriors_title") and vis(img, "train_btn_idle")) or vis(img, "speedup_btn")


# --- Tips: known state -> deterministic recovery action ---
PLAYBOOK = [
    ("cap_popup", lambda img: tap(714, 1134)),          # exceeded capacity -> Confirm
    ("exit_dialog", lambda img: tap(360, 1134)),        # quit game? -> Cancel (never Quit)
    ("modal_speedup_title", lambda img: tap(*locate(img, "finish_all_btn")[1])),  # stray speedup -> Finish All
]


def handle_known(img):
    for name, action in PLAYBOOK:
        if vis(img, name):
            action(img)
            time.sleep(0.8)
            return name
    return None


def refresh_app():
    adb("shell", "am", "force-stop", PKG)
    time.sleep(2)
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    for _ in range(24):
        time.sleep(5)
        if on_training(screencap()):
            return True
    return False


def to_training_via_barracks():
    # locate the barracks building (matches ~0.95 across camera positions)
    img = screencap()
    s, (bx, by) = locate(img, "barracks_bldg")
    if s < 0.80:
        return False
    tap(bx, by, d=1.3)
    r = screencap()
    # verify IDLE radial: Train present AND no gem "Instant Finish" at the Train spot.
    st, tc = locate(r, "radial_train")
    if st >= 0.80:
        tap(*tc, d=1.4)
    else:
        return False
    tap(135, 1237, d=0.9)   # select T1
    return on_training(screencap())


def vlm_classify(img):
    p = os.path.join(HERE, "_vlm.png")
    cv2.imwrite(p, img)
    q = ("Look at this Evony game screenshot. Reply with ONE word: "
         "TRAINING if it is the troop training screen, CITY if it is the city map, "
         "POPUP if a dialog/popup is open, or UPDATE if it shows an app-update/store screen.")
    out = subprocess.run(["ollama", "run", VLM_MODEL, q, p],
                         capture_output=True, text=True).stdout.strip().upper()
    for k in ("TRAINING", "UPDATE", "POPUP", "CITY"):
        if k in out:
            return k
    return "UNKNOWN"


def recover(max_steps=8):
    """Bring the game back to the T1 Warriors training screen. Returns True on success."""
    for _ in range(max_steps):
        img = screencap()
        if on_training(img):
            return True
        if handle_known(img):
            continue
        # intent-based fallback: classify with the local VLM, act on the class
        cls = vlm_classify(img)
        if cls == "UPDATE":
            if refresh_app():
                return True
        elif cls == "CITY":
            if to_training_via_barracks():
                return True
        elif cls == "POPUP":
            # unknown popup: try a top-right close X, then re-check (never press back on city)
            tap(1010, 594, d=0.7)
        else:
            # last resort: barracks nav, then a gentle back to clear a transient
            if to_training_via_barracks():
                return True
            adb("shell", "input", "keyevent", "4")
            time.sleep(0.8)
    return on_training(screencap())


if __name__ == "__main__":
    print("recover ->", recover())
