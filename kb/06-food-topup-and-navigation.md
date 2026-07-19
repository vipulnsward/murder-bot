---
title: "Evony Bot — Safe Food Top-Up & Navigation (verified)"
tags: [evony, evony-bot, automation, food, navigation, adb, reference]
type: project
source: "verified live on BlueStacks this session (1080x1920)"
---

# Evony Bot — Safe Food Top-Up & Navigation

All coordinates verified on BlueStacks at **1080x1920**.

## Navigation: reach the T1 Warriors training screen
1. City view → tap **Barracks** building `(500, 800)` → radial menu opens.
2. Match template `radial_train` (score ~0.99) → tap radial **Train** `(179, 679)`.
3. Tap **T1 Warriors** icon `(135, 1237)`.
4. Verify: `warriors_title` and `train_btn_idle` both match (== on idle T1 screen).

## The capacity popup (critical — the stable training flow)
- When idle, the slider defaults to its **food-affordable max (e.g. 271766)**, which is **above the actual training capacity (269228)**. The game **resets the slider to that max after every batch** (the value does NOT persist).
- So tapping **Train** pops: *"Training failed. You have exceeded the training capacity... adjusted to the capacity of 269228, continue?"* with **Cancel / Confirm**.
- **STABLE FLOW (matches the player's manual flow): tap Train → wait ~0.7s for the popup → tap Confirm `(714,1134)` → batch starts at 269228 → Training Speedup → Finish All.** Do NOT bother typing 269228 (fragile, and the game resets it anyway) — just Confirm the popup every cycle.
- **Confirm button = `(714, 1134)`** (green, right). Cancel = `(360,1134)` (never spends anything). Template `cap_popup` detects it.
- Race fix: screenshot for the popup only AFTER a ~0.7s wait (it animates in), or the Confirm is missed and the batch never starts (looks like a false "food out").

## Never navigate on a false food-out
- A failed Train (no batch start) previously triggered the food top-up **navigation**, which blind-tapped into the radial and hit **"Instant Finish" (gems)** → a "spend 3910 gems?" popup. Fix: on NOFOOD, **read the top-bar food first**; only navigate to top-up if food is genuinely `< 500M`. Otherwise retry in place. This keeps the bot on the training screen (no gem risk).
- In the idle barracks radial, Train is safe at `(179,679)`; in the BUSY radial that same spot is **Instant Finish (gems)** — never blind-tap it.

## Train one batch (verified)
- Set qty **269,228** (tap qty field `(880,1588)` → 8×DEL → `input text 269228` → OK `(975,1852)`); skip if already 269,228.
- Tap **Train** (locate `train_btn_idle`) → wait for `speedup_btn` (busy).
- Tap **Training Speedup** → wait `modal_speedup_title` → tap **Finish All** (`finish_all_btn`).
- Verify return to `train_btn_idle`; Own increases by exactly **269,228**.
- Each batch costs ~43.1M food and one Finish All (~2d10h of speedup items).

## Safe food top-up ("open 1B food only")
**Entry (safe = top bar):** city view → tap **red food amount** in top bar `(200, 33)` → opens the **Resources** panel scoped to **food only** (no other resource can be opened here).

**Find the right item:** swipe up `(540,1400)->(540,500)` once → the **"1M Food"** row appears.
- Match template `food_1m_label` to anchor the row → Use button = `(label_x+550, label_y+80)`.
- CRITICAL: this uniquely identifies **"1M Food"** — NOT **"1M Safe Food"** (a different item) and NOT the **💎 gem "Buy"** boxes (5K/10K/50K/500K/5M show gem prices — tapping = spends gems).
- Owned items show a **green "Use (count)"** button; verify green before tapping.

**Set the amount (the slider is coarse — ~286 items/pixel — so it can't hit a precise value by dragging):**
- Tap the **Minimum button** (bottom-left green button of the modal) at `(311, 1328)` — NOT the slider `−` at `(162,1058)`. The `−` only steps −1, so from max (≈157k) it can never reach 1. After tapping Minimum the slider **animates**; retry-read the count until it settles at ≤5 (drag handle fully left `swipe 840,1058→150,1058` as fallback).
- Tap `+` `(900,1058)` up to the target (**~2000 = ~2B**; each item = 1M food). **Use host-side ADB taps with ~20ms pacing** — reliable (only ~1% dropped, e.g. 1985/1999). On-device loops drop ~20%. Don't fire faster than ~20ms/tap (drops + looks bot-like).
- **HARD SAFETY GATE:** OCR the count (region `300,1150,770,1205`, read number before "/"). Only press **Use** if `count ≤ 2000` (cap). Never press Use while the slider is at max — that would open ALL food (e.g. 158,492 → 158B) into lootable/upkeep-eaten storage. **Never open all.**
- Verify the modal **Use** button `(765,1329)` is green by sampling OFF-center pixels `(690,1305),(840,1305),(690,1352),(840,1352)` (center is white "Use" text → false negatives).
- Press **Use** → toast "You received N,000,000 in Food"; item count drops by exactly N; top-bar food rises ~1B.
- Close with red **X** `(1010, 594)`.

**Verified result:** opened 995 × 1M Food → food 9.5M → 1B; "1M Food" count 158,492 → 157,497 (−995 exactly). No other item touched.

## Orchestrator (train_to_1b.py)
Loop: ensure Warriors idle → if `Own ≥ 1B` stop → read top-bar food; if **< 100M** proactively top up (before stall) → else train one batch. On `NOFOOD` (train won't start) also tops up. Navigates back via city→barracks→train after each top-up.

## Key numbers
- ~3.3M troops/min, ~5s/cycle. To 1B from ~796M ≈ ~757 batches.
- Real gate = **food + speedup items**, not clicking. Food auto-refills ~1B (~23 batches) per top-up; speedup inventory is the ultimate ceiling.
