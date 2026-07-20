"""Evony game brain — a self-built catalog of screens.

Each recorded screen becomes: {label, text_signature, buttons (text+coords),
gems, ...}. The bot/LLM query it ("on this screen, where is 'Use'?") for
OCR-grounded, zoom-robust actions. Seed it from saved frames now; grow it by
exploring the live game later (record every new screen you land on).

record(path)          -> one screen record (dict)
build(paths, out)     -> writes out/catalog.json + copies screens/, returns catalog
label_of(record)      -> best screen label (template FSM > OCR text hint)
"""

import json
import os
import shutil

import cv2

import ocr_read
import screen_fsm


def record(path_or_img, name=None):
    img = cv2.imread(path_or_img) if isinstance(path_or_img, str) else path_or_img
    texts = ocr_read.read_all(img)
    # template FSM label first (fast, precise), fall back to OCR text hint
    label = screen_fsm.identify(img)
    if label == "unknown":
        label = ocr_read.screen_hint(img) or "unknown"
    buttons = [
        {"text": t, "x": c[0], "y": c[1], "conf": round(cf, 2)}
        for t, c, cf in texts if 1 <= len(t) <= 22 and cf >= 0.6
    ]
    signature = sorted({t.lower() for t, _, _ in texts if (" " in t or t.isalpha()) and len(t) <= 30})
    return {
        "file": name or (os.path.basename(path_or_img) if isinstance(path_or_img, str) else "live"),
        "label": label,
        "gems": ocr_read.read_gems(img),
        "n_text": len(texts),
        "text_signature": signature[:14],
        "buttons": buttons,
    }


def build(paths, out="game_brain"):
    os.makedirs(os.path.join(out, "screens"), exist_ok=True)
    catalog = []
    for p in paths:
        if not os.path.exists(p):
            continue
        rec = record(p)
        catalog.append(rec)
        try:
            shutil.copy(p, os.path.join(out, "screens", os.path.basename(p)))
        except Exception:
            pass
    # index: one representative + count per label
    by_label = {}
    for r in catalog:
        by_label.setdefault(r["label"], []).append(r["file"])
    index = {lbl: {"count": len(fs), "examples": fs[:3]} for lbl, fs in sorted(by_label.items())}
    json.dump({"screens": catalog, "index": index}, open(os.path.join(out, "catalog.json"), "w"), indent=2)
    return catalog, index


if __name__ == "__main__":
    import glob
    import sys
    paths = sys.argv[1:] or sorted(glob.glob("status_*.png"))
    cat, index = build(paths)
    print(f"recorded {len(cat)} screens from {len(paths)} frames")
    print("--- screens by label ---")
    for lbl, info in index.items():
        print(f"  {lbl:22s} x{info['count']}  e.g. {info['examples'][0]}")
    # show one useful example: buttons on a speedup modal
    for r in cat:
        if r["label"] == "speedup_modal":
            btns = [b["text"] for b in r["buttons"] if b["text"].lower() in ("use", "finish all")]
            print(f"--- speedup_modal '{r['file']}' key buttons: {btns} ---")
            break
