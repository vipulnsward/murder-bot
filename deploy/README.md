# Murder Bot — Hetzner + Redroid deploy package

Run the Evony automation bot **headless** on a cheap Hetzner ARM VM using
**Redroid** (Android-in-Docker) instead of BlueStacks. No Google Play / GApps —
Evony logs in with **email + password**, which is all Redroid needs.

```
Hetzner CAX21 (Ampere arm64, Ubuntu 24.04)
└─ docker compose (deploy/docker-compose.yml)
   ├─ redroid            Android 11, arm64 native, hosts Evony + adbd:5555
   ├─ postgres:16        db "murderbot"
   ├─ murderbot-bot      run_bot.py  ── adb ──▶ redroid:5555
   ├─ murderbot-manager  uvicorn app:app :8800 (web UI + live MJPEG)
   └─ caddy              :80/:443 → manager, auto-HTTPS for murderbot.gg
```

Everything ARM-native: `python:3.11-slim`, `postgres:16`, `caddy:2`, and
`redroid/redroid:11.0.0-latest` are all multi-arch, so **no x86 translation** on
Ampere.

---

## Files in this package

| File | Purpose |
|------|---------|
| `Dockerfile.bot` | Worker image: adb + tesseract + opencv/onnxruntime + Linux-safe bot deps |
| `Dockerfile.manager` | FastAPI manager image: adb + opencv + app deps |
| `requirements.bot.txt` | Linux/arm64 dependency subset (mlx/mlx-vlm removed — see note) |
| `docker-entrypoint.sh` | `adb connect` + wait-for-boot, then exec the real command |
| `docker-compose.yml` | The 5-service stack |
| `Caddyfile` | Reverse proxy + auto-HTTPS |
| `cloud-init.yaml` | Ubuntu 24.04 first-boot: docker + binder + secrets + `compose up` |
| `.env.example` | Secrets/config template (cloud-init generates the real `.env`) |
| `../.dockerignore` | Keeps build contexts lean + secret-free (repo root) |

---

## Go-live runbook

### 0. Prerequisites
- Hetzner Cloud account + a project.
- A domain you can point at the VM (placeholder here: **murderbot.gg**).
- The Evony APK (`.apk` / `.xapk` split — use the base APK) on your laptop.
- The bot repo pushed somewhere you can `git clone`, or ready to `rsync`/`scp`.

### 1. Create the VM (CAX21 = 4 vCPU Ampere / 8 GB — the sweet spot for one emulator)
```bash
hcloud server create \
  --name murderbot \
  --image ubuntu-24.04 \
  --type cax21 \
  --location fsn1 \
  --ssh-key <your-key> \
  --user-data-from-file deploy/cloud-init.yaml
```
Or use the Cloud Console: **Create Server → Arm64 (CAX) → Ubuntu 24.04**, and
paste `deploy/cloud-init.yaml` into the *Cloud config* box.

cloud-init installs Docker, loads the `binder` kernel module, and writes
`/opt/murderbot/deploy/.env` with fresh random secrets.

### 2. Upload the code (if cloud-init didn't clone it)
cloud-init only auto-starts the stack when the code is already at
`/opt/murderbot`. If you didn't bake a `git clone` in, upload it:
```bash
# from your laptop, at the repo root
rsync -az --delete \
  --exclude '.venv' --exclude '.git' --exclude 'game_brain/live' \
  ./ root@<vm-ip>:/opt/murderbot/
```
Then on the VM:
```bash
cd /opt/murderbot/deploy
docker compose up -d --build      # first build ~5–10 min on arm64
docker compose ps                 # all services should become healthy
```

### 3. Verify binder + Redroid actually came up
```bash
# On the host: binder devices must exist for Redroid to boot.
ls -l /dev/binder /dev/hwbinder /dev/vndbinder 2>/dev/null || ls -l /dev/binderfs
lsmod | grep binder

# Redroid should reach boot_completed within ~2–3 min:
docker compose logs -f redroid
docker inspect --format '{{.State.Health.Status}}' murderbot-redroid-1
```
If `/dev/binder` is missing:
`sudo modprobe binder_linux devices=binder,hwbinder,vndbinder` then
`docker compose restart redroid`.

### 4. Sideload the Evony APK into Redroid
The bot + manager containers already have `adb` and can reach `redroid:5555`.
```bash
# copy the APK to the VM, then into the manager container:
scp Evony.apk root@<vm-ip>:/tmp/Evony.apk
docker compose cp /tmp/Evony.apk murderbot-manager:/tmp/Evony.apk

docker compose exec murderbot-manager sh -lc '
  adb connect "$ADB_TARGET" &&
  adb -s "$ADB_TARGET" install -r /tmp/Evony.apk &&
  adb -s "$ADB_TARGET" shell pm list packages | grep -i evony'
```
(For a `.xapk`/split bundle, unzip it and `adb install-multiple base.apk config.*.apk`.)

### 5. First email/password login
Open the live screen and drive the first login by hand once (Redroid keeps the
session in the `redroid-data` volume afterward):
```bash
# temporary tunnel to the manager before DNS/HTTPS is ready:
ssh -L 8800:localhost:8800 root@<vm-ip>
# then browse http://localhost:8800  → sign up → Add Evony account
```
Launch Evony and log in via the live view using tap/text over adb, e.g.:
```bash
docker compose exec murderbot-manager sh -lc '
  adb -s "$ADB_TARGET" shell monkey -p <evony.package.name> 1 &&
  adb -s "$ADB_TARGET" shell input text "your@email.com"'
```
Choose **“Log in with email”** in Evony, enter the credentials, clear any
first-run popups. Once you're at the city view, the bot can take over.

### 6. Point DNS at the VM + get HTTPS
Create DNS records for your domain:
```
murderbot.gg.      A     <vm-ipv4>
murderbot.gg.      AAAA  <vm-ipv6>     # CAX has IPv6; optional
```
Set `DOMAIN=murderbot.gg` in `/opt/murderbot/deploy/.env` (cloud-init defaults
to it), then `docker compose up -d caddy`. Caddy fetches a Let's Encrypt cert
automatically once DNS resolves and ports 80/443 are open in the Hetzner
firewall. Visit **https://murderbot.gg** → the manager UI + live emulator view.

### 7. Start the bot
The `murderbot-bot` service runs continuously (`restart: always`). Watch it:
```bash
docker compose logs -f murderbot-bot
```
Tune behaviour from the manager’s **Bot configuration** panel (writes
`/state/bot_config.json`, shared with the bot via the `bot-state` volume).

---

## REQUIRED code edits (apply in the real checkout before deploying)

These live **outside this worktree** (`neo_app/` is untracked) or across many bot
modules, so they’re listed for the coordinator rather than changed here.

### A. `config.py` — ALREADY DONE (in this branch)
`config.py` now reads the ADB target from the environment:
```python
import os
ADB_TARGET = os.environ.get("ADB_TARGET", "127.0.0.1:5555")
DEVICE = ADB_TARGET
```
This makes `evony_bot.py` (the only importer of `config`) honour `ADB_TARGET`
with zero further changes. Locally it stays `127.0.0.1:5555`.

### B. `neo_app/app.py` — 6 one-line env wraps (needed for the manager container)
`os` is already imported. Change each hardcoded constant to read env with the
**same default** (backward-compatible; local behaviour unchanged):

| Line | From | To |
|------|------|----|
| 28 | `DB_DSN = "dbname=murderbot host=localhost"` | `DB_DSN = os.environ.get("DB_DSN", "dbname=murderbot host=localhost")` |
| 31 | `DEVICE = "127.0.0.1:5555"` | `DEVICE = os.environ.get("ADB_TARGET", "127.0.0.1:5555")` |
| 32–35 | `BOT_SCRIPT = Path("…scratchpad/video_report_loop.sh")` | `BOT_SCRIPT = Path(os.environ.get("BOT_SCRIPT", "…/video_report_loop.sh"))` |
| 36 | `BOT_PIDFILE = Path("/tmp/video_report_loop.pid")` | `BOT_PIDFILE = Path(os.environ.get("BOT_PIDFILE", "/tmp/video_report_loop.pid"))` |
| 37 | `BOT_CONFIG_PATH = Path("/Users/.../bot_config.json")` | `BOT_CONFIG_PATH = Path(os.environ.get("BOT_CONFIG_PATH", "/Users/.../bot_config.json"))` |
| 38 | `BOT_STATUS_PATH = Path("/Users/.../bot_status.json")` | `BOT_STATUS_PATH = Path(os.environ.get("BOT_STATUS_PATH", "/Users/.../bot_status.json"))` |
| 39 | `BOT_LOG_PATH = Path("/tmp/video_report_loop.log")` | `BOT_LOG_PATH = Path(os.environ.get("BOT_LOG_PATH", "/tmp/video_report_loop.log"))` |

`NEO_SECRET` and `EVONY_ENC_KEY` are **already** env-aware via
`persisted_secret()`; compose passes them from `.env`.

### C. Bot modules — ADB target edit list (~15 modules + a few call sites)
Every module hardcodes the ADB serial. Two mechanical rules; pick per line.

**Rule 1 — module-level constants** → route through the central env-driven
config. Replace the whole line (match the existing local name `DEVICE` / `DEV` /
`D`):
```
from config import ADB_TARGET as DEVICE     # or: as DEV / as D
```

| File:line | Current |
|-----------|---------|
| `fast_screenshot.py:7` | `DEVICE = "127.0.0.1:5555"` |
| `orchestrator.py:30` | `DEVICE = "127.0.0.1:5555"` |
| `watchdog.py:8` | `DEVICE = "127.0.0.1:5555"` |
| `recovery_handler.py:8` | `DEVICE = "127.0.0.1:5555"` |
| `live_stream.py:14` | `DEVICE = "127.0.0.1:5555"` |
| `skill_library.py:19` | `DEVICE = "127.0.0.1:5555"` |
| `keep_live.py:20` | `DEVICE = "127.0.0.1:5555"` |
| `train_to_1b.py:10` | `DEVICE = "127.0.0.1:5555"` |
| `status.py:8` | `DEVICE = "127.0.0.1:5555"` |
| `food_topup.py:10` | `DEVICE = "127.0.0.1:5555"` |
| `infra_demo.py:7` | `DEV = "127.0.0.1:5555"` |
| `map_forever.py:9` | `DEV = "127.0.0.1:5555"` |
| `live_rally.py:21` | `DEV = "127.0.0.1:5555"` |
| `live_map.py:28` | `DEV = "127.0.0.1:5555"` |
| `auto_refill.py:10` | `D = "127.0.0.1:5555"` |

**Rule 2 — function defaults / argparse / inline literals** → replace just the
string literal with `os.environ.get("ADB_TARGET", "127.0.0.1:5555")` (ensure the
file has `import os`):

| File:line | Current |
|-----------|---------|
| `run_bot.py:30` | `p.add_argument("--device", default="127.0.0.1:5555")` |
| `humanize.py:100` | `def __init__(self, device="127.0.0.1:5555", …)` |
| `shared_capture.py:31` | `def grab(device="127.0.0.1:5555", …)` |
| `shared_capture.py:46` | `def grab_wait(device="127.0.0.1:5555", …)` |
| `curriculum.py:25` | `shared_capture.grab_wait("127.0.0.1:5555")` |
| `verify.py:59` | `shared_capture.grab_wait("127.0.0.1:5555")` |
| `gen_dashboard.py:285` | `["adb", "-s", "127.0.0.1:5555", "exec-out", …]` |

Ready-to-run sed for Rule 2 (review the diff before committing):
```bash
cd /opt/murderbot
for f in run_bot.py humanize.py shared_capture.py curriculum.py verify.py gen_dashboard.py; do
  grep -q '^import os' "$f" || sed -i '1i import os' "$f"
  sed -i 's/"127\.0\.0\.1:5555"/os.environ.get("ADB_TARGET", "127.0.0.1:5555")/g' "$f"
done
```

**Separate subproject (only if you deploy it):** `keep/config.py:34`
(`adb_serial`) and `keep/stream.py:17` have their own `127.0.0.1:5555` defaults —
edit them the same way if the `keep/` console is part of the deploy.

> Belt-and-braces: `docker-compose.yml` already sets `ADB_TARGET=redroid:5555`
> **and** passes `--device redroid:5555` to `run_bot.py`, so the main worker
> works even before Rule 1/2 land. Apply them so every module (live view,
> watchdog, recovery, dashboard, etc.) targets Redroid consistently.

---

## Risks — be honest about these

1. **Root / emulator detection.** Redroid is a rooted AOSP build in a container.
   Evony may run fine (it’s not a hardened banking app), but it *can* detect
   emulator/root signals and soft-block, shadow-ban, or crash-loop.
   - **Check:** after login, watch `docker compose logs -f redroid` and the live
     view for forced logouts / “unsupported device” dialogs over the first hour.
   - **Mitigate:** set realistic `androidboot.redroid_*` props, avoid superhuman
     tap cadence (the bot already humanizes input), one account per device.

2. **Software-GL performance.** `redroid_gpu_mode=guest` = SwiftShader CPU
   rendering (no GPU passthrough on CAX). Evony is GPU-heavy; expect low FPS,
   slow map panning, and higher CPU. CAX21 (4 Ampere cores) handles one account;
   don’t co-host several.
   - **Check:** `docker stats` (CPU steal/usage), and eyeball live-view smoothness.
   - **Mitigate:** cap the bot’s scan/render cadence; step up to CAX31 if the
     render loop starves the automation loop. `host` GPU mode needs a real GPU
     Hetzner CAX doesn’t provide — don’t expect it.

3. **binder module absent.** If the kernel/module isn’t loaded, Redroid never
   boots (`binder: transaction failed`).
   - **Check:** `ls /dev/binder` and `docker compose logs redroid`.
   - **Mitigate:** the cloud-init `modprobe`/`modules-load.d` handles it; re-run
     `modprobe binder_linux devices=binder,hwbinder,vndbinder` if needed. ashmem
     is **not** required — Redroid 11 uses `memfd` on the 24.04 (6.x) kernel.

4. **Split-container start/stop.** The manager’s Start/Stop buttons were written
   to `Popen`/`os.kill` a **local** process. Here the bot is a **separate
   container**, so those buttons won’t control it out of the box. Live view,
   config, roster, and accounts all work; treat the bot as always-on
   (`restart: always`). Wiring the buttons to the container needs a follow-up
   (Docker socket or a shared supervisor) — intentionally out of scope.

5. **No local vision-LLM.** `mlx`/`mlx-vlm` are Apple-only and excluded from the
   Linux image, so `run_bot.py --llm-fallback` won’t work on the VM. The CV/OCR
   loop is unaffected; wire a remote LLM API if you need the fallback.

6. **APK source & ToS.** Sideloading + automating Evony may violate its ToS
   (account risk is yours). Use a legit APK; keep credentials in the encrypted
   store (`EVONY_ENC_KEY`), never in plaintext or logs.

---

## Common commands
```bash
cd /opt/murderbot/deploy
docker compose ps
docker compose logs -f murderbot-bot
docker compose logs -f redroid
docker compose exec murderbot-manager sh -lc 'adb -s "$ADB_TARGET" devices'
docker compose restart murderbot-bot
docker compose down          # stop (keeps volumes/data)
docker compose down -v       # DESTROY everything incl. Android + db data
```
