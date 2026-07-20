# Orchestrator — the full-service bot (v2)

The original `train_to_1b.py` trains troops (see `README.md`). This layer generalizes
it into a **multi-feature engine** that replicates a full-service Evony bot — defense,
base development, daily upkeep, alliance, gathering, rallies, monsters — locally, on
your own account, **gem-safe and humanized**, with **local** vision (no API keys/cost).

## Run

```bash
cd evony-bot          # mise auto-activates .venv (python 3.14, see .mise.toml)
python run_bot.py               # training task (gem-safe) + macro schedule + watchdog
python run_bot.py --dry-run     # wire the whole stack, 0 ticks, no ADB (smoke test)
python run_bot.py --no-macro    # 24/7, no human rhythm (discouraged — kb/30)
python run_bot.py --llm-fallback  # escalate stuck states to the vision LLM
```

Exit codes: 0 done · 2 disconnect · 3 stopped (bot-tell/human) · 1 error.
Remote alerts: set `EVONY_NOTIFY_SLACK` (incoming-webhook URL); a macOS banner fires by
default (`EVONY_NOTIFY_MAC=0` to mute).

Env is **mise-managed**: `.mise.toml` pins python 3.14 and auto-activates a repo `.venv`
(`--system-site-packages`, inheriting the mise ML stack). Clean rebuild:
`python -m venv --system-site-packages .venv && pip install -r requirements.txt`.

## Loop

`orchestrator.run()` each tick: macro-schedule gate → screenshot → disconnect guard →
watchdog → run due tasks. Everything is a `Task(name, interval, priority, enabled, run)`.

| Layer | File | Role |
|---|---|---|
| Engine | `orchestrator.py` | scheduler + FSM disconnect-guard + watchdog + humanized `Ctx` |
| Scheduling | `scheduler.py` | time-based task queue (priority + interval) |
| Screen state | `screen_fsm.py`, `game_brain/` | which screen? + disconnect detection |
| Crash recovery | `watchdog.py` | app-gone / stuck-off-anchor → app_refresh |
| Humanize | `humanize.py` | jittered taps, WindMouse swipes, self-policing (kb/30) |
| Rhythm | `macro_schedule.py` | nightly sleep + micro-breaks — the top anti-ban layer (kb/30) |
| Alerts | `notify.py` | macOS banner + Slack/Discord on disconnect/bot-tell/crash |
| Launcher | `run_bot.py` | one command, rotating-file logging, graceful stop |
| Vision (text) | `ocr_read.py` | RapidOCR — numbers + text-button grounding (**primary**) |
| Vision (grounding) | `holo_vision.py` | Holo1.5-7B MLX — `ground(img,"the X button")→(x,y)`, `describe()` |
| Vision (reasoning) | `llm_agent.py` | JSON `decide()` fallback (ollama qwen2.5vl / anthropic) |

## Feature modules (built + unit-tested; disabled until live-wired)

Each = a tested **decision policy** + **pluggable perception**. The policy (what to do,
and the gem/march/stamina guards) is done and verified offline. Only `perceive()`/`act()`
— reading the screen and tapping — are `[LIVE-CAPTURE]` stubs that **raise loudly** rather
than tap blindly, so a mis-enabled task fails safe.

| Task | kb | Policy class | Guard (unit-tested) |
|---|---|---|---|
| `auto_shield` | 26 | `ShieldPolicy` | items only; already-covered→hold; no-items→notify human |
| `daily_collect` | 28 | `DailyCollector` | free actions; cooldowns; per-tick cap |
| `alliance` | 28 | `AlliancePolicy` | **never a gem donation tier** |
| `base_dev` | 27 | `BaseDevPolicy` | speedups = items only; else idle, never gem finish |
| `gather` | 23 | `GatherPolicy` | **always keeps `reserved_for_rallies` marches free** |
| `rally_join` | 24 | `RallyJoinPolicy` | joins capped by idle marches |
| `monster` | 25 | `MonsterPolicy` | respects `max_level` + `min_stamina_reserve` |

Run any module's self-test directly: `python auto_shield.py`, `python gather.py`, …

### Enable a feature on a clean session

1. Capture the UI templates for its screens (kb/31 maps the ~30 screens).
2. Implement `perceive(img) -> <Perception>` (OCR + templates + red-dot area) and
   `act(ctx, …)` — tap the UI path, **free/item controls only, never a gem control**.
   Use `holo_vision.ground(img, "the <button>")` where a template is brittle.
3. Pass them into the module's `make_task(perceive=…, act=…)` inside
   `orchestrator.default_tasks()` and set `enabled=True`. The policy + tests already
   cover every decision — you're only wiring eyes and fingers.

## Vision

`ocr_read` (RapidOCR) is **primary** — zoom-robust text/number reading.
`holo_vision` (Holo1.5-7B, local MLX on Apple Silicon, ~1.2s/call, free) is the
**grounding fallback** for icons/dense screens: downscale to ≤960 long-side before
inference, coords scaled back to device space (validated on the disconnect screen —
Quit/Restart grounded correctly). `llm_agent.decide()` is the last-resort JSON escalation.

## Invariants

- **Gem safety** — no task taps a gem-spend path; training/base-dev use item "Use";
  shields/daily/alliance use free/item paths. Every guard is unit-tested.
- **Disconnect** — the engine STOPS + notifies on the account-disconnect screen; it never
  taps Quit/Restart. Root fix: separate accounts from easy-bot.club (kb/32) so the login
  tug-of-war disappears.
- **Humanized + paced** — every tap jittered + self-policing; the macro schedule keeps the
  bot idle-on-timers, not grinding 24/7 (the real report-trigger, kb/30).
