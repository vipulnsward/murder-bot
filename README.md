# Evony T1 Training Bot

Vision-based automation for **Evony: The King's Return** on BlueStacks (ADB), built to mass-train T1 ground troops (Warriors) toward 1,000,000,000, with automatic food top-up.

> Evony's ToS prohibits automation. Use only on accounts whose risk you accept.

## Why vision (not API/accessibility)
Evony is a Unity/IL2CPP app (`com.topgamesinc.evony.flexion`) — no accessibility tree, so Appium/Maestro can't read it. Everything here is **screenshot → OpenCV template match + Tesseract OCR → ADB tap**, which is deterministic, local, and free.

## Setup
```bash
python3.12 -m venv evony-venv && source evony-venv/bin/activate
pip install opencv-python-headless numpy       # + system `tesseract`
adb connect 127.0.0.1:5555                      # BlueStacks
```
Device assumed 1080x1920. Adjust coordinates/templates for other resolutions.

## Scripts
| File | Purpose |
|---|---|
| `train_to_1b.py` | **Autonomous orchestrator**: navigate → train T1 → auto food top-up when low → repeat until Own ≥ 1B. |
| `evony_bot.py` | Training-only loop (assumes game left on the Warriors screen). |
| `food_topup.py` | Standalone safe food top-up (open ~1B via 1M Food items). |
| `status.py` | Reads a run log + screen, prints batches/troops/Own/rate/food; saves `status_latest.png`. |
| `config.py` | Device, target, quantity, timings, coordinates. |
| `templates/` | Button crops for state detection & click-proof location. |
| `kb/` | Researched Evony reference (combat, resources, tasks, botting, project). |

## Verified flow
**Train cycle:** idle Warriors → set qty 269,228 → Train → Training Speedup → **Finish All** (uses speedup items) → verify Own +269,228 → repeat.
**Navigation:** city → Barracks `(500,800)` → radial Train `(179,679)` → T1 icon `(135,1237)`.
**Food top-up (safe):** top-bar food link → Resources panel (food-only) → scroll → match **"1M Food"** label (never Safe Food / never gem-Buy) → open modal → **Minimum → `+` to ~1000 → OCR hard-cap (≤2000) → green-check → Use** → confirms food +~1B.

## Safety gates (food)
- Only the green **Use** button of the **"1M Food"** row (owned) — never a 💎 gem/Buy button, never "1M Safe Food".
- Count is set from Minimum with `+` and **OCR-verified ≤ 2000 before Use** — the loop refuses to ever "open all".

## Measured
~3.3M troops/min, ~5s/cycle, +269,228/batch. The real ceiling is **speedup items + food**, not clicking — the bot converts stockpiles to troops; it can't manufacture them.

## Run
```bash
python train_to_1b.py                 # autonomous to 1B with auto food top-up (<100M)
python food_topup.py --target 1000 --cap 2000 --dry-run   # test food top-up (no Use)
python status.py run_1b.log           # status snapshot
```
