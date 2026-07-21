"""perception — shared visual primitives for Evony [LIVE-CAPTURE] tasks.

Images are BGR numpy arrays in device coordinates. OCR and Holo are lazy and
fail closed so a missing local model never interrupts the bot.
"""

from __future__ import annotations

import os
import re
import tempfile

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def red_dot(img, box, min_frac=0.015):
    """True when notification-red pixels exceed `min_frac` inside `box`."""
    if img is None or img.ndim != 3 or img.shape[2] < 3:
        return False
    x1, y1, x2, y2 = box
    x1, x2 = max(0, x1), min(img.shape[1], x2)
    y1, y2 = max(0, y1), min(img.shape[0], y2)
    crop = img[y1:y2, x1:x2]
    if not crop.size:
        return False
    blue, green, red = cv2.split(crop[:, :, :3])
    return float(np.mean((red > 150) & (green < 90) & (blue < 90))) > min_frac


def _template(template):
    if isinstance(template, np.ndarray):
        return template
    path = os.fspath(template)
    if not os.path.exists(path):
        path = os.path.join(HERE, "templates", path if path.endswith(".png") else path + ".png")
    return cv2.imread(path)


def _matches(img, template):
    template = _template(template)
    if img is None or template is None or img.ndim != template.ndim:
        return None, None
    height, width = template.shape[:2]
    if img.shape[0] < height or img.shape[1] < width:
        return None, None
    return cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED), (width, height)


def find(img, template, threshold=0.85):
    """Return the center of the strongest template match, or None."""
    scores, size = _matches(img, template)
    if scores is None:
        return None
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    width, height = size
    return (x + width // 2, y + height // 2) if score >= threshold else None


def find_all(img, template, threshold=0.85, max_hits=30, nms_dist=20):
    """Return score-sorted template centers with distance-based suppression."""
    scores, size = _matches(img, template)
    if scores is None or max_hits <= 0:
        return []
    width, height = size
    ys, xs = np.where(scores >= threshold)
    candidates = sorted(((float(scores[y, x]), int(x + width // 2), int(y + height // 2))
                         for y, x in zip(ys, xs)), reverse=True)
    hits = []
    for _, x, y in candidates:
        if all((x - hx) ** 2 + (y - hy) ** 2 > nms_dist ** 2 for hx, hy in hits):
            hits.append((x, y))
            if len(hits) == max_hits:
                break
    return hits


def read_text(img, box=None):
    """Return OCR text for an image or crop; return "" on failure."""
    try:
        import ocr_read
        return " ".join(text for text, _, _ in ocr_read.read_all(img, box))
    except Exception:
        return ""


def read_number(img, box=None):
    """Return the first OCR integer with separators removed, or None."""
    match = re.search(r"\d[\d, ]*", read_text(img, box))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group())
    return int(digits) if digits else None


def ground(img, instruction):
    """Holo grounding fallback; return a device center or None on failure."""
    try:
        import holo_vision
        if isinstance(img, (str, os.PathLike)):
            return holo_vision.ground(img, instruction)
        with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
            if not cv2.imwrite(temporary.name, img):
                return None
            return holo_vision.ground(temporary.name, instruction)
    except Exception:
        return None


def describe(img, question):
    """Return Holo's description, or "" on failure."""
    try:
        import holo_vision
        if isinstance(img, (str, os.PathLike)):
            return holo_vision.describe(img, question)
        with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
            if not cv2.imwrite(temporary.name, img):
                return ""
            return holo_vision.describe(temporary.name, question)
    except Exception:
        return ""


if __name__ == "__main__":
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch

    ok = True

    def check(name, passed, detail=""):
        global ok
        print(f"{name}: {'PASS' if passed else 'FAIL'}{detail}")
        ok &= passed

    canvas = np.zeros((1920, 1080, 3), np.uint8)
    box = (100, 200, 200, 300)
    canvas[210:230, 110:130] = (0, 0, 255)
    check("red_dot painted", red_dot(canvas, box))
    check("red_dot empty", not red_dot(canvas, (300, 300, 400, 400)))

    rng = np.random.default_rng(7)
    template = rng.integers(20, 256, (13, 15, 3), dtype=np.uint8)
    one = np.zeros((180, 240, 3), np.uint8)
    one_xy = (71, 83)
    one[one_xy[1]:one_xy[1] + 13, one_xy[0]:one_xy[0] + 15] = template
    expected_one = (one_xy[0] + 7, one_xy[1] + 6)
    found = find(one, template, threshold=0.99)
    check("find", found is not None and np.linalg.norm(np.subtract(found, expected_one)) <= 2,
          f" found={found}")

    many = np.zeros((220, 280, 3), np.uint8)
    locations = [(20, 25), (130, 70), (210, 170)]
    expected_many = [(x + 7, y + 6) for x, y in locations]
    for x, y in locations:
        many[y:y + 13, x:x + 15] = template
    found_many = find_all(many, template, threshold=0.99)
    all_found = len(found_many) == 3 and all(
        any(np.linalg.norm(np.subtract(hit, expected)) <= 2 for hit in found_many)
        for expected in expected_many
    ) and all(
        np.linalg.norm(np.subtract(first, second)) > 20
        for index, first in enumerate(found_many) for second in found_many[index + 1:]
    )
    check("find_all", all_found, f" found={found_many}")

    blank = np.zeros((80, 240, 3), np.uint8)
    check("read_number blank", read_number(blank) is None)

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("model unavailable")

    fake_holo = SimpleNamespace(ground=unavailable, describe=unavailable)
    with patch.dict(sys.modules, {"holo_vision": fake_holo}):
        check("ground fallback", ground(blank, "anything") is None)
        check("describe fallback", describe(blank, "anything") == "")

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
