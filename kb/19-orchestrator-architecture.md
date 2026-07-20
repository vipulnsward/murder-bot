# Orchestrator Architecture — building toward a full-service bot

Goal: **replicate a full Evony automation bot** (training + gathering + rallies + monsters +
defense + alliance + daily) and run/improve it locally. `orchestrator.py` is the engine that
makes adding features incremental instead of a rewrite. It wires together the tested building
blocks from this session:

| Block | Role |
|-------|------|
| `fast_screenshot.py` | fast frames (raw `screencap` → NumPy, ~2.4× faster) |
| `screen_fsm.py` | "which screen am I on?" + **account-disconnect guard** |
| `watchdog.py` | crash/stuck detection + `app_refresh` recovery |
| `scheduler.py` | ALAS-style time-based scheduling (priority + interval) |

## The model

Every feature is a **`Task(name, interval, priority, enabled, run)`**. `run(ctx)` does **one
unit of work** and returns an optional seconds-override for its next run. The orchestrator loop:

1. grabs a frame,
2. **disconnect guard** — if the account-disconnect screen is up, it **STOPS without tapping**
   (the account is shared with easy-bot.club, whose logins cause it),
3. runs the single most-due, highest-priority ready task,
4. sleeps until the next task is due.

`training` is implemented (reuses `train_to_1b`, gem-safe: item-based "Use", never "Finish All").
Every other feature is registered as a **disabled stub** with the exact behavior to fill in.

## Adding a feature (the local workflow)

1. **Capture its UI** on a clean, uncontended session: screencap the screens it touches, crop
   tight templates into `templates/`, note button coordinates.
2. **Implement `run(ctx)`**: use `ctx.screencap()` + `screen_fsm.identify()` to confirm the
   screen, then tap. Reuse `screen_fsm.ensure_training`-style nav patterns. Raise `NotReady`
   if it can't act this tick (the scheduler retries).
3. **Enable it** in `default_tasks()` and pick a sensible `interval`/`priority` (defense = low
   interval + top priority; daily/alliance = hourly).
4. **Gem-safety rule (hard):** no task may tap a gem-spend path. Prefer item/free actions; gate
   any gem action behind explicit, bounded confirmation. Training already follows this.

## Task registry & roadmap mapping (see kb/18)

| Task | Priority | Interval | Status | Needs |
|------|:--------:|:--------:|--------|-------|
| `training` | 10 | 6s | **working** | — |
| `auto_shield` | 1 | 20s | stub | incoming-attack UI templates ([fixed-UI]) |
| `rally_join` | 12 | 60s | stub | rally-list UI ([fixed-UI-ish]) |
| `monster` | 14 | 90s | stub | map scan + presets ([zoom-nav]) |
| `gather` | 15 | 120s | stub | zoom-robust map/tile nav ([zoom-nav]) |
| `alliance` | 25 | 4h | stub | alliance UI ([fixed-UI]) |
| `daily_collect` | 30 | 1h | stub | mail/wheel/eggs/patrol UI ([fixed-UI]) |

Build order (kb/18): auto_shield → alliance → daily_collect → (zoom-nav) → gather → rally →
monster. Fixed-UI features don't need the camera-zoom-robust nav; map features do.

## Known constraints carried in

- **Camera-zoom / banner-overlay fragility** — building templates match only near a canonical
  zoom; a training banner over the barracks shifts the match (see kb/12, multiscale.py). Map
  features (gather/monster) need zoom-robust nav (scroll-to-center + `barracks_busy`-style
  state templates) before they're reliable.
- **Shared account with easy-bot.club** — login contention shows as the disconnect screen; the
  engine yields (stops) rather than fighting. A coexistence mode (time-slice, or auto-reclaim
  after N minutes) is an open design choice.

## Run

```bash
python orchestrator.py            # dry-run self-test (no ADB)
python -c "import orchestrator; orchestrator.run()"   # live (training enabled)
```

`train_to_1b.py` still runs standalone unchanged; the orchestrator is the additive path toward
the full-feature bot.
