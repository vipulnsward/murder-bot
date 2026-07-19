import argparse
import os
import re
import subprocess
import time

import cv2
import numpy as np

DEVICE = "127.0.0.1:5555"
HERE = os.path.dirname(os.path.abspath(__file__))
TDIR = os.path.join(HERE, "templates")

TARGET_OWN = 1_500_000_000
TRAIN_QTY = 271766
MATCH = 0.85

BARRACKS_TAP = (500, 800)
RADIAL_TRAIN_TAP = (179, 679)
T1_ICON_TAP = (135, 1237)
CANCEL_TAP = (360, 1134)
CAP_CONFIRM = (714, 1134)
QTY_FIELD_TAP = (880, 1588)
OK_TAP = (975, 1852)
OWN_REGION = (330, 1070, 760, 1140)
QTY_REGION = (745, 1548, 1015, 1628)

TOPBAR_FOOD_TAP = (200, 33)
SCROLL = (540, 1400, 540, 500, 500)
LABEL_TO_USE = (550, 80)
M_MINUS = (162, 1058)
M_PLUS = (900, 1058)
M_MIN_BTN = (311, 1328)
M_USE = (765, 1329)
M_USE_PROBES = [(690, 1305), (840, 1305), (690, 1352), (840, 1352)]
M_COUNT = (300, 1150, 770, 1205)
CLOSE_X = (1010, 594)

FOOD_TARGET = 2000
FOOD_CAP = 2500


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def adb(*a, binary=False):
    c = ["adb", "-s", DEVICE, *a]
    return subprocess.run(c, capture_output=True).stdout if binary else \
        subprocess.run(c, capture_output=True, text=True).stdout


def screencap():
    raw = adb("exec-out", "screencap", "-p", binary=True)
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def tap(x, y, d=0.2):
    adb("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(d)


def back(d=0.9):
    adb("shell", "input", "keyevent", "4")
    time.sleep(d)


def tpl(name):
    return cv2.imread(os.path.join(TDIR, name + ".png"))


def locate(img, name):
    t = tpl(name)
    r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    _, s, _, loc = cv2.minMaxLoc(r)
    th, tw = t.shape[:2]
    return float(s), (loc[0], loc[1]), (loc[0] + tw // 2, loc[1] + th // 2)


def vis(img, name):
    return locate(img, name)[0] >= MATCH


def ocr(img, box, wl):
    x1, y1, x2, y2, = box
    g = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    inv = cv2.THRESH_BINARY_INV if box == M_COUNT else cv2.THRESH_BINARY
    _, t = cv2.threshold(g, 0, 255, inv + cv2.THRESH_OTSU)
    cv2.imwrite(os.path.join(HERE, "_t.png"), t)
    return subprocess.run(["tesseract", os.path.join(HERE, "_t.png"), "stdout",
                           "--psm", "7", "-c", f"tessedit_char_whitelist={wl}"],
                          capture_output=True, text=True).stdout.strip()


def read_own(img):
    o = ocr(img, OWN_REGION, "0123456789,")
    m = re.findall(r"[\d,]{4,}", o)
    return int(max(m, key=len).replace(",", "")) if m else None


def read_qty(img):
    o = ocr(img, QTY_REGION, "0123456789")
    m = re.findall(r"\d{3,}", o)
    return int(max(m, key=len)) if m else None


def read_food_count(img):
    o = ocr(img, M_COUNT, "0123456789,/")
    h = o.split("/")[0].replace(",", "").strip()
    return int(h) if h.isdigit() else None


FOOD_BOX = (150, 8, 300, 64)
FOOD_LOW = 0


def read_food_topbar(img):
    x1, y1, x2, y2 = FOOD_BOX
    g = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cv2.imwrite(os.path.join(HERE, "_f.png"), t)
    o = subprocess.run(["tesseract", os.path.join(HERE, "_f.png"), "stdout",
                        "--psm", "7", "-c", "tessedit_char_whitelist=0123456789.KMB"],
                       capture_output=True, text=True).stdout.strip().replace(" ", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KMB])", o)
    if m:
        return float(m.group(1)) * {"B": 1e9, "M": 1e6, "K": 1e3}[m.group(2)]
    return None


def on_warriors_idle(img=None):
    img = img if img is not None else screencap()
    return vis(img, "warriors_title") and vis(img, "train_btn_idle"), img


def to_city():
    for _ in range(6):
        img = screencap()
        if vis(img, "exit_dialog"):
            tap(*CANCEL_TAP, d=0.7)
            return
        if vis(img, "modal_speedup_title"):
            tap(*CLOSE_X, d=0.5)
            continue
        back()


def goto_warriors(tries=6):
    for _ in range(tries):
        img = screencap()
        if on_warriors_idle(img)[0] or vis(img, "speedup_btn"):
            return img
        if vis(img, "exit_dialog"):
            tap(*CANCEL_TAP, d=0.7)
            continue
        if vis(img, "cap_popup"):
            tap(*CAP_CONFIRM, d=0.7)
            continue
        back()
    img = screencap()
    if on_warriors_idle(img)[0] or vis(img, "speedup_btn"):
        return img
    return None


def set_train_qty(img):
    if read_qty(img) == TRAIN_QTY:
        return
    tap(*T1_ICON_TAP)
    tap(*QTY_FIELD_TAP, d=0.5)
    adb("shell", "input", "keyevent", *(["67"] * 8))
    adb("shell", "input", "text", str(TRAIN_QTY))
    time.sleep(0.25)
    tap(*OK_TAP, d=0.4)


def wait_for(name, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        img = screencap()
        if vis(img, name):
            return img
        time.sleep(0.25)
    return None


def train_one_batch():
    img = screencap()
    if vis(img, "speedup_btn"):
        busy = img
    elif on_warriors_idle(img)[0]:
        s, _, c = locate(img, "train_btn_idle")
        if s < MATCH:
            return "NAV"
        tap(*c)
        time.sleep(0.7)
        p = screencap()
        if vis(p, "cap_popup"):
            tap(*CAP_CONFIRM, d=0.6)
        busy = wait_for("speedup_btn", 8)
        if busy is None:
            return "NOFOOD"
    else:
        return "NAV"
    _, _, c = locate(busy, "speedup_btn")
    tap(*c)
    modal = wait_for("modal_speedup_title", 8)
    if modal is None:
        return "SKIP"
    s, _, c = locate(modal, "finish_all_btn")
    if s < MATCH:
        return "SKIP"
    tap(*c)
    if wait_for("train_btn_idle", 10) is None:
        return "SKIP"
    return "OK"


def use_green(img):
    return sum(1 for x, y in M_USE_PROBES
               if img[y, x][1] > img[y, x][2] and img[y, x][1] > img[y, x][0]) >= 3


def topup_food(target=FOOD_TARGET, cap=FOOD_CAP):
    to_city()
    tap(*TOPBAR_FOOD_TAP, d=1.1)
    found = None
    for _ in range(4):
        img = screencap()
        if locate(img, "food_1m_label")[0] >= MATCH:
            found = img
            break
        x1, y1, x2, y2, dur = SCROLL
        adb("shell", "input", "swipe", *map(str, (x1, y1, x2, y2, dur)))
        time.sleep(1.0)
    if found is None:
        log("topup ABORT: 1M Food row not found")
        return False
    s, loc, _ = locate(found, "food_1m_label")
    ux, uy = loc[0] + LABEL_TO_USE[0], loc[1] + LABEL_TO_USE[1]
    px = found[uy, ux]
    if not (px[1] > px[2] and px[1] > px[0]):
        log("topup ABORT: 1M Use not green")
        return False
    tap(ux, uy, d=1.4)

    cnt = None
    for _ in range(8):
        time.sleep(0.4)
        cnt = read_food_count(screencap())
        if cnt is not None:
            break
    if cnt is None:
        log("topup ABORT: modal not detected")
        tap(*CLOSE_X); return False

    tap(*M_MIN_BTN, d=0.5)
    cnt = None
    for _ in range(6):
        time.sleep(0.3)
        cnt = read_food_count(screencap())
        if cnt is not None and cnt <= 5:
            break
    if cnt is None or cnt > 5:
        adb("shell", "input", "swipe", "840", "1058", "150", "1058", "400")
        for _ in range(5):
            time.sleep(0.3)
            cnt = read_food_count(screencap())
            if cnt is not None and cnt <= 50:
                break
    if cnt is None or cnt > 50:
        log("topup ABORT: could not reach minimum"); tap(*CLOSE_X); return False
    log(f"at minimum (count={cnt}); +{target - cnt} to reach {target}")
    for _ in range(max(0, target - cnt)):
        adb("shell", "input", "tap", str(M_PLUS[0]), str(M_PLUS[1]))
        time.sleep(0.02)
    time.sleep(0.4)
    img = screencap()
    cnt = read_food_count(img)
    log(f"topup: count={cnt} (target {target}, cap {cap})")
    if cnt is None or cnt <= 0 or cnt > cap or not use_green(img):
        log("topup ABORT: safety gate failed"); tap(*CLOSE_X); return False
    tap(*M_USE, d=1.4)
    log(f"topup: opened {cnt} x 1M Food (~{cnt}M food).")
    tap(*CLOSE_X, d=0.5)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-topups", type=int, default=100)
    a = ap.parse_args()
    log(f"target={TARGET_OWN:,} qty={TRAIN_QTY:,} food_target={FOOD_TARGET}")
    if goto_warriors() is None:
        log("warning: not on Warriors screen at start; loop will recover")
    ok_batches = 0
    topups = 0
    fails = 0
    cyc = 0
    while True:
        cyc += 1
        do_check = (cyc % 10 == 1)
        img = screencap()
        idle = on_warriors_idle(img)[0]
        if fails >= 10:
            log(f"STOP: {fails} consecutive failures — needs a human look."); break

        low_food = False
        if idle and do_check:
            own = read_own(img)
            if own is not None:
                log(f"batches={ok_batches} own={own:,} (to 1B: {max(0, TARGET_OWN - own):,})")
                if own >= TARGET_OWN:
                    log(f"DONE: Own {own:,} >= {TARGET_OWN:,}. batches={ok_batches} topups={topups}")
                    break
            food = read_food_topbar(img)
            if food is not None and food < FOOD_LOW:
                low_food = True
                log(f"food ~{food/1e6:.0f}M < {FOOD_LOW//1_000_000}M — top-up #{topups+1}")

        if low_food:
            r = "NOFOOD"
        else:
            r = train_one_batch()

        if r == "OK":
            ok_batches += 1
            fails = 0
            log(f"batch {ok_batches} ok")
        elif r == "NOFOOD":
            fimg = screencap()
            if vis(fimg, "cap_popup"):
                tap(*CAP_CONFIRM, d=0.6)
                fails = 0
                continue
            food = read_food_topbar(fimg)
            if not low_food and (food is None or food >= FOOD_LOW):
                log(f"train didn't start; food ~{(food or 0)/1e6:.0f}M ok — retry (no nav)")
                fails += 1
                time.sleep(1.5)
                continue
            log(f"food genuinely low — top-up #{topups+1}")
            done = False
            for attempt in range(2):
                if topup_food():
                    done = True
                    break
                goto_warriors()
            if done:
                topups += 1
                goto_warriors()
                fails = 0
            else:
                fails += 1
            time.sleep(2)
        else:
            fails += 1
            goto_warriors()
            time.sleep(1.5)
    log(f"ended: {ok_batches} batches, {topups} food top-ups (~{ok_batches*TRAIN_QTY:,} troops).")


if __name__ == "__main__":
    main()
