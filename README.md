# Evony Troop Trainer

Vision-based automation that trains troops in **Evony: The King's Return** running on
a local Android emulator (BlueStacks). It drives the game entirely through ADB input
(taps/swipes) and reads the screen with OpenCV template matching + Tesseract OCR — no
game API, no memory hacks, no accessibility tree (Evony is a Unity/IL2CPP app, so the
screen is the only interface).

It ran a real campaign from **685.7M → 1.0B+ T1 Warriors** unattended, and now targets
1.5B T1 then T2 ground.

> Evony's ToS prohibits automation. Use only on a self-owned account whose risk you accept.

---

## What's in here

| File | What it does |
|------|--------------|
| `train_to_1b.py` | Main loop: train a full batch, Finish-All with speedups, repeat until the target count. |
| `auto_refill.py` | Self-healing food refill: navigate to Resources, open ~5B food (bounded), walk back to the barracks. Also `app_refresh()` (force-stop + relaunch) as a last-resort recovery. |
| `recovery_handler.py` | Recovery playbook — dismisses event popups, re-navigates to the barracks, optional vision-LLM fallback. |
| `food_topup.py` | Opens food resource items in controlled amounts (never "open all"). |
| `status.py` / `config.py` | Shared OCR/state helpers and tuning constants. |
| `gen_dashboard.py` | Renders `evony_status.html` — a branded live status dashboard (progress to target, rate, ETA, screenshot). |
| `live_stream.py` | MJPEG live stream of the emulator screen on `:8088` + a `/stats` JSON endpoint (re-OCRs the count every 10s). |
| `hls_stream.sh` | H.264 HLS variant of the stream (`adb screenrecord \| ffmpeg`) for smoother HD over a tunnel. |
| `templates/` | Click-proof PNG templates for each UI element (train button, speedup button, popups, barracks, etc.). |
| `kb/` | Researched knowledge base on Evony combat, resources, tasks, botting, buffs, self-healing. |

---

## Requirements

- **BlueStacks** (or any Android emulator) with ADB debugging enabled, Evony installed and logged in.
- **ADB** reachable at `127.0.0.1:5555` (BlueStacks default). Adjust `DEVICE` if yours differs.
- **Python 3.12** with `opencv-python-headless` and `numpy`.
- **Tesseract OCR** (`brew install tesseract`) for reading troop counts / food.
- Streaming extras (optional): **cloudflared** (public URL) and **ffmpeg** (HLS).

```bash
python3.12 -m venv evony-venv
source evony-venv/bin/activate
pip install opencv-python-headless numpy pytesseract
adb connect 127.0.0.1:5555      # confirm the emulator is attached
adb devices
```

---

## Usage

### 1. Train troops

Open the game to the **Warriors (T1) barracks training screen** first, then:

```bash
source evony-venv/bin/activate
python train_to_1b.py
```

It loops: tap **Train** → **Confirm** the capacity popup → wait for the batch →
**Finish All** with speedups → back to idle → repeat, until `Own >= TARGET_OWN`.
Progress is logged with a running count and ETA.

**Tuning** (top of `train_to_1b.py`):

```python
DEVICE     = "127.0.0.1:5555"   # ADB target
TARGET_OWN = 1_500_000_000      # stop when you own this many of the trained troop
TRAIN_QTY  = 271766             # slider max the game resets to each batch
```

> **Why we Confirm instead of typing a number:** the game resets the slider to its max
> (271,766) every batch, which exceeds current training capacity (269,228), so tapping
> Train pops a "capacity exceeded → adjust to 269,228?" dialog. Tapping **Confirm** is
> faster and far more reliable than typing into the quantity field. This is the single
> biggest stability win in the project.

### 2. Live dashboard (static HTML)

```bash
python gen_dashboard.py        # writes evony_status.html with a fresh screenshot + stats
```

Open `evony_status.html` in a browser, or regenerate it on a loop for a live view.

### 3. Live stream + stats API

```bash
python live_stream.py          # serves on http://localhost:8088
```

- `/`       — combined dashboard page (live MJPEG video + auto-refreshing stats).
- `/stream` — raw MJPEG (`multipart/x-mixed-replace`).
- `/stats`  — JSON: `{own, food, running, pct, to_go, ...}`, re-OCR'd every 10s.

Expose it publicly with Cloudflare (QUIC/UDP is often blocked, so force http2):

```bash
cloudflared tunnel --url http://localhost:8088 --protocol http2
```

### 4. Smooth HD stream (HLS)

For higher quality than MJPEG, stream H.264 via screenrecord:

```bash
./hls_stream.sh                # writes hls/stream.m3u8 + segments
```

Serve the `hls/` directory and point an `<video>`/hls.js player (or the same tunnel) at it.

### 5. Food top-up

`food_topup.py` opens resource food items in **bounded amounts** (hard OCR cap, so it
never "opens all food"). Call it when the trainer reports low food, or run it standalone.

---

## How it works

1. **Capture** — `adb exec-out screencap -p` grabs the current frame.
2. **Detect state** — `cv2.matchTemplate` against `templates/*.png` (match > ~0.9) tells us
   which screen/popup we're on: idle barracks, mid-training (speedup button visible),
   capacity popup, exit dialog, etc. Templates are cropped tight so they match across
   camera pans and minor UI shifts.
3. **Read numbers** — Tesseract OCR on fixed screen regions reads the owned-troop count
   and food, with sanity bounds to reject misreads.
4. **Act** — `adb input tap/swipe/text/keyevent` performs the click.
5. **Recover** — if knocked off the training screen by an event popup, the recovery
   playbook dismisses it (Cancel/Back only — never taps anything that could spend gems)
   and re-locates the barracks by template before resuming.

---

## Self-healing (runs for hours unattended)

Out of food, Evony forces the training quantity to 1 and puts a timer on the Train button,
so `train_one_batch` returns `NAV`, not `NOFOOD`. The loop therefore refills on **sustained
failure of any kind**, not a specific code:

- **3 and 6 consecutive fails** → `auto_refill.refill()` opens ~5B food (5000 × 1M items) and
  navigates back to the barracks. Bounded and gated so it never opens all food or taps a gem
  button.
- **8 fails** → `auto_refill.app_refresh()` force-stops and relaunches the app (resets the
  camera to default zoom where templates match again), then re-navigates.
- **10 fails** → stop for a human look (rare).

The modal quantity is read with a **color mask** (orange-on-beige defeats grayscale
thresholding): keep pixels where `r-g > 45 && r-b > 60`, invert, upscale, OCR.

Run the refill or a refresh manually any time:

```bash
python auto_refill.py 5000     # open ~5B food and return to Warriors
python auto_refill.py refresh  # force-stop + relaunch + navigate to Warriors
```

A 2-minute monitor loop restarts the bot if it dies, confirms each refill fired, and refreshes
the dashboards. See `kb/11-self-healing-food-refill.md` for the full write-up.

## Notes & safety rails

- **Never spends gems.** Recovery is dismiss/back-only; blind taps that once hit a gem
  "Instant Finish" button were removed.
- **Never "opens all" food.** Food top-up is hard-capped.
- **Stale display resync:** if the in-game resource display desyncs, a force-stop +
  relaunch (`am force-stop` / `monkey`) re-syncs it.
- The `kb/` folder documents the game mechanics and design decisions behind these rails.

This is a personal automation tool for a single self-owned account. Use responsibly.
