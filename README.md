# Easybot — the Evony PvP brain that never sleeps

An autonomous **Evony: The King's Return** platform: runs your account 24/7, reads every
incoming fight and tells you exactly when to defend / rally / ghost / bubble (backed by a real
battle simulator that learns from *your* reports), maps the game into a vision DB, tracks every
enemy, and continuously learns the meta from YouTube + web guides. Local-first, one command from
a live Hetzner deployment.

> **Gem/resource-safe by design.** The bot never taps Quit, never spends gems, never buys. On a
> disconnect it either waits or (per config) reclaims via Restart only. Attack execution is OFF
> by default. Automating Evony likely violates its ToS — run at your own risk.
>
> The original automation-core notes live in `docs_core_README.md`.

## What it does

- **Live view** — the emulator streamed to your browser (`/manager`).
- **Advanced AI countering** (`/counter`, `counter_ai.py`) — `decide(state)` / `decide_vs(name)`
  return a ranked plan (defend/rally/ghost/bubble + lead type + expected loss %), quantified by a
  cloned battle simulator on your real roster + buffs, and citing what it's learned.
- **Enemy intel on everyone** (`/intel`, `enemy_intel.py`) — troops, buffs, generals, coords,
  W/L, threat, in the `enemies` table.
- **Attack planner** (`/attack`, `attack_planner.py`) — ranks favorable-trade targets (advisory;
  execution gem-safe + config-gated OFF).
- **Self-evolving brain** (`/brain`, `knowledge_*`) — ingests Evony YouTube + guide pages, distills
  them into tactics the decision engine cites; a 24/7 daemon keeps it learning.
- **Vision-DB mapping** (`/map`, `game_mapper.py`) — screenshots + OCRs + catalogs game screens.
- **Runs the account** (`video_report_loop.sh`) — joins rallies ~every minute, tops stamina from
  owned items, scans battle reports, auto-reclaims after a kickout.
- **10-page manager** — home hub, bot control, counter, intel, attack, brain, reports, map,
  generals gallery, billing, settings — argon2 auth, Fernet-encrypted credentials, rate-limited,
  security-header-hardened, `/healthz` monitored.

## Architecture

```
Browser ──HTTPS──▶ Caddy (security headers) ──▶ manager (FastAPI :8800) ──┐
                                                                          ├─▶ Postgres (murderbot)
   game bot loop ──ADB──▶ Redroid (headless Android) ◀────────────────────┘
   knowledge daemon ──▶ YouTube / web guides ──▶ knowledge table ──▶ distilled brain ──▶ counter_ai
```

On a Hetzner ARM VM everything runs as containers (`deploy/docker-compose.yml`); Evony runs
natively in Redroid (no x86 translation). Locally the bot drives BlueStacks on `127.0.0.1:5555`.

## Quick start (local)

```bash
make manager      # web UI at http://127.0.0.1:8800  (signup → /home onboarding)
make bot          # start the 24/7 game bot loop
make learn        # start the 24/7 knowledge daemon
make check        # system health (DB, engines, daemons)
make test         # 17-test regression suite
make backup       # dump the DB
```

## Go live (Hetzner)

```bash
HCLOUD_TOKEN=<your-token> ./deploy/launch.sh    # creates the ARM VM + brings up the stack
```
Then point `easybot.gg` at the printed IP, sideload the Evony APK into Redroid, and log in with
your email/password. Full runbook: `deploy/README.md`. Cost/ROI: `deploy/COST_MODEL.md`.

## Pricing (subscriptions, `/billing`)

| Free | Pro $7/mo | Alliance $29/mo |
|---|---|---|
| dashboard + brain preview | full bot + AI counter + intel + reports | multi-account + intel on everyone |

Break-even on ~$1K/mo infra ≈ **143 Pro** or **34 Alliance** subs.

## Layout

| Path | What |
|---|---|
| `neo_app/` | FastAPI manager + the 10 page routers (`*_view.py`) + `hub_view.py` |
| `counter_ai.py` | AI counter engine (+ simulator + optional LLM narration) |
| `enemy_intel.py` / `attack_planner.py` | recon + attack planning |
| `knowledge_ingest.py` / `knowledge_synth.py` / `discord_bot.py` | learning pipeline |
| `game_mapper.py` / `screen_fsm.py` / `vision_db.py` | vision DB |
| `deploy/` | Dockerfiles, compose, cloud-init, Caddyfile, `launch.sh`, `db_backup.sh`, cost model |
| `tests/` | pytest regression suite (`make test`) · `pytest.ini` · `.github/workflows/ci.yml` |
| `selfcheck.py` | one-command system health check |
