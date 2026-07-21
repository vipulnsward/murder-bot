# Murder Bot

A **gem-safe, humanized automation bot** for **Evony: The King's Return** running on a
local Android emulator (BlueStacks). It drives the game entirely through ADB input
(taps/swipes) and understands the screen with OpenCV template matching, fast RapidOCR,
and a **local Holo1.5-7B vision model** (MLX, on-device) — no game API, no memory hacks,
no accessibility tree (Evony is a Unity/IL2CPP app, so the screen is the only interface).

Murder Bot pairs the automation core with a **web control app** (FastAPI + React) for
running, configuring, and watching the bot live, plus a researched strategy knowledge
base (300+ generals, 140+ guides) it can consult.

> Evony's ToS prohibits automation. This is a personal tool for a single self-owned
> account whose risk you accept. Use responsibly.

---

## Safety invariants (locked, not optional)

These are enforced in code, not just documented — they are the whole point of the bot.

- **Never spends gems.** No task or recovery path ever taps a gem button (Finish All /
  Instant Finish / Buy / Confirm-purchase). The control app's `gem_spend` flag is a frozen
  field — the API returns `422` on any attempt to set it true.
- **Disconnect = stop.** On the account-disconnect screen the bot stops and notifies; it
  never taps Quit/Restart on its own (reclaim requires an explicit operator confirm).
- **Humanized input.** WindMouse-style curved motion, per-tap jitter and dwell, deliberate
  vs. quick taps, and same-button repeat limits — no robotic pixel-perfect cadence.
- **Human activity schedule.** A macro schedule adds micro-breaks and an overnight sleep
  block so activity looks human across a day.
- **Bounded actions.** Resource opens are hard-capped ("never open all"), and every module
  self-polices its own guard values.

---

## What it does

An orchestrator runs pluggable, independently-tested feature modules on a time-based
scheduler (most-due, highest-priority task wins; each reschedules itself):

| Module | Job |
|--------|-----|
| `auto_shield.py`   | Keep a defensive shield up; proactively re-shield before it lapses. |
| `daily_collect.py` | Daily upkeep — collect resources, chests, and free dailies. |
| `alliance.py`      | Alliance help, donations, and gifts. |
| `base_dev.py`      | Base development — buildings, research, and upgrades. |
| `gather.py`        | Send troops to gather tiles (reserves marches for rallies). |
| `rally_join.py`    | Join alliance rallies against monsters/enemies. |
| `monster.py`       | Solo-hunt monsters within stamina and level caps. |

Every module ships with a self-test and gem-safe defaults. The full suite is **17/17
passing** (`python selftest.py`).

---

## The stack

| Layer | Tech |
|-------|------|
| **Language / runtime** | Python 3.14 (managed with `mise`, repo `.venv`) |
| **Device control** | ADB → BlueStacks (`127.0.0.1:5555`); `input tap/swipe`, `screencap`, `screenrecord` |
| **Perception** | OpenCV template matching + **RapidOCR** (rec-only fast path, content-hash cache) + **Holo1.5-7B** vision via `mlx-vlm` (local, free) |
| **Vision memory** | `vision.db` (SQLite) — mapped screens, UI elements, and captures with perceptual-hash dedup |
| **Knowledge base** | `game_kb.py` (SQLite) — **303 generals**, **144 guides** crawled from evonyguidewiki.com; `strategist.py` / `general_advisor.py` query it |
| **Control app — backend** | **FastAPI** (imports the bot modules directly), WebSockets for live status/logs/screen |
| **Control app — frontend** | **React + TypeScript + Vite**, Tailwind + shadcn/ui, React Query |
| **Live screen** | One `screenrecord` → `ffmpeg` fan-out: **HLS 60fps** for the browser **+** a shared JPEG for the mapper (solves the two-consumer / one-ADB constraint) |
| **Remote access** | Cloudflare quick tunnel (`cloudflared --url`) → public HTTPS |
| **Notifications** | macOS banners + optional Slack/Discord webhooks |

---

## Layout

| Path | What it is |
|------|------------|
| `orchestrator.py` | The engine: scheduler + FSM + watchdog + humanized tap/find context. |
| `run_bot.py` | Entry point that wires the orchestrator and the feature modules. |
| `humanize.py` · `macro_schedule.py` | Human-like input + activity schedule. |
| `nav.py` | Reliable navigation primitives (back, city view, reclaim-after-disconnect). |
| `perception.py` · `screen_id.py` · `ocr_read.py` · `holo_vision.py` | Vision toolkit (find/ground/read-number/classify). |
| `vision_db.py` · `game_brain/vision.db` | The mapped-game vision store. |
| `state_reader.py` · `strategist.py` · `brain.py` · `general_advisor.py` | Read game state and decide/advise from the knowledge base. |
| `game_kb.py` · `data/*.jsonl` | Strategy knowledge base + reproducible seed data. |
| `keep/` | FastAPI backend for the control app (`server.py`, `bridge.py`, `stream.py`). |
| `keep/web/` | React + TS control-app frontend. |
| `keep_live.py` | Runs the full control app locally with a live emulator frame source. |
| `templates/` | Click-proof PNG templates for UI elements and buildings. |
| `kb/` | Researched write-ups on combat, resources, botting, buffs, self-healing. |
| `selftest.py` | One-command test suite for every module (17/17). |

---

## Requirements

- **BlueStacks** (or any Android emulator) with ADB debugging on, Evony installed and logged in.
- **ADB** reachable at `127.0.0.1:5555` (adjust `DEVICE` if yours differs).
- **Python 3.14** via `mise` (`mise install`), then the repo `.venv` (`--system-site-packages`
  so the ML stack from the global env is visible).
- Optional: **ffmpeg** (HLS stream), **cloudflared** (public URL), **Node** (build the frontend).

```bash
mise install                     # Python 3.14 per .mise.toml
adb connect 127.0.0.1:5555       # confirm the emulator is attached
adb devices
python selftest.py               # 17/17 should pass
```

---

## Usage

### Run the control app (dashboard + live screen)

```bash
python keep_live.py --port 8000
```

Then open `http://127.0.0.1:8000` — Dashboard, Live screen, Tasks, Config, Schedule,
Generals, Knowledge, and Safety. The gem-lock and Panic Stop are surfaced and enforced.

Expose it publicly (ephemeral URL, only up while your Mac + app + tunnel run):

```bash
cloudflared tunnel --url http://localhost:8000
```

### Build the frontend after UI changes

```bash
cd keep/web && npm install && npm run build
```

### Run the bot

```bash
python run_bot.py                # orchestrator + feature modules on the scheduler
```

---

## How it works

1. **Capture** — a shared `screenrecord`→`ffmpeg` pipeline produces both the browser HLS
   stream and a fresh JPEG frame; the bot reads the frame (one ADB capture, two consumers).
2. **Understand** — OpenCV templates and OCR identify the screen and read numbers; Holo1.5
   grounds free-form queries ("where is X?") when a template doesn't exist yet.
3. **Decide** — the scheduler picks the most-due task; `strategist`/`brain` consult the
   knowledge base for strategy calls.
4. **Act** — humanized `adb input tap/swipe` performs the move (gem buttons are never targets).
5. **Recover** — a watchdog handles crashes/stuck screens; on disconnect it stops and notifies
   rather than tapping anything risky.

See **[ORCHESTRATOR.md](ORCHESTRATOR.md)** for the engine design and `kb/` for the game
mechanics and decisions behind the safety rails.

---

## History

Murder Bot began as a single-purpose **troop trainer** and ran multiple unattended
campaigns (e.g. a T2 ground push to **500M Conscripts** — 294 batches, 8 food refills, 0
failures) before growing into the multi-feature, gem-safe, vision-driven bot it is today.
Those early runs proved out the self-healing and safety-rail design the current modules
inherit.
