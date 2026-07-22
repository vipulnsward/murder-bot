"""Read the city top-bar HUD (resources, power, gems, VIP) from a frame.

Read-only: this never taps anything. It OCRs fixed regions of the 1080x1920 city
view. Regions were mapped from the live client; values are only trusted when the
frame is actually the city (see is_city), so the caller should keep the last good
read while the bot is inside menus.
"""

from __future__ import annotations

import json
import os
import re
import time

import nav
import ocr_read

# The mapper reaches clean-city states between probes and writes the HUD here; the
# control app's bridge reads it so the dashboard stays live even while mapping.
HUD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_brain", "live", "hud.json")

# Fixed HUD regions (x1, y1, x2, y2) on the 1080x1920 city view.
_RES_BOXES = {
    "food": (200, 8, 372, 62),
    "wood": (372, 8, 528, 62),
    "stone": (548, 8, 720, 62),
    "gold": (740, 8, 900, 62),
    "refined": (900, 8, 1046, 62),
}
_POWER_BOX = (180, 70, 430, 128)
_GEMS_BOX = (812, 78, 1060, 138)
_VIP_BOX = (222, 122, 340, 178)

_NUM = re.compile(r"([\d][\d,]*\.?\d*)\s*([KMB]?)", re.I)
_MULT = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def parse_amount(text):
    """'515.8M' -> 515800000, '7,780,719' -> 7780719, junk -> None."""
    if not text:
        return None
    m = _NUM.search(str(text).replace(" ", ""))
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", "")) * _MULT[m.group(2).upper()])
    except (ValueError, KeyError):
        return None


def _read_amount(img, box):
    best = None
    for txt, _c, conf in ocr_read.read_all(img, box=box, cache=True):
        val = parse_amount(txt)
        if val is not None and (best is None or conf > best[1]):
            best = (val, conf)
    return best[0] if best else None


def read_hud(img):
    """Return {resources{...}, power, gems, vip, ok} from a city frame, or ok=False
    (with nulls) when the frame is not the clean city view."""
    if img is None:
        return {"ok": False, "resources": {}, "power": None, "gems": None, "vip": None}
    if not nav.is_city(ocr_read.read_all(img, box=nav.CITY_BOX, cache=True)):
        return {"ok": False, "resources": {}, "power": None, "gems": None, "vip": None}
    resources = {name: _read_amount(img, box) for name, box in _RES_BOXES.items()}
    vip_txt = " ".join(t for t, _c, _cf in ocr_read.read_all(img, box=_VIP_BOX, cache=True))
    vip_m = re.search(r"(\d{1,3})", vip_txt.replace("VIP", "").replace("IP", ""))
    return {
        "ok": True,
        "resources": resources,
        "power": _read_amount(img, _POWER_BOX),
        "gems": _read_amount(img, _GEMS_BOX),
        "vip": int(vip_m.group(1)) if vip_m else None,
    }


def write_hud(hud, path=HUD_FILE):
    """Atomically persist a HUD read (stamped with ts) for the control app to serve."""
    if not hud or not hud.get("ok"):
        return False
    payload = dict(hud)
    payload["ts"] = time.time()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def read_hud_file(path=HUD_FILE, max_age_s=90.0):
    """Return the persisted HUD if present, ok, and newer than max_age_s, else None."""
    try:
        with open(path) as fh:
            hud = json.load(fh)
    except (OSError, ValueError):
        return None
    if hud.get("ok") and (time.time() - hud.get("ts", 0)) <= max_age_s:
        return hud
    return None


def _selftest():
    """Pure-logic self-test (no ADB): amount parsing, the city guard, HUD-file round-trip."""
    import tempfile
    ok = True

    amt_cases = [("515.8M", 515_800_000), ("7,780,719", 7_780_719), ("1.2B", 1_200_000_000),
                 ("300K", 300_000), ("42", 42), ("abc", None), ("", None), (None, None)]
    for raw, want in amt_cases:
        got = parse_amount(raw)
        if got != want:
            print(f"FAIL parse_amount({raw!r}) -> {got} (want {want})"); ok = False

    if read_hud(None).get("ok") is not False:
        print("FAIL read_hud(None) not ok=False"); ok = False

    orig = ocr_read.read_all
    dummy = object()
    try:
        ocr_read.read_all = lambda img, *a, **k: []                       # no city markers
        if read_hud(dummy).get("ok") is not False:
            print("FAIL read_hud(non-city) not ok=False"); ok = False
        ocr_read.read_all = lambda img, *a, **k: [("Mail", (987, 1685), 0.9),
                                                  ("515.8M", (300, 30), 0.95)]
        hud = read_hud(dummy)
        if hud.get("ok") is not True or hud.get("power") != 515_800_000:
            print(f"FAIL read_hud(city) -> {hud}"); ok = False
    finally:
        ocr_read.read_all = orig

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "hud.json")
        if write_hud({"ok": False}, p) is not False:
            print("FAIL write_hud(not ok) not False"); ok = False
        if write_hud({"ok": True, "power": 5, "resources": {}}, p) is not True:
            print("FAIL write_hud(ok) not True"); ok = False
        rd = read_hud_file(p, max_age_s=90)
        if not rd or rd.get("power") != 5:
            print(f"FAIL read_hud_file roundtrip -> {rd}"); ok = False
        if read_hud_file(p, max_age_s=-1) is not None:
            print("FAIL read_hud_file(stale) not None"); ok = False

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    import sys

    if "--live" in sys.argv:
        import cv2

        args = [a for a in sys.argv[1:] if a != "--live"]
        path = args[0] if args else "/tmp/hud_clean.jpg"
        hud = read_hud(cv2.imread(path))
        print(f"ok={hud['ok']} power={hud['power']} gems={hud['gems']} vip={hud['vip']}")
        for k, v in hud["resources"].items():
            print(f"  {k:8s} {v}")
    else:
        raise SystemExit(0 if _selftest() else 1)
