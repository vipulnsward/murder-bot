# Stuck-Batch Glitch & Instant-Finish Recovery

A second, rarer stall mode discovered during the T2 500M run — distinct from a genuine
out-of-food, and requiring a completely different fix. Getting these two confused wastes
either food (refilling when full) or time (app-refreshing a batch that won't clear).

## Normal training: batches are Finish-All'd with speedup *items*

Each training batch = `TRAIN_QTY` (271,766) Conscripts. At this barracks level a batch's
**natural** timer is ~**2d 16h**. The bot never waits that out — right after queueing it
applies **training speedup items** (Finish-All) to complete the batch in ~6s. The account
holds a huge speedup stock (~43k×10min + 49k×15min + 35k×30min + hours/days tiers ≈ 1,500+
days of reduction), so this is effectively free and sustains hundreds of batches per run.

## The glitch: a batch stranded at its full natural timer

If a cycle is interrupted at the wrong moment — a camera/zoom drift, an app hiccup, a nav
break — a batch can end up **queued but never sped up**. The barracks is then **busy** for
the full ~2d16h, so:

- `train_btn_idle` reads low (the barracks isn't idle — it's training), so `on_warriors_idle`
  is False and the loop counts failures.
- The failure path assumes the usual cause (out of food) and spins into refill attempts.
- **`app_refresh()` does not help** — force-stop + relaunch keeps the in-progress training
  queue; the batch is still stuck at 2d16h afterward.

Observed live at 14:13 on the 500M run: the loop logged repeated "out of food / auto-refill"
while food was actually **2.8B** and stone **32.6B**, and the barracks showed
`Conscripts · 2d 15:5x` counting down naturally.

## Telling the two stalls apart — read the TOP-BAR FOOD number

This is the whole diagnosis. Screencap and look at the top-bar food:

| Signal | Genuine out-of-food | Stuck-batch glitch |
|--------|--------------------|--------------------|
| Top-bar food | tiny (`130`, `4.3M`, red on train screen) | healthy (`>300M`, e.g. `2.8B`) |
| Barracks banner | idle / Train button (timer overlay) | multi-day `Conscripts · Nd NN:NN` |
| `train_btn_idle` | low | low |
| Correct fix | let the bot auto-refill (self-heals) | **Instant Finish** the batch |
| `app_refresh` fixes it? | n/a (refill does) | **No** |

## Recovery: Instant Finish (gems), not item-speedup

The item-speedup modal misbehaved on the stranded batch — tapping **Use** consumed items but
the displayed **Remaining Time did not drop**. The reliable clear is the barracks radial's
**Instant Finish** (gems):

1. `pkill` the bot so it stops taping.
2. Tap the barracks banner (`490,1290`) to open the radial menu.
3. Tap **Instant Finish** (`215,1180`) — cost scales with remaining time; a 2d16h batch was
   **~4,287 gems** (0.05% of an 8.19M-gem balance — trivial).
4. Confirm **Okay** (`540,1065`).
5. Verify the barracks is idle: `barracks_bldg` template jumps to **>0.9** (banner gone).
6. Relaunch: `nohup python train_to_1b.py --target <N> > run.log 2>&1 &`.

After the batch lands, the relaunched bot navigates from the clean city view (barracks now
matches at ~0.96) back into training and resumes ~6s/batch.

## Verified

Cleared live on the 500M run: Instant Finish for 4,287 gems (balance 8,194,180 → 8,189,894),
`barracks_bldg` 0.14 → **0.964** (idle), relaunch → `batch 1 ok … batch 11 ok` in ~90s. The
run then completed to **501,481,135** with no recurrence.

## Automation gap (open)

The bot cannot self-clear a stranded batch — it needs the gem Instant Finish, which the loop
never issues. Today the 2-minute monitor catches it (distinguish by top-bar food, then
Instant Finish). A permanent fix would detect "busy barracks + healthy food + multi-day
timer" and either re-apply speedups to that queue or issue the Instant Finish automatically.
