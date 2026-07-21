# Murder Bot — management app plan (design only, not implemented)

A local web app to **run, configure, observe, and debug** the Evony bot — the ESB /
easy-bot.club style control panel, but for our own gem-safe local bot. View and edit
every config, toggle features, watch the live screen, tail logs, and use the vision
tools that accelerate live-wiring. Feature-rich, simple, and nice to look at.

> Working name: **Murder Bot** (the Keep is Evony's command center). Alt: *Suzerain*.

---

## 1. Principles

- **Single source of truth for config.** Today each module owns a `DEFAULTS`/policy
  dataclass. The app needs one typed, validated, hot-reloadable config — this is the
  linchpin refactor (see §4). Edit in the UI → the running bot picks it up without
  losing its game session.
- **Gem-safety is surfaced and LOCKED.** The UI shows the hard invariants (no gem spend,
  disconnect-stop, humanize on) as read-only guarantees. There is no toggle that can turn
  gem spending on. A prominent **Panic Stop**.
- **Everything observable.** Live screen + FSM/Holo screen label, task states, macro
  schedule, logs, notifications, and the LLM decision log — all visible in real time.
- **Simple surface, rich underneath.** Clean left-nav shell; progressive disclosure
  (advanced policy params behind an "Advanced" fold).
- **Reuse, don't rewrite.** The backend imports the existing modules directly (policies,
  `ocr_read`, `holo_vision`, `screen_id`, `live_stream`, `notify`) — the app is a shell
  around code that already works and is tested (17/17 suite).

## 2. Architecture

```
┌──────────────── Frontend (React + TS SPA) ────────────────┐
│  Dashboard · Live · Tasks · Config · Schedule · Fleet ·    │
│  Logs · Vision · KB · Safety        (Tailwind + shadcn/ui) │
└───────────────▲───────────────────────────▲───────────────┘
      REST (React Query)              WebSocket (status/logs/frames)
┌───────────────┴───────────────────────────┴───────────────┐
│                 Backend API (FastAPI, Python)              │
│  /api/config  /api/tasks  /api/status  /api/control        │
│  /api/vision  /api/templates  /ws/{logs,status,screen}     │
├────────────────────────────────────────────────────────────┤
│  Control bridge  ──►  Orchestrator (managed thread/process)│
│                       scheduler · FSM · watchdog · tasks    │
│  Config store (config.yaml + pydantic)  ◄── hot reload      │
│  Reuses: policies, ocr_read, holo_vision, screen_id,        │
│          live_stream (MJPEG), notify, fleet (kb/32)         │
└────────────────────────────────────────────────────────────┘
                         │ ADB
                 BlueStacks / emulators
```

## 3. Tech stack (recommended)

| Layer | Choice | Why |
|---|---|---|
| Backend | **FastAPI** (Python 3.14, mise `.venv`) | Same runtime as the bot → imports policies/vision directly; `fastapi` already installed; async + WebSocket + auto OpenAPI |
| Realtime | **WebSocket** (+ SSE fallback) | live logs, status, screen frames |
| Frontend | **React + TypeScript + Vite** | your stack; rich UI; fast dev |
| UI kit | **Tailwind + shadcn/ui (Radix)** | clean, accessible, un-opinionated visuals; easy dark mode |
| Data | **React Query** (REST) + a `useWS` hook | caching, optimistic config edits, live streams |
| Config | **Pydantic v2 models + `config.yaml`** | typed, validated, diff-able, hot-reload |
| Charts | **Recharts** | troops/food/ETA history |
| Screen | reuse **`live_stream.py`** MJPEG (later: WebRTC) | already built |

*Simpler alt (if you want less JS):* server-rendered **HTMX + Alpine + Tailwind** off the
same FastAPI — fewer moving parts, still nice, but less "app-like" for rich views.

## 4. Config model (the linchpin)

Centralize the scattered configs into one schema the app and bot share:

```
config.yaml
├─ device / fleet:   accounts[] {name, adb_port, enabled, features[]}
├─ safety:           gem_spend: false (LOCKED)  · disconnect: stop_only
├─ humanize:         jitter, delays, windmouse, click_window ...   (from humanize.DEFAULTS)
├─ macro_schedule:   sleep_len_h, sleep_anchor_h, break cadence ...
├─ tasks:            per task → {enabled, interval, priority, policy params}
│                     auto_shield{react_within_s, reshield_margin_s, desired_cover_s, proactive}
│                     gather{reserved_for_rallies, tile prefs} · monster{max_level, min_stamina_reserve}
│                     alliance{donations_per_day} · daily_collect{max_per_tick, cooldowns} · ...
├─ vision:           ocr_first, holo_model, holo_fallback_on
└─ notify:           slack_webhook, mac_banner, discord_webhook
```

- Each module gains a `from_config(cfg)` classmethod; `orchestrator.run()` loads `config.yaml`.
- The app validates edits against the pydantic schema; **gem_spend is a frozen field** (422 on any attempt to set true).
- **Hot reload:** PUT `/api/config` writes yaml + signals the bridge to re-read at the next tick boundary (no session loss).

## 5. Backend API surface

- `GET/PUT /api/config` — whole config or a JSON-patch subtree; validated; hot-reload.
- `GET /api/tasks` · `POST /api/tasks/{name}/toggle` · `POST /api/tasks/{name}/run-now`.
- `GET /api/status` — running/paused/disconnected, current task, macro state, uptime, counts.
- `POST /api/control` — start · pause · resume · **panic-stop** · reclaim-session (guarded).
- `GET /api/logs?since=` · `GET /api/events` (notification history) · `GET /api/decisions` (llm_decisions.jsonl).
- `POST /api/vision/ocr` · `/api/vision/ground {instruction}` · `/api/vision/classify` — run on the current frame.
- `GET/POST /api/templates` — list/capture/crop templates (the kb/31 wiring accelerator).
- `WS /ws/status` · `/ws/logs` · `/ws/screen` (MJPEG or frame push).

## 6. Frontend — pages & features

- **Dashboard** — status card (running/paused/**disconnected**), current task + macro state
  (active/break/sleep), uptime, safety badges (🔒 no-gems · disconnect-safe · humanized),
  live screen thumbnail, mini troops/food/ETA charts, recent events. One **Panic Stop**.
- **Live** — full emulator stream + overlay of FSM label / Holo classification; click a spot →
  "what's here?" (grounding); manual tap/swipe (dev mode, gem-guarded).
- **Tasks** — table of all 8 tasks: enable toggle, interval, priority, last run, next run,
  status; expand a row → its policy params (with the guard values highlighted, e.g. gather's
  `reserved_for_rallies`, monster's caps). "Run now."
- **Config** — full structured editor grouped by section (safety / humanize / schedule / tasks /
  vision / notify), validation inline, diff + save, revert. Advanced fold. Raw-YAML view.
- **Schedule** — 24h timeline visualizing sleep block + micro-breaks; edit active hours / sleep
  length / break cadence and see the timeline update.
- **Fleet** — accounts/emulators (kb/32): per-account device port, enabled features, status;
  note on staying on separate accounts from easy-bot.club.
- **Logs** — live tail (WS), level filter, search; **Events** = disconnect/bot-tell/crash history.
- **Vision** — OCR/Holo playground on the current frame; **Template Capture** tool (grab → crop →
  name → save to `templates/`) to speed the `[LIVE-CAPTURE]` wiring; grounding tester with coord overlay.
- **Knowledge** — rendered browser of the `kb/` docs (the researched game knowledge).
- **Safety** — the invariants explained + shown enforced; the gem-lock; disconnect policy;
  humanization status; Panic Stop.

## 7. UI direction (nice + simple)

- Left icon-nav rail + top status strip; content area with card/table layouts.
- **Dark-first** (the bot runs overnight), light available. Neutral grays with a single accent.
- Typography per practicaltypography: **Geist / IBM Plex / Inter**, body ~15–16px, dark-gray
  text, generous line-height, tabular-nums for all the counters/coords.
- State encoded in form + color: green=running, amber=break/sleep, red=disconnected/attack.

```
┌───────────────────────────────────────────────────────────┐
│ ● Running · Training · 🔒 gem-safe · humanized   [Panic ⏹] │
├──┬────────────────────────────────────────────────────────┤
│▚ │  Keep · Warriors T2                    ┌─ live ───────┐ │
│⧉ │  Trained 501M  Food 629M  ETA 3h12m    │  [emulator]  │ │
│☰ │  ┌ Tasks ──────────────────────────┐   │  screen:city │ │
│⏱ │  │ training     ● 6s   ▲10          │   └──────────────┘ │
│⚔ │  │ auto_shield  ○ 20s  ▲1  (wire)   │   Events            │
│▤ │  │ gather       ○ 120s reserve=2    │   • 02:14 sleep→…   │
│⚙ │  └──────────────────────────────────┘   • 01:50 break     │
└──┴────────────────────────────────────────────────────────┘
```

## 8. Safety & deployment

- **Local-only by default** (bind 127.0.0.1). Remote access = your existing Cloudflare tunnel
  (like the current dashboard) with auth (token / Cloudflare Access) — never open unauthenticated.
- **Gem-lock** enforced server-side (frozen pydantic field), not just hidden in the UI.
- **Reclaim-session** (tap Restart after a disconnect) requires an explicit confirm in the UI —
  mirrors the standing rule to never auto-tap Quit/Restart.
- Config writes are versioned (keep last N `config.yaml` snapshots) for easy revert.

## 9. Phased roadmap

- **P1 — MVP (view/edit + observe):** config-centralization refactor → FastAPI skeleton →
  Dashboard + Tasks (toggle/params) + Config editor + live status (WS). Gem-lock + Panic Stop.
- **P2 — observe deeper:** Live screen + overlays, Logs/Events stream, Schedule timeline, Safety page.
- **P3 — power tools:** Vision playground + **Template Capture** + grounding tester, Fleet/multi-account,
  KB viewer, metrics/history charts.

## 10. Open decisions (your call)

1. **Frontend:** React SPA (rich, recommended) vs. HTMX/Alpine (simpler, less JS)?
2. **Scope now:** single-account console first, or design Fleet/multi-account in from P1?
3. **Access:** local-only, or remote via the miru.so Cloudflare tunnel (needs auth) from the start?
4. **Name:** *Murder Bot*, *Suzerain*, or your pick?

*This is a plan only — nothing here is implemented. The config-centralization refactor (§4) is
the first real step and also independently improves the bot.*
