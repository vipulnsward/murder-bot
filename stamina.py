"""stamina — top up Monarch stamina from owned Stamina items (learned live).

Flow (verified on the real client — fills 6,668 -> 9,999 in one call):
  King/Monarch avatar (top-left) -> profile -> the stamina bar's orange "+" ->
  "Use Item" popup (25/50/100 Stamina items) -> tap the biggest item's "Use (qty)" ->
  quantity selector -> DRAG the slider fully right to max the quantity -> "Use".
The green "Max" button doesn't register a tap; the slider drag does. GEM-SAFE: only
ever taps the green Use on OWNED items; never the "Buy … Gems / CHF" package banner.
Overfill past 9,999 is capped by the game's own max quantity.
"""

from __future__ import annotations

import subprocess
import time

import live_map
import nav
import ocr_read
import shared_capture

DEV = "127.0.0.1:5555"
AVATAR = (70, 60)          # King/Monarch avatar (top-left)
STAMINA_PLUS = (492, 1410)  # the orange "+" on the profile's stamina bar


def _cap():
    return shared_capture.grab_wait(DEV, timeout=6)


def _tap(x, y, d=1.9):
    subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", str(int(x)), str(int(y))])
    time.sleep(d)


def _back():
    subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"]); time.sleep(1.1)


def _tokens(img):
    return ocr_read.read_all(img) if img is not None else []


def _low(img):
    return " ".join(str(t).lower() for t, *_ in _tokens(img))


def add_stamina():
    """Top up stamina to the cap using owned Stamina items. Returns True if it used items.
    Gem-safe: never taps the purchase banner. Leaves the game on a clean city."""
    live_map.clear_popups(max_iters=6)
    _tap(*AVATAR)                                  # -> Monarch profile
    if "monarch" not in _low(_cap()):
        _back(); live_map.clear_popups(max_iters=3)
        return False
    _tap(*STAMINA_PLUS)                            # -> Use Item popup
    img = _cap()
    if "use item" not in _low(img) and "select an item" not in _low(img):
        _back(); live_map.clear_popups(max_iters=3)
        return False
    # Pick the biggest owned item: the "Use ( <qty> )" green buttons on the right; the
    # 100-Stamina row is the lowest one. Never the "Buy" package (that's left/red, no paren).
    uses = [(cx, cy) for t, (cx, cy), cf in _tokens(img)
            if cx > 760 and "use" in str(t).lower() and "(" in str(t)]
    if not uses:
        _back(); live_map.clear_popups(max_iters=3)
        return False
    uses.sort(key=lambda p: p[1])
    _tap(*uses[-1])                                # -> quantity selector
    time.sleep(0.6)
    # Set max quantity by dragging the slider fully right (the "Max" button doesn't
    # register a tap; the drag reliably maxes the qty = fills toward the 9,999 cap).
    subprocess.run(["adb", "-s", DEV, "shell", "input", "swipe", "290", "1010", "870", "1010", "400"])
    time.sleep(1.2)
    img = _cap()
    confirm = next(((cx, cy) for t, (cx, cy), cf in _tokens(img)
                    if str(t).strip().lower() == "use" and cy > 1200), None)
    if confirm:
        _tap(*confirm)                             # consume items
    # close the popups back to the city
    for _ in range(3):
        _back()
        if nav.is_city(ocr_read.read_all(_cap(), box=nav.CITY_BOX)):
            break
    live_map.clear_popups(max_iters=4)
    return True


def read_stamina():
    """Current stamina value from the profile ('X / cap'), or None. Opens+closes profile."""
    live_map.clear_popups(max_iters=4)
    _tap(*AVATAR)
    img = _cap()
    val = None
    for t, (cx, cy), cf in _tokens(img):
        ts = str(t).replace(" ", "")
        if "/" in ts and 1350 < cy < 1470 and any(c.isdigit() for c in ts):
            val = ts
    _back(); live_map.clear_popups(max_iters=3)
    return val


def _to_int(val):
    """Stamina value ('6.668/100' / '9,999') -> int (digits before the '/'), or None."""
    if not val:
        return None
    digits = "".join(c for c in str(val).split("/")[0] if c.isdigit())
    return int(digits) if digits else None


def current_stamina():
    """Current stamina as an int, or None."""
    return _to_int(read_stamina())


def top_up_if_low(threshold=5000):
    """Top up to the cap only when stamina is below `threshold`. Avoids opening the item
    menu (and wasting items past the 9,999 cap) every cycle. Returns True only if it
    actually topped up. Gem-safe."""
    cur = current_stamina()
    if cur is None or cur >= threshold:
        return False
    return add_stamina()


def _selftest():
    """Pure-logic self-test (no ADB): the stamina parser and the top-up gate."""
    ok = True

    int_cases = [("6.668/100", 6668), ("9,999", 9999), ("100 / 9999", 100),
                 ("3,331", 3331), (None, None), ("", None), ("/100", None), (4567, 4567)]
    for raw, want in int_cases:
        got = _to_int(raw)
        if got != want:
            print(f"FAIL _to_int({raw!r}) -> {got} (want {want})"); ok = False

    # top_up_if_low must NOT open the item menu at/above cap or on an unknown read,
    # and MUST top up once when below threshold (gem-safety = never waste items at cap).
    g = globals()
    orig_cur, orig_add = g["current_stamina"], g["add_stamina"]
    calls = []
    g["add_stamina"] = lambda: (calls.append(1) or True)
    try:
        g["current_stamina"] = lambda: 9999
        if top_up_if_low(5000) is not False or calls:
            print(f"FAIL: topped up at cap (calls={calls})"); ok = False
        g["current_stamina"] = lambda: None
        if top_up_if_low(5000) is not False or calls:
            print(f"FAIL: topped up on unknown read (calls={calls})"); ok = False
        g["current_stamina"] = lambda: 3000
        r = top_up_if_low(5000)
        if r is not True or len(calls) != 1:
            print(f"FAIL: did not top up when low (r={r}, calls={calls})"); ok = False
    finally:
        g["current_stamina"], g["add_stamina"] = orig_cur, orig_add

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    import sys

    if "--live" in sys.argv:
        print("stamina before:", read_stamina())
        print("add_stamina ->", add_stamina())
        print("stamina after:", read_stamina())
    else:
        raise SystemExit(0 if _selftest() else 1)
