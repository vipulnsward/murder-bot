import argparse
import os
import re
import subprocess
import time

import cv2
import numpy as np

DEVICE = "127.0.0.1:5555"
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(HERE, "templates")

TOPBAR_FOOD_TAP = (200, 33)
SCROLL_SWIPE = (540, 1400, 540, 500, 500)
LABEL_TO_USE = (550, 80)
MODAL_MINUS = (162, 1058)
MODAL_PLUS = (900, 1058)
MODAL_USE = (765, 1329)
MODAL_USE_GREEN_PROBES = [(690, 1305), (840, 1305), (690, 1352), (840, 1352)]
COUNT_REGION = (300, 1150, 770, 1205)
MATCH_THRESHOLD = 0.85


def adb(*args, binary=False):
    cmd = ["adb", "-s", DEVICE, *args]
    if binary:
        return subprocess.run(cmd, capture_output=True).stdout
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def screencap():
    raw = adb("exec-out", "screencap", "-p", binary=True)
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def tap(x, y):
    adb("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(0.25)


def back():
    adb("shell", "input", "keyevent", "4")
    time.sleep(0.8)


def locate(img, name):
    tpl = cv2.imread(os.path.join(TEMPLATE_DIR, name + ".png"))
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return float(score), loc


def read_count(img):
    x1, y1, x2, y2 = COUNT_REGION
    g = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cv2.imwrite(os.path.join(HERE, "_ct.png"), t)
    out = subprocess.run(
        ["tesseract", os.path.join(HERE, "_ct.png"), "stdout", "--psm", "7",
         "-c", "tessedit_char_whitelist=0123456789,/"],
        capture_output=True, text=True).stdout.strip()
    head = out.split("/")[0].replace(",", "").strip()
    return int(head) if head.isdigit() else None


def use_button_is_green(img):
    ok = 0
    for x, y in MODAL_USE_GREEN_PROBES:
        b, g, r = [int(v) for v in img[y, x]]
        if g > r and g > b:
            ok += 1
    return ok >= 3


def open_food_panel():
    back()
    tap(*TOPBAR_FOOD_TAP)
    time.sleep(1.0)


def scroll_to_1m(max_scrolls=4):
    for _ in range(max_scrolls):
        img = screencap()
        score, _ = locate(img, "food_1m_label")
        if score >= MATCH_THRESHOLD:
            return img
        x1, y1, x2, y2, dur = SCROLL_SWIPE
        adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur))
        time.sleep(1.0)
    img = screencap()
    score, _ = locate(img, "food_1m_label")
    return img if score >= MATCH_THRESHOLD else None


def set_count(target):
    for _ in range(8):
        tap(*MODAL_MINUS)
    time.sleep(0.3)
    c = read_count(screencap())
    if c is None:
        return None
    for _ in range(max(0, target - c)):
        adb("shell", "input", "tap", str(MODAL_PLUS[0]), str(MODAL_PLUS[1]))
    time.sleep(0.4)
    return read_count(screencap())


def topup(target=1000, cap=2000, dry_run=False):
    open_food_panel()
    img = scroll_to_1m()
    if img is None:
        print("ABORT: 1M Food row not found")
        return False
    score, loc = locate(img, "food_1m_label")
    ux, uy = loc[0] + LABEL_TO_USE[0], loc[1] + LABEL_TO_USE[1]
    b, g, r = [int(v) for v in img[uy, ux]]
    if not (g > r and g > b):
        print(f"ABORT: 1M Food Use button not green at ({ux},{uy})")
        return False
    tap(ux, uy)
    time.sleep(0.8)

    if read_count(screencap()) is None:
        print("ABORT: quantity modal not detected")
        return False

    count = set_count(target)
    print(f"count set to {count} (target {target}, cap {cap})")
    if count is None or count <= 0 or count > cap:
        print(f"ABORT: count {count} outside safe range (1..{cap})")
        return False

    img = screencap()
    if not use_button_is_green(img):
        print("ABORT: Use button not green")
        return False
    if dry_run:
        print(f"DRY-RUN: would open {count} x 1M Food (~{count}M food). Not pressing Use.")
        return True

    tap(*MODAL_USE)
    time.sleep(1.5)
    print(f"USED {count} x 1M Food (~{count}M food added).")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--cap", type=int, default=2000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.target > a.cap:
        print("target exceeds cap; refusing")
        return
    topup(a.target, a.cap, a.dry_run)


if __name__ == "__main__":
    main()
