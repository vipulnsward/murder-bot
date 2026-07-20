# OSS Bot Survey — Techniques to Adopt

Survey of open-source Evony / mobile-game bots to learn from. Bottom line: there is **no
strong, maintained OSS Evony:TKR bot** — the Evony repos are tiny (0–2★, single-purpose). The
real value is in adjacent-genre 4X bots (Rise of Kingdoms, Whiteout Survival) and mature
general frameworks (**ALAS**, **MaaFramework**). Our stack (Python + ADB + OpenCV +
Tesseract + BlueStacks) is exactly the common one, so the patterns port directly. Repos below
were read from their GitHub pages/READMEs, not cloned — validate before implementing.

## Evony-specific repos (all small; blueprint value only)

- **evsahal/TaskEnforcerX** (Python+PySide6, ~2024) — nearly our stack: BlueStacks 540p, ADB,
  bundled Tesseract; automates rally-join, map scan, training, black-market. **Steal:** a
  `calibration.xlsx` that externalizes screen coordinates/regions (re-tune resolution without
  touching code); SQLite for run/account state. https://github.com/evsahal/TaskEnforcerX
- **ctedescojr/EVONY-Bot** (Python) — generals "cultivate gold" loop. **Steal:** Tesseract
  digit whitelist `--psm 6 outputbase digits`; grayscale→threshold→contour pipeline; sentinel
  auto-pause on a `[0,0,0,0]` read. https://github.com/ctedescojr/EVONY-Bot
- **williamdai8/evony_automation_tools** (Python) — `evony_boss_queue_detector.py`,
  `evony_crash_detector.py`. **Steal:** a dedicated **crash/disconnect watchdog** that
  relaunches the game, and a boss-banner template watcher.
  https://github.com/williamdai8/evony_automation_tools
- **sonpiaz/4x-game-agent** (Python, 13★) — targets Evony/RoK/Lords Mobile. 5-layer hybrid:
  PaddleOCR → **FSM screen-classifier + auto popup-dismiss** → **World Model (persistent state
  + timer prediction)** → workflows → LLM-vision fallback; state re-read every 60s. **Steal:**
  the World-Model timer prediction and the FSM+popup-dismiss layer. https://github.com/sonpiaz/4x-game-agent
- DEAD (old Flash-era Evony, protocol-level, ignore): GargIT/AutoEvony-2.0, sonya75/pyEvony,
  NEAT-portal scripts.

## Best architecture references (general frameworks)

- **LmeSzinc/AzurLaneAutoScript (ALAS)** — the reference. Patterns to steal (all pure-Python):
  - **Two-queue, time-based scheduler:** `waiting_task` (future) + `pending_task` (ready),
    keyed on a `next_run` timestamp; a task raises `TaskEnd` on completion and `task_delay()`
    sets the next run from a per-task `SuccessInterval`. This is *exactly* our "train every N,
    refill when low, poll dashboard every M" need — replaces ad-hoc `sleep`s. **Highest-value
    pattern for us.**
  - **Priority queue with a pinned `Restart` task:** on crash/anomaly the orchestrator calls
    `task_call('Restart')` to relaunch the game before resuming.
  - **Exception-driven control flow** (`TaskEnd`/custom types decoded into retry/restart/pause).
  - **Config-as-code:** one YAML → generated typed config + WebUI schema + defaults.
  - **"Request human takeover"** on hitting a limit instead of failing silently (anti-ban
    hygiene). https://github.com/LmeSzinc/AzurLaneAutoScript
- **MaaXYZ/MaaFramework / MAA** — declarative JSON task pipeline (recognize→act→next, with
  conditional branches + error fallbacks) and **multiple recognition backends behind one
  interface**: template, **feature match (ORB, scale/rotation-invariant)**, OCR, **ONNX
  (YOLO)**, color match. The "beyond single-template" answer: fall back template → feature →
  color on low confidence. https://github.com/MaaXYZ/MaaFramework
- **openatx/uiautomator2** — tap by real Android view/element instead of pixel template where
  Evony exposes them; its `adbutils` layer is a solid maintained ADB library (reconnect,
  multi-device) if we outgrow raw `adb` subprocess. https://github.com/openatx/uiautomator2
- 4X analogs worth a look: **GabrielAgrela/OSROKBOT** (63★, clean state machine where each
  state points to the next on success/failure; captcha-pause), **kida14id/rok-rally-bot**
  (region-segmented OCR per rally slot + de-dup state tracking),
  **batazor/whiteout-survival-autopilot** (per-profile scheduling w/ TTL+priority, OCR-as-a-
  service, CEL rules engine, multi-account `devices.yaml`).

## Screenshot transport — our biggest quick win

We use `adb exec-out screencap` (~0.24s, sometimes up to ~1.5s) — the loop bottleneck. ALAS's
benchmark of alternatives (per frame):

| method | latency |
|--------|--------:|
| DroidCast_raw (raw Bitmap over socket, no root) | ~0.036s |
| aScreenCap | ~0.070s |
| ADB_nc (screencap piped over netcat) | ~0.125s |
| **plain adb screencap** | **~0.245s** |
| uiautomator2 screenshot | ~0.521s |

**hansalemaos/adbnativeblitz** (Python) gets "as fast as scrcpy" frames via a persistent
`adb screenrecord` H.264 stream decoded to NumPy — **README demos BlueStacks**, most drop-in.
Wrap whatever we pick behind a single `screenshot()` method so it's swappable.
https://github.com/hansalemaos/adbnativeblitz · https://github.com/Torther/DroidCast_raw

## Human-like input (anti-detection, behavioral only)

- **WindMouse** — physics-based pointer path: gravity toward target + random wind + capped
  velocity + near-target damping (overshoot/zero-in). Params `G_0=9, W_0=3, M_0=15, D_0=12`.
  Adapt to ADB by emitting the intermediate points as a multi-segment `input swipe` / motion
  sequence instead of a teleport-tap. https://ben.land/post/2021/04/25/windmouse-human-mouse-movement/
- Cheap complements: ±jitter on tap coordinates (~±2.5px), randomized inter-action delays,
  **shuffled task order each cycle** (RoK bots use this), and human-scale idle windows.

## Commercial bots (feature spec + anti-ban framing only)

GNBots-TKR / ESB-TKR / BoostBot etc. define the target roadmap: **auto start+join rally,
attack monsters/bosses, auto-shield/instant-bubble on incoming attack (killer feature),
full-map scan, multi-account (dozens)**. All frame anti-ban as **image-recognition + humanized
clicking, NOT memory/process injection** — the same class of bot we build. Evony appears less
captcha-aggressive than RoK, so likely detection is **behavioral** (superhuman timing, no idle,
identical repeated coords, 24/7 uptime) — mitigated by the randomization above.

## Techniques to adopt — ranked (value / effort), mapped to our stack

| # | Technique | Value | Effort | Maps to us |
|---|-----------|:----:|:-----:|-----------|
| 1 | Faster screenshot (`adbnativeblitz`/`DroidCast_raw`) behind a `screenshot()` shim | ★★★★★ | med | ~7–40× faster loop; BlueStacks-proven |
| 2 | ALAS two-queue time-based scheduler (`next_run`+`SuccessInterval`, `TaskEnd`) | ★★★★★ | med | replaces sleeps; fits train/refill/poll cadence |
| 3 | Region-segmented OCR + digit whitelist + preprocess | ★★★★☆ | low | segment food/troop/queue reads; big robustness, tiny effort |
| 4 | Human-like tap/timing randomization + shuffled task order | ★★★★☆ | med | anti-detection + fewer mis-taps on animated UI |
| 5 | Crash/disconnect watchdog + pinned `Restart` recovery task | ★★★★☆ | med | extends self-heal beyond food; handle `adb reconnect` |
| 6 | FSM "which screen am I on?" layer + auto popup-dismiss | ★★★★☆ | high | robustness beyond blind template taps; base for new features |
| 7 | Multi-scale + ORB feature-match fallback on low template confidence | ★★★☆☆ | med | handles resolution/zoom drift |
| 8 | Auto-gathering march loop (idle slot → map → node → dispatch → ETA → redispatch) | ★★★★☆ | high | the free path to fund 1B (see kb/14) |
| 9 | World-model timer prediction (schedule next check at batch/march ETA) | ★★★☆☆ | med | fewer screenshots; ties into #2 |
| 10 | Rally + monster/boss automation (detect → join/attack preset → confirm) | ★★★★☆ | high | highest-value new capability after gathering |
| 11 | Per-account profiles + externalized coordinate calibration | ★★★☆☆ | med | multi-account; re-tune ≠ code change |
| 12 | "Pause + notify human" (Discord/Telegram) on anomaly instead of blind retry | ★★★☆☆ | low | safer anti-ban posture |
| 13 | ONNX/YOLO screen classifier | ★★☆☆☆ | v.high | only if template matching becomes the limiter; needs labeled data |

**Near-term sequence:** 1 → 2 → 3 → 4 → 5 (all low/med effort, high value, pure additions to
our stack), then 6 (FSM) as the base for 8 (gather) and 10 (rally/monster). Defer 13.

Note: #8 (auto-gather) is the concrete enabler for the 1B food problem in `kb/13`/`kb/14`.
