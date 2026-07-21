"""Local OCR (RapidOCR / PaddleOCR models via ONNX) — text + boxes.

Improves the bot three ways (see kb/21):
  - robust number reads (troops/food/gems) where Tesseract misses,
  - text-based button grounding (find "Use"/"Train" -> tap its box) — zoom-robust,
  - text-based screen hints.

Fast (~0.4s full frame; crop a region to go faster). Lazy-loads the engine.
"""

import re
from hashlib import blake2b

import cv2

USE_ANGLE_CLS = False
DET_LIMIT_SIDE_LEN = 640
NUMBER_UPSCALE = 2

_ENGINE = None
_REC_ENGINE = None
_CACHE = {}


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR(use_angle_cls=USE_ANGLE_CLS,
                           det_limit_side_len=DET_LIMIT_SIDE_LEN,
                           det_model_path=None)
    return _ENGINE


def _rec_engine():
    global _REC_ENGINE
    if _REC_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _REC_ENGINE = RapidOCR(use_angle_cls=USE_ANGLE_CLS, use_text_det=False)
    return _REC_ENGINE


def _crop(img, box):
    if isinstance(img, str):
        img = cv2.imread(img)
    ox, oy = 0, 0
    if box:
        x1, y1, x2, y2 = box
        ox, oy = x1, y1
        img = img[y1:y2, x1:x2]
    return img, ox, oy


def _cache_key(img, ox, oy):
    pixels = img if img.flags.c_contiguous else img.copy()
    return (blake2b(pixels.data, digest_size=16).digest(), pixels.shape,
            pixels.dtype.str, ox, oy)


def clear_cache():
    """Clear cached OCR reads."""
    _CACHE.clear()


def read_all(img, box=None, cache=False):
    """Return [(text, (cx, cy), conf)]. img: BGR ndarray or path. box: optional
    (x1,y1,x2,y2) crop; centers are returned in FULL-image coordinates.
    Set cache=True to reuse results for identical crop pixels."""
    img, ox, oy = _crop(img, box)
    key = _cache_key(img, ox, oy) if cache else None
    if key in _CACHE:
        return list(_CACHE[key])
    res, _ = _engine()(img)
    out = []
    for pts, txt, conf in (res or []):
        cx = int((pts[0][0] + pts[2][0]) / 2) + ox
        cy = int((pts[0][1] + pts[2][1]) / 2) + oy
        out.append((txt, (cx, cy), float(conf)))
    if cache:
        _CACHE[key] = tuple(out)
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


def read_number_fast(img, box=None, pick="largest", upscale=NUMBER_UPSCALE):
    """Read one number from a tight crop without running text detection."""
    crop, _, _ = _crop(img, box)
    gray = (crop if crop.ndim == 2 else
            cv2.cvtColor(crop, cv2.COLOR_BGRA2GRAY if crop.shape[2] == 4
                         else cv2.COLOR_BGR2GRAY))
    if upscale and upscale != 1:
        gray = cv2.resize(gray, None, fx=upscale, fy=upscale,
                          interpolation=cv2.INTER_CUBIC)
    res, _ = _rec_engine()(gray)
    if res:
        text = res[0][1].strip()
        if re.fullmatch(r"[\d,.\s]+", text):
            number = _to_int(text)
            if number is not None:
                return number
    return read_number(img, box, pick)


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
    from time import perf_counter

    test_frame = ("/private/tmp/claude-501/-Users-sward-work-scratch/"
                  "c2e71639-9f51-4ec5-b5ef-685684771afc/scratchpad/holo_test.png")
    number_box = (828, 75, 1015, 128)
    image = cv2.imread(test_frame)

    read_all(image, number_box)
    read_number_fast(image, number_box)

    started = perf_counter()
    full = read_all(image)
    full_ms = (perf_counter() - started) * 1000

    started = perf_counter()
    number = read_number(image, number_box)
    number_ms = (perf_counter() - started) * 1000

    started = perf_counter()
    fast_number = read_number_fast(image, number_box)
    fast_number_ms = (perf_counter() - started) * 1000

    clear_cache()
    started = perf_counter()
    cached_first = read_all(image, number_box, cache=True)
    cache_first_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    cached_second = read_all(image, number_box, cache=True)
    cache_second_ms = (perf_counter() - started) * 1000

    texts = " ".join(text.lower() for text, _, _ in full)
    ok = (image is not None and number == fast_number == 7794429 and
          cached_first == cached_second and cache_second_ms < cache_first_ms / 4 and
          all(text in texts for text in ("disconnected", "quit", "restart")))
    print(f"full read_all: {full_ms:.1f} ms, {len(full)} boxes")
    print(f"read_number: {number_ms:.1f} ms, value={number}")
    print(f"read_number_fast: {fast_number_ms:.1f} ms, value={fast_number}")
    print(f"cache: first={cache_first_ms:.1f} ms, second={cache_second_ms:.3f} ms")
    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
