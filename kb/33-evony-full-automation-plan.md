# Evony Full-Automation Build Plan (capstone)

Synthesis of the overnight research (kb/23–32) into a **phased build order** for the orchestrator.
Each feature maps to its research doc, its in-game UI flow, and the OSS bot whose code to lift.

## Foundations already built (this project)
- `orchestrator.py` — multi-task engine (scheduler + FSM disconnect-guard + watchdog + fast
  screenshots); training works, other features are stubs to fill.
- `screen_fsm.py` + `game_brain/` — screen classification + catalog (kb/31 feeds ~30 more nodes
  after a live capture pass).
- `ocr_read.py` (RapidOCR) — reliable numbers + **text-button grounding** (zoom-robust).
- `llm_agent.py` — vision fallback; **switch to Holo1.5-7B via MLX** (kb/29), OCR stays primary.
- Gem-safety (item-based "Use" only) enforced throughout.

## Reusable OSS bots (lift, don't reinvent)
- **sonpiaz/4x-game-agent (MIT)** — near-drop-in for **base-dev + world-model + template_match
  find_all + FSM/ensure_home/popup-stack**. The best architectural blueprint.
- **Jany-M/TaskEX** (our exact stack: Py3.12+ADB+BlueStacks+OpenCV+Tesseract, 540×960) —
  **auto-bubble** code + **multi-instance** (per-port + SQLite registry) + red-X-close-with-safety-guard.
- **TungNC-echoes/auto-evony-v1** — **rally/boss tap sequences** (attack→war→5min→preset→general→
  troop→march; join flow) + multi-MEmu.

## Strategic frame
- **Our niche = base development + daily collection + troop training** — UNCLAIMED (no OSS/commercial
  Evony bot does them). The map/rally/gather/stamina side is **easy-bot.club's** domain.
- **Coexistence = SEPARATE ACCOUNTS** (kb/32): cloud easy-bot on **farm** accounts, our local bot on
  **main/build** accounts → zero session contention (the disconnect tug-of-war dissolves).
- **Vision:** OCR primary (kb/21/22) → Holo1.5-7B MLX fallback (kb/29) → deterministic FSM for known
  screens. **Gem-safe + humanize (kb/30)** wrap every task; **fleet.py** (kb/32) for N accounts.

## Feature → kb → OSS map
| Task (orchestrator) | kb | UI flow / detection | Lift from |
|---|---|---|---|
| `base_dev` (upgrade+research+duty) | kb/27 | green up-arrow `find_all`; radial→Upgrade; Academy→Research; Duty hot-swap; item speedups | 4x-game-agent (world_model, building_finder, workflow_engine) |
| `daily_collect` | kb/28 | red-dot (red-pixel-area) → claim; wall patrol/wheel/mail/tax/levy/bounty/shrine/VIP | 4x-game-agent screen_analyzer red-dot |
| `alliance` | kb/28 | Embassy hand (help-all); Science donation (stop before gem tier); Gift/Treasure | — |
| `auto_shield` | kb/26 | Watchtower incoming ETA → City Buff→Truce→Use (item); reactive+proactive | TaskEX auto_bubble (add reactive trigger) |
| `gather` | kb/23 | globe→Search→Resource tab→level→Go→tile→Gather→March; poll-and-fill march slots | — (map-nav) |
| `rally_join` | kb/24 | war_button→filter boss portraits→join_button→preset→general→march | auto-evony-v1 join flow |
| `monster` / rally-set | kb/24,25 | Search→Monster tab→type+level→Go→sprite→Attack→March; or attack→war→5min→preset | auto-evony-v1 boss_attacker |
| training (done) | (existing) | Train→speedup→**Use** (items, gem-safe) | — |
| fleet / multi-account | kb/32 | N ADB ports, per-account profiles.yaml (no passwords), round-robin | TaskEX per-port registry |
| humanize / anti-detect | kb/30 | jittered taps, ranged delays, WindMouse swipes, macro schedule, pause-on-unknown | ALAS utils/device |

## Phased build order
**Phase 0 — infra (small, do first):** point `llm_agent` at Holo1.5-7B MLX; add `humanize` wrapper
(kb/30) around `ctx.tap/swipe` + shuffle scheduler + Discord/Telegram notify on unknown/disconnect;
wire the ALAS-style scheduler into the live loop.

**Phase 1 — fixed-UI features (no zoom-robust map nav needed) — highest value/effort:**
1. `auto_shield` (survival gate; unblocks unattended running) — kb/26 + TaskEX.
2. `daily_collect` + `alliance` (red-dot claim loops) — kb/28.
3. Harden `base_dev` (our niche; green-arrow find_all) — kb/27 + 4x-game-agent.
   → All fixed-UI: template + OCR + red-dot; run on the scheduler.

**Phase 2 — map features (need the zoom-robust nav + kb/31 capture pass):**
4. `gather` — kb/23 (also funds any food goal).
5. `rally_join` — kb/24 (UI-list based, easier).
6. `monster` / rally-set — kb/24,25 (map scan + presets; hardest).
   Prereq: do the **kb/31 live capture pass** (~30 screens need templates) so `screen_fsm` +
   `game_brain` can navigate reliably; then map features become tractable.

**Phase 3 — scale:** `fleet.py` for N accounts (kb/32); each account a profile + device.

## Immediate next actions (when back at a clean session)
1. Live **capture pass** for kb/31's ~30 un-templated screens → grow `game_brain/catalog.json`.
2. Build `auto_shield` (Phase 1, #1) end-to-end and live-verify.
3. Swap vision to Holo1.5-7B (MLX server) + add `humanize` + notify.
All gem-safe; separate accounts from easy-bot.club; OCR-first, LLM-fallback.
