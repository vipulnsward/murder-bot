---
title: "Evony T1 Training Bot — Project State"
tags: [evony, evony-bot, project, adb, opencv, reference]
type: project
source: "this session"
---

# Evony T1 Training Bot — Project State

## Goal
Reach **1,000,000,000 T1 ground troops (Warriors)** by automating the training loop on local BlueStacks.

## Environment
- BlueStacks Evony (`com.topgamesinc.evony.flexion`), 1080x1920, ADB at `127.0.0.1:5555`.
- Python 3.12 venv (`evony-venv`) with `opencv-python-headless`, `numpy`; system `tesseract`.

## Files (scratchpad)
- `evony_bot.py` — main loop (state machine).
- `config.py` — device, target, TRAIN_QTY=269228, timings, coordinates, OCR regions.
- `templates/` — matched button crops: `warriors_title`, `warrior_t1_icon`, `train_btn_idle`, `speedup_btn`, `instant_train_btn`, `slider_minus/plus`, `modal_speedup_title`, `finish_all_btn`, `use_btn`.
- `status.py` — reads log + OCRs food, saves `status_latest.png`.

## Verified flow (one cycle)
1. Confirm idle Warriors screen (`train_btn_idle` template).
2. If qty != 269228: tap T1 icon -> tap qty field -> clear (8x DEL) -> `input text 269228` -> OK.
3. Tap **Train** (green) -> batch starts (2d 09:59).
4. Tap **Training Speedup** -> speedup modal.
5. Tap **Finish All** -> batch completes instantly using speedup items.
6. Verify return to idle + read Own; stop at 1B.

## Measured performance
- ~**3.3M troops/min**, ~**4.8-5.5s/cycle**, +269,228 per batch.
- Session progress: Own **685,654,504 -> ~766M+** (tens of millions trained, every batch OCR-verified).
- Stability: transient skips (popups / mid-transition) auto-recovered via back-press + consecutive-pause guard.

## The real bottleneck (not clicking)
- Each batch = ~43.5M food + one **Finish All** (~2d10h of speedup items).
- To 1B from ~766M ≈ ~870 batches ≈ ~1.6h of bot time IF food + speedups are stockpiled.
- **Speedup inventory** and **food** are the true gates; automation is solved.

## Next features (to build)
1. **Auto food top-up** — when food < one batch, open N x 1B food items from the bag, then resume ("top up 1B at a time"). See 02-resources-items.md.
2. **Watchdog / self-healing** — ADB reconnect, BlueStacks restart, generic popup-closer, screenshot-diff stuck detector, structured logs.
3. **LLM fallback (self-improving)** — on unknown state, call a local vision model (moondream -> UI-TARS/Qwen2.5-VL); save new template+action so it's deterministic next time.
