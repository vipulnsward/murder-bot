# Self-Healing Food Refill & Stability

How the trainer keeps running unattended for hours: it detects when it can't make
progress, opens more food by itself, navigates back to the barracks, and resumes —
without spending gems or opening all food.

## The out-of-food failure mode (and why it was subtle)

When food runs out, Evony does **not** show a clean "not enough food" popup. Instead:

- The training **quantity slider is forced to 1**, and the food count on the training
  screen turns **red** (e.g. `160`).
- The **Train** button gains a `00:00:01` timer overlay.

Because the button now looks different, the `train_btn_idle` template only matches ~0.62
(below the ~0.9 threshold), so `on_warriors_idle` is **False** and `train_one_batch`
returns **`NAV`**, not `NOFOOD`. The original loop only refilled on `NOFOOD`, so out-of-food
fell through to the silent recovery branch and looped to the 10-fail STOP with **zero
top-ups** — the log jumped straight from "batch N ok" to "STOP" with nothing in between.

**Fix:** trigger the refill on *sustained failure of any kind*, not on a specific return
code. After 3 (and again at 6) consecutive non-OK cycles, run the refill (out of food is by
far the most common cause). At 8, force-stop + relaunch the app as a last resort. Only STOP
at 10 if none of that helped.

## Reading the food modal (orange-on-beige OCR)

The quantity modal shows `N / OWN` (e.g. `2,984 / 124,657`) in **orange text on a beige
panel**. A grayscale Otsu threshold returns an empty string — the two tones are too close in
luminance. The reliable read is a **color mask**: keep pixels where `r-g > 45 && r-b > 60`
(saturated orange), invert, upscale 3x, then Tesseract with `--psm 7`. This turns an
intermittent `None` into a solid read every time.

Also require a freshly opened modal to read **> 1000** (it always starts at max = full owned
count) before trusting it — this rejects a stray small OCR value from the list screen behind
the modal, which would otherwise fool the "modal opened" check.

## The refill sequence (never opens all, never spends gems)

1. Dismiss any dialog (exit dialog → **Cancel** at 360,1134).
2. Back out to city, tap the food resource in the top bar (200,33) → Resources.
3. Scroll down until `food_1m_label` matches > 0.90 (the **1M Food** row with ~124k owned).
   Its green **Use** button is at label-top-left + (525, 135).
4. In the modal: tap **Minimum** (→ 1), then batch **+** taps on-device
   (`adb shell 'i=0; while [ $i -lt N ]; do input tap 900 1058; i=$((i+1)); done'`) — ~810 of
   1000 taps register, so ~6200 taps ≈ 5000 items ≈ 5B food. On-device looping is ~4s/1000 vs
   minutes of host round-trips.
5. Safety gate: the count must be `> 0` and `<= target*1.5`, else close (X at 1010,594) and
   abort. This is what guarantees it never taps **Use** at max (which would dump all ~124B
   food and make the city a plunder target — safe capacity is only 93).
6. Tap **Use**, confirm the "You received ~N in Food" banner, close.
7. Navigate back: tap the barracks building → the **View** (crossed-swords) radial option →
   Warriors training screen.

Gems are never touched: recovery is Cancel/Back only, and the gem-cost boxes (500K/5M/10K/50K,
priced in 💎) never match `food_1m_label`.

## Camera-zoom fragility & the app-refresh net

Templates like `barracks_bldg` are captured at one camera zoom. If the user pans/zooms and
leaves the game elsewhere, template navigation can fail. The catch-all is
`auto_refill.app_refresh()`: `am force-stop com.topgamesinc.evony.flexion` + `monkey ... 1`
relaunches to the **default** zoom where templates match again, then `to_warriors()` re-navs.
Wired in at 8 consecutive fails, before STOP.

## Monitoring

A 2-minute external loop (ScheduleWakeup) verifies the process is alive and progressing,
counts `auto-refill OK` events, refreshes the dashboard, and restarts / manually refills if
the self-heal ever fails. On "I'm using the game", it immediately kills the bot and stops the
loop so nothing taps while the human plays.

## Verified

Caught live in the log:

```
stuck (3 fails, r=NAV) — auto-refill #1 (likely out of food)
REFILL OK: opened ~5027 x 1M Food (~5.03B food)
auto-refill OK; resumed on Warriors
```

Food out → detected in 3 cycles → opened 5B → walked back to the barracks → resumed, fully
unattended.
