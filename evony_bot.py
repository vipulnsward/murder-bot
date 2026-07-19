import argparse
import os
import random
import re
import subprocess
import sys
import time

import cv2
import numpy as np

import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(HERE, "templates")
TEMPLATES = {}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def adb(*args, binary=False):
    cmd = ["adb", "-s", C.DEVICE, *args]
    if binary:
        return subprocess.run(cmd, capture_output=True).stdout
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def screencap():
    raw = adb("exec-out", "screencap", "-p", binary=True)
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def load_templates():
    for f in os.listdir(TEMPLATE_DIR):
        if f.endswith(".png"):
            TEMPLATES[f[:-4]] = cv2.imread(os.path.join(TEMPLATE_DIR, f))


def locate(img, name):
    tpl = TEMPLATES[name]
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    th, tw = tpl.shape[:2]
    return float(score), (loc[0] + tw // 2, loc[1] + th // 2)


def visible(img, name):
    score, _ = locate(img, name)
    return score >= C.MATCH_THRESHOLD


def wait_for(name, timeout=None):
    timeout = C.STEP_TIMEOUT if timeout is None else timeout
    end = time.time() + timeout
    while time.time() < end:
        img = screencap()
        if visible(img, name):
            return img
        time.sleep(C.POLL_INTERVAL)
    return None


def tap_xy(x, y):
    x += random.randint(-C.TAP_JITTER_PX, C.TAP_JITTER_PX)
    y += random.randint(-C.TAP_JITTER_PX, C.TAP_JITTER_PX)
    adb("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(random.uniform(C.TAP_DELAY_MIN, C.TAP_DELAY_MAX))


def tap_template(img, name):
    score, center = locate(img, name)
    if score < C.MATCH_THRESHOLD:
        return False
    tap_xy(*center)
    return True


def ocr_number(img, box):
    x1, y1, x2, y2 = box
    crop = img[y1:y2, x1:x2]
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thr = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    tmp = os.path.join(HERE, "_ocr.png")
    cv2.imwrite(tmp, thr)
    out = subprocess.run(
        ["tesseract", tmp, "stdout", "--psm", "7",
         "-c", "tessedit_char_whitelist=0123456789,"],
        capture_output=True, text=True,
    ).stdout
    nums = re.findall(r"[\d,]{2,}", out)
    if not nums:
        return None
    best = max(nums, key=lambda s: len(s.replace(",", "")))
    try:
        return int(best.replace(",", ""))
    except ValueError:
        return None


def read_own(img):
    return ocr_number(img, C.OWN_REGION)


def read_qty(img):
    return ocr_number(img, C.QTY_REGION)


def type_quantity(n):
    tap_xy(*C.QTY_FIELD_TAP)
    time.sleep(0.18)
    adb("shell", "input", "keyevent", *(["67"] * 8))
    adb("shell", "input", "text", str(n))
    time.sleep(0.12)
    tap_xy(*C.OK_TAP)
    time.sleep(0.18)


def ensure_idle_warriors():
    img = screencap()
    if visible(img, "train_btn_idle") and visible(img, "warriors_title"):
        return img
    for _ in range(2):
        adb("shell", "input", "keyevent", "4")
        time.sleep(0.8)
        img = screencap()
        if visible(img, "train_btn_idle") and visible(img, "warriors_title"):
            return img
    return None


def run_cycle(dry_run):
    img = ensure_idle_warriors()
    if img is None:
        log("not on idle Warriors screen — leave the game on the T1 Warriors "
            "training screen. skipping.")
        return "PAUSE"

    own = read_own(img)
    own_str = f"{own:,}" if own is not None else "unread"
    if own is not None and own >= C.TARGET_OWN:
        log(f"TARGET REACHED: own={own_str} >= {C.TARGET_OWN:,}. stopping.")
        return "DONE"

    if dry_run:
        log(f"[dry-run] idle, own={own_str}, would train {C.TRAIN_QTY:,} "
            f"then Finish All. no taps sent.")
        return "PAUSE"

    if read_qty(img) != C.TRAIN_QTY:
        tap_xy(*C.T1_ICON_TAP)
        type_quantity(C.TRAIN_QTY)
        img = screencap()

    if not tap_template(img, "train_btn_idle"):
        log("Train button not found after entering qty. skipping.")
        return "PAUSE"

    busy = wait_for("speedup_btn")
    if busy is None:
        log("did not enter training (insufficient food or blocked?). stopping.")
        return "STOP"

    if not tap_template(busy, "speedup_btn"):
        log("could not open Training Speedup. skipping.")
        return "PAUSE"

    modal = wait_for("modal_speedup_title")
    if modal is None:
        log("speedup modal did not open. skipping.")
        return "PAUSE"

    finisher = "finish_all_btn" if C.USE_FINISH_ALL else "use_btn"
    if not tap_template(modal, finisher):
        log(f"{finisher} not found. skipping.")
        return "PAUSE"

    done = wait_for("train_btn_idle")
    if done is None:
        log("did not return to idle after Finish All.")
        return "PAUSE"

    new_own = read_own(done)
    if new_own is not None and own is not None:
        log(f"cycle ok: own {own:,} -> {new_own:,} (+{new_own - own:,})")
    else:
        log(f"cycle ok: own now {new_own:,}" if new_own else "cycle ok (own unread)")
    return "CONTINUE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max-cycles", type=int, default=0)
    args = ap.parse_args()

    load_templates()
    log(f"device={C.DEVICE} target={C.TARGET_OWN:,} qty={C.TRAIN_QTY:,} "
        f"dry_run={args.dry_run} templates={len(TEMPLATES)}")

    cycles = 0
    ok_cycles = 0
    consec_pause = 0
    while True:
        result = run_cycle(args.dry_run)
        cycles += 1
        if result == "CONTINUE":
            ok_cycles += 1
        if result in ("DONE", "STOP"):
            break
        if args.once:
            break
        if args.max_cycles and cycles >= args.max_cycles:
            log(f"reached max-cycles={args.max_cycles}. stopping.")
            break
        if result == "PAUSE":
            consec_pause += 1
            if consec_pause >= C.MAX_CONSEC_PAUSE:
                log(f"{consec_pause} consecutive skips — food likely exhausted "
                    f"or stuck. stopping.")
                break
            time.sleep(C.PAUSE_SLEEP)
        else:
            consec_pause = 0
            time.sleep(random.uniform(C.CYCLE_GAP_MIN, C.CYCLE_GAP_MAX))

    log(f"run ended: {ok_cycles} batches trained "
        f"(~{ok_cycles * C.TRAIN_QTY:,} troops this run).")


if __name__ == "__main__":
    main()
