# OCR module + Game Brain

## ocr_read.py — local OCR (RapidOCR / PaddleOCR via ONNX), ~0.4s/frame
Fixes the fragile bits of template+Tesseract:
- `read_gems()` / `read_number()` — reads counts Tesseract missed (gems 7,794,779 @ conf 1.0).
- `find_button(img, "Use")` — whole-word text match -> tap center. **Zoom-robust** grounding for
  text-labeled controls (no template scale problem, see kb/12). e.g. Use @ (791,1838).
- `screen_hint()` — text-based screen guess (disconnect / speedup_modal / exit_dialog) to
  corroborate the template FSM.

## game_brain.py — self-built catalog of screens
`record(frame)` -> {label, gems, text_signature, buttons[text,x,y,conf]}. `build(frames)` writes
`game_brain/catalog.json` + copies screens. Seeded from 28 recorded frames -> 8 screen types
(city, barracks_radial, disconnect, speedup_modal, training_idle, resources, exit_dialog, unknown),
each with OCR-grounded button coordinates. The bot/LLM query the brain: "on screen X, where is
button Y?" -> coords, instead of hardcoded taps.

Grow it by exploring the live game: land on a screen -> record() -> append. Label unknowns with the
LLM (kb/20) and distill into templates/rules. Raw screenshots are gitignored; catalog.json is the
durable brain.

## Why this improves the bot
1. Reliable numbers (own/food/gems) regardless of font/background.
2. Zoom-robust taps for text buttons -> fixes the camera/banner fragility that blocked nav.
3. A structured screen map that both the deterministic layer and the LLM fallback read from.
