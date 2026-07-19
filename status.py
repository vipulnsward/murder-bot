import re
import subprocess
import sys
import datetime

import cv2

DEVICE = "127.0.0.1:5555"
LOG = sys.argv[1] if len(sys.argv) > 1 else "run_100b.log"
SHOT = "status_latest.png"
FOOD_BOX = (158, 10, 292, 62)
OWN_BOX = (330, 1070, 760, 1140)


def adb_screen(path):
    raw = subprocess.run(["adb", "-s", DEVICE, "exec-out", "screencap", "-p"],
                         capture_output=True).stdout
    with open(path, "wb") as f:
        f.write(raw)
    return cv2.imread(path)


def ocr(img, box, wl):
    x1, y1, x2, y2 = box
    c = img[y1:y2, x1:x2]
    g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cv2.imwrite("_s.png", t)
    return subprocess.run(["tesseract", "_s.png", "stdout", "--psm", "7",
                           "-c", f"tessedit_char_whitelist={wl}"],
                          capture_output=True, text=True).stdout.strip()


def parse_food(s):
    s = s.replace(" ", "").replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KMB])", s)
    if m:
        return float(m.group(1)) * {"B": 1e9, "M": 1e6, "K": 1e3}[m.group(2)], s
    m2 = re.search(r"(\d+(?:\.\d+)?)", s)
    if m2:
        v = float(m2.group(1))
        if 0 < v < 200:
            return v * 1e9, s
    return None, s


def read_log():
    rows = []
    batches = None
    topups = 0
    for l in open(LOG):
        mt = re.match(r"\[(\d\d:\d\d:\d\d)\]", l)
        mo = re.search(r"-> ([\d,]+)", l) or re.search(r"own=([\d,]+)", l)
        if mt and mo:
            rows.append((mt.group(1), int(mo.group(1).replace(",", ""))))
        mb = re.search(r"batches=(\d+)", l)
        if mb:
            batches = int(mb.group(1))
        if "top-up" in l or "topup:" in l or "opened" in l and "1M Food" in l:
            topups += 1
    if not rows:
        return None
    if batches is None:
        batches = sum(1 for l in open(LOG) if "cycle ok" in l)
    ts = lambda s: datetime.datetime.strptime(s, "%H:%M:%S")
    secs = (ts(rows[-1][0]) - ts(rows[0][0])).total_seconds() or 1
    return dict(n=batches, own=rows[-1][1], start=rows[0][1],
                troops=batches * 269228, secs=secs,
                rate=batches * 269228 / secs * 60, topups=topups)


def main():
    img = None
    food = None
    for _ in range(4):
        img = adb_screen(SHOT)
        f, raw = parse_food(ocr(img, FOOD_BOX, "0123456789.KMB"))
        if f and f > 1e6:
            food = f
            break
    lg = read_log()
    batches_left = int(food / 43_500_000) if food else None
    print("=== EVONY BOT STATUS ===")
    if lg:
        print(f"batches this run: {lg['n']}")
        print(f"troops built:     +{lg['troops']:,}")
        print(f"own now:          {lg['own']:,}  (to 1B: {1_000_000_000-lg['own']:,})")
        print(f"rate:             {lg['rate']:,.0f} troops/min ({lg['secs']/lg['n']:.1f}s/cycle)")
    food_str = f"{food/1e9:.2f}B" if food and food >= 1e9 else (f"{food/1e6:.0f}M" if food else "unread")
    print(f"food left:        {food_str}  (~{batches_left} batches)" if batches_left else f"food left: {food_str}")
    print(f"screenshot:       {SHOT}")


if __name__ == "__main__":
    main()
