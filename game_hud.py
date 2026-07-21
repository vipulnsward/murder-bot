"""Read the city top-bar HUD (resources, power, gems, VIP) from a frame.

Read-only: this never taps anything. It OCRs fixed regions of the 1080x1920 city
view. Regions were mapped from the live client; values are only trusted when the
frame is actually the city (see is_city), so the caller should keep the last good
read while the bot is inside menus.
"""

from __future__ import annotations

import re

import nav
import ocr_read

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
        return int(float(m.group(1).replace(",", "")) * _MULT[m.group(2).upper()])
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


if __name__ == "__main__":
    import sys

    import cv2

    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hud_clean.jpg"
    hud = read_hud(cv2.imread(path))
    print(f"ok={hud['ok']} power={hud['power']} gems={hud['gems']} vip={hud['vip']}")
    for k, v in hud["resources"].items():
        print(f"  {k:8s} {v}")
