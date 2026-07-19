import os
import subprocess
import sys
import time

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
D = "127.0.0.1:5555"
try:
    TARGET_ITEMS = int(sys.argv[1])
except (IndexError, ValueError):
    TARGET_ITEMS = 2000

import train_to_1b as T


def adb(*a):
    return subprocess.run(["adb", "-s", D, *a], capture_output=True).stdout


def cap():
    open("_ar.png", "wb").write(adb("exec-out", "screencap", "-p"))
    return cv2.imread("_ar.png")


def tap(x, y, d=0.6):
    adb("exec-out", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(d)


def m(img, name):
    t = cv2.imread(os.path.join(HERE, "templates", name + ".png"))
    r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    h, w = t.shape[:2]
    return mx, (loc[0] + w // 2, loc[1] + h // 2), (loc[0], loc[1])


def dismiss(img=None):
    for _ in range(3):
        img = img or cap()
        if m(img, "exit_dialog")[0] > 0.9:
            tap(360, 1134, 0.8)
            img = None
            continue
        break


def open_resources():
    for _ in range(5):
        img = cap()
        if m(img, "exit_dialog")[0] > 0.9:
            tap(360, 1134, 0.8)
            continue
        if m(img, "barracks_bldg")[0] > 0.85:
            break
        adb("exec-out", "input", "keyevent", "4")
        time.sleep(1.1)
    tap(200, 33, 1.5)


def find_1m_food():
    for _ in range(6):
        img = cap()
        mx, _, tl = m(img, "food_1m_label")
        if mx >= 0.90:
            return tl
        adb("exec-out", "input", "swipe", "540", "1400", "540", "650", "500")
        time.sleep(1.0)
    return None


def refill(target=TARGET_ITEMS):
    dismiss()
    open_resources()
    tl = find_1m_food()
    if tl is None:
        print("REFILL FAIL: 1M Food row not found")
        return False
    tap(tl[0] + 525, tl[1] + 135, 1.5)
    cnt = T.read_food_count(cap())
    if not cnt or cnt < 1000:
        tl = find_1m_food()
        if tl:
            tap(tl[0] + 525, tl[1] + 135, 1.5)
            cnt = T.read_food_count(cap())
    if not cnt or cnt < 1000:
        print("REFILL FAIL: modal did not open (cnt=%s)" % cnt)
        tap(1010, 594)
        return False
    tap(310, 1325, 1.0)  # Minimum
    cnt = T.read_food_count(cap())
    if cnt is None or cnt > 50:
        print("REFILL FAIL: minimum not reached", cnt)
        tap(1010, 594)
        return False
    for _ in range(14):
        cnt = T.read_food_count(cap()) or 0
        if cnt >= target:
            break
        rem = target - cnt
        taps = rem if rem <= 250 else min(int(rem / 0.85), 900)
        adb("shell", "i=0; while [ $i -lt %d ]; do input tap 900 1058; i=$((i+1)); done" % taps)
        time.sleep(0.25)
    cnt = T.read_food_count(cap())
    if cnt is None or cnt <= 0 or cnt > target * 1.3:
        print("REFILL FAIL: unsafe count", cnt)
        tap(1010, 594)
        return False
    tap(765, 1325, 1.8)  # Use
    print("REFILL OK: opened ~%d x 1M Food (~%.2fB food)" % (cnt, cnt / 1000.0))
    tap(1010, 594, 0.6)
    return True


def to_warriors():
    for _ in range(4):
        img = cap()
        if m(img, "warriors_title")[0] > 0.9 or m(img, "speedup_btn")[0] > 0.9:
            return True
        if m(img, "exit_dialog")[0] > 0.9:
            tap(360, 1134, 0.8)
            continue
        bmx, bc, _ = m(img, "barracks_bldg")
        if bmx > 0.85:
            tap(bc[0], bc[1], 1.4)
            rmx, rc, _ = m(cap(), "radial_train")
            if rmx > 0.85:
                tap(rc[0], rc[1], 1.6)
            continue
        adb("exec-out", "input", "keyevent", "4")
        time.sleep(1.1)
    return m(cap(), "warriors_title")[0] > 0.9


PKG = "com.topgamesinc.evony.flexion"


def app_refresh():
    print("app_refresh: force-stopping + relaunching", PKG)
    adb("shell", "am", "force-stop", PKG)
    time.sleep(3)
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    for _ in range(12):
        time.sleep(5)
        img = cap()
        if m(img, "warriors_title")[0] > 0.9 or m(img, "barracks_bldg")[0] > 0.85:
            break
        if m(img, "exit_dialog")[0] > 0.9:
            tap(360, 1134, 0.8)
        else:
            adb("exec-out", "input", "keyevent", "4")
    ok = to_warriors()
    print("app_refresh: back on Warriors" if ok else "app_refresh: could not reach Warriors")
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        sys.exit(0 if app_refresh() else 1)
    ok = refill()
    if not ok:
        sys.exit(1)
    w = to_warriors()
    print("to_warriors:", w)
    sys.exit(0 if w else 2)
