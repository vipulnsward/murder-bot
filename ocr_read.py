"""Local OCR (RapidOCR / PaddleOCR models via ONNX) — text + boxes.

Improves the bot three ways (see kb/21):
  - robust number reads (troops/food/gems) where Tesseract misses,
  - text-based button grounding (find "Use"/"Train" -> tap its box) — zoom-robust,
  - text-based screen hints.

Fast (~0.4s full frame; crop a region to go faster). Lazy-loads the engine.
"""

import re

import cv2

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


def read_all(img, box=None):
    """Return [(text, (cx, cy), conf)]. img: BGR ndarray or path. box: optional
    (x1,y1,x2,y2) crop; centers are returned in FULL-image coordinates."""
    if isinstance(img, str):
        img = cv2.imread(img)
    ox, oy = 0, 0
    if box:
        x1, y1, x2, y2 = box
        ox, oy = x1, y1
        img = img[y1:y2, x1:x2]
    res, _ = _engine()(img)
    out = []
    for pts, txt, conf in (res or []):
        cx = int((pts[0][0] + pts[2][0]) / 2) + ox
        cy = int((pts[0][1] + pts[2][1]) / 2) + oy
        out.append((txt, (cx, cy), float(conf)))
    return out


def find_button(img, label, box=None, min_conf=0.6):
    """Center (x, y) of the text region whose text matches `label` as a whole word
    (case-insensitive), or None. Whole-word avoids 'use' matching 'because'.
    Zoom-robust alternative to template matching for text-labeled controls."""
    pat = re.compile(r"\b" + re.escape(label.lower()) + r"\b")
    best = None
    for txt, c, conf in read_all(img, box):
        if conf >= min_conf and pat.search(txt.lower()):
            if best is None or conf > best[1]:
                best = (c, conf)
    return best[0] if best else None


def _to_int(s):
    d = re.sub(r"[^0-9]", "", s)
    return int(d) if d else None


def read_number(img, box=None, pick="largest"):
    """Read the most prominent integer in a region (commas stripped)."""
    nums = []
    for txt, c, conf in read_all(img, box):
        n = _to_int(txt)
        if n is not None and re.fullmatch(r"[\d,]+", txt.strip()):
            nums.append((n, c, conf))
    if not nums:
        return None
    if pick == "largest":
        return max(nums, key=lambda t: t[0])[0]
    return nums[0][0]


def read_gems(img):
    """Gem count from the top-right (informational; RapidOCR reads it reliably where
    Tesseract failed). Full-frame read, then pick the big number in the top-right."""
    for txt, (cx, cy), conf in read_all(img):
        if cx > 820 and cy < 140 and re.fullmatch(r"[\d,]{5,}", txt.strip()):
            return _to_int(txt)
    return None


def screen_hint(img):
    """Cheap text-based screen guess to corroborate the template FSM."""
    texts = " ".join(t.lower() for t, _, _ in read_all(img)).lower()
    if "disconnected" in texts or "someone login" in texts:
        return "disconnect"
    if "finish all" in texts and "use" in texts:
        return "speedup_modal"
    if "exit the game" in texts:
        return "exit_dialog"
    return None


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:] or ["status_cleared.png", "status_r2.png", "status_speed.png"]:
        import os
        if not os.path.exists(f):
            continue
        print(f"{f}: gems={read_gems(f)}  hint={screen_hint(f)}  "
              f"use_btn={find_button(f, 'use')}  finish={find_button(f, 'finish all')}")
