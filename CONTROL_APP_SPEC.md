# Murder Bot — implementation-ready spec

> Companion to **CONTROL_APP_PLAN.md**. That doc sets direction; this one is the buildable
> spec: the exact config schema, the API contract, the control bridge, the frontend tree,
> the design system, and a phased ticket backlog. Nothing here changes the plan's decisions
> (FastAPI + React/TS/Vite + Tailwind/shadcn + WebSocket, single `config.yaml`, gem-lock
> surfaced and LOCKED, "Murder Bot" naming). It makes them concrete.

**Working name:** Murder Bot. **Runtime:** Python 3.14 in the repo `.venv` (mise), reusing
the existing modules directly. **Bind:** `127.0.0.1` by default; remote only via the existing
Cloudflare tunnel with auth.

Contents:
1. [Config schema](#1-config-schema-the-linchpin) — pydantic v2 model tree over `config.yaml`
2. [REST + WebSocket API contract](#2-rest--websocket-api-contract)
3. [Control bridge](#3-control-bridge)
4. [Frontend](#4-frontend)
5. [UI / design system](#5-ui--design-system)
6. [Phased backlog](#6-phased-backlog)
7. [Risks & open decisions](#7-risks--open-decisions)

Appendix: [A. Extracted real defaults](#appendix-a-extracted-real-defaults) · [B. Repo touch-map](#appendix-b-repo-touch-map)

---

## 1. Config schema (the linchpin)

Today every module owns its own `DEFAULTS` dict or policy dataclass. The refactor centralizes
them into one pydantic v2 tree serialized to `config.yaml`. Each module gains a
`from_config(cfg_section)` classmethod; `orchestrator.run(config)` loads the tree and constructs
the `Humanizer`, `MacroSchedule`, `Scheduler`, and each `Task` from it. The app validates every
edit against this tree, so the UI and the bot share one source of truth.

### 1.1 Conventions

- **Ranges** (e.g. `delay_between_taps = (0.30, 0.80)` in `humanize.DEFAULTS`) become a small
  `Range` submodel `{lo, hi}` with `hi >= lo` enforced — clearer in YAML and in the UI than a
  bare 2-tuple, and losslessly convertible back to the tuple the modules expect via
  `.as_tuple()`.
- **Every task section** carries the scheduler triple `enabled: bool`, `interval: float` (s),
  `priority: int`, plus its policy fields. Lower `priority` number = runs first (matches
  `scheduler._ready`, which heapifies on `priority` ascending).
- **`gem_spend`** is a real frozen field (`Field(frozen=True)`) *and* is guarded by a validator
  that raises on any truthy value — a hand-edited `config.yaml: safety.gem_spend: true` fails to
  load at startup, and a `PUT /api/config` that sets it returns `422`. The lock lives in the
  schema, not the UI.
- Defaults below are copied verbatim from the code (see [Appendix A](#appendix-a-extracted-real-defaults)).

### 1.2 Model tree

```python
# config_schema.py  — pydantic v2. The single source of truth for the bot + the app.
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

CONFIG_VERSION = 1

class Range(BaseModel):
    """An inclusive [lo, hi] draw range; serializes as {lo, hi} in YAML."""
    model_config = ConfigDict(extra="forbid")
    lo: float
    hi: float
    @model_validator(mode="after")
    def _ordered(self):
        if self.hi < self.lo:
            raise ValueError(f"range hi ({self.hi}) < lo ({self.lo})")
        return self
    def as_tuple(self) -> tuple[float, float]:
        return (self.lo, self.hi)

# ── device / fleet ───────────────────────────────────────────────────────────
class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    adb_serial: str = "127.0.0.1:5555"     # orchestrator.DEVICE default
    enabled: bool = False
    features: list[str] = Field(default_factory=list)   # task names active for this account
    notes: str = ""                                     # e.g. "separate acct from easy-bot.club (kb/32)"

class Fleet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_account: str = "main"           # which account the single running engine drives now
    accounts: list[Account] = Field(default_factory=lambda: [Account(name="main", enabled=True)])
    @model_validator(mode="after")
    def _active_exists(self):
        names = {a.name for a in self.accounts}
        if self.active_account not in names:
            raise ValueError(f"active_account {self.active_account!r} not in accounts {names}")
        return self

# ── safety (LOCKED invariants) ───────────────────────────────────────────────
class Safety(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    gem_spend: bool = Field(default=False, frozen=True)   # 🔒 NEVER true — see validator
    disconnect_policy: str = "stop_only"   # literal; only "stop_only" is accepted
    humanize_required: bool = Field(default=True, frozen=True)
    macro_required: bool = True            # macro schedule on by default (kb/30)
    reclaim_requires_confirm: bool = Field(default=True, frozen=True)
    @field_validator("gem_spend")
    @classmethod
    def _no_gems(cls, v):
        if v:
            raise ValueError("gem_spend is a locked invariant and can never be true")
        return v
    @field_validator("disconnect_policy")
    @classmethod
    def _only_stop(cls, v):
        if v != "stop_only":
            raise ValueError("disconnect_policy is locked to 'stop_only' (never taps Quit/Restart)")
        return v

# ── humanize  (humanize.DEFAULTS) ────────────────────────────────────────────
class WindMouse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    G0: float = 9.0
    W0: float = 3.0
    M0: float = 15.0
    D0: float = 12.0

class Humanize(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jitter_samples: int = 3
    tap_box_shrink_px: int = 6
    delay_between_taps: Range = Range(lo=0.30, hi=0.80)
    delay_after_menu:   Range = Range(lo=0.80, hi=2.50)
    delay_between_tasks: Range = Range(lo=3.0, hi=15.0)
    reaction_floor: float = 0.25
    tap_duration_ms:   Range = Range(lo=40, hi=120)
    deliberate_tap_ms: Range = Range(lo=150, hi=400)
    deliberate_tap_prob: float = Field(default=0.10, ge=0.0, le=1.0)
    windmouse: WindMouse = WindMouse()
    swipe_segment_px: int = 12
    click_window: int = 15
    same_button_max: int = 12   # self-policing tell threshold (TooManyClicks)
    alt_button_max: int = 6

# ── macro_schedule  (macro_schedule.DEFAULTS) ────────────────────────────────
class MacroSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True                        # False == run 24/7 (discouraged, kb/30)
    sleep_len_h:    Range = Range(lo=6.0, hi=9.0)
    sleep_anchor_h: Range = Range(lo=1.0, hi=4.0)
    micro_break_every_min: Range = Range(lo=20.0, hi=60.0)
    micro_break_len_min:   Range = Range(lo=2.0, hi=8.0)
    idle_poll_cap_s: float = 300.0
    seed_salt: int = 0                          # MacroSchedule(seed_salt=...) — per-account variety

# ── tasks (each = scheduler triple + its policy fields) ──────────────────────
class TaskBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    interval: float = Field(gt=0)
    priority: int
    jitter: float = 0.0        # scheduler.Task jitter fraction

class TrainingTask(TaskBase):
    enabled: bool = True
    interval: float = 6.0
    priority: int = 10
    target_own: int = 1_000_000_000     # config.TARGET_OWN
    train_qty:  int = 269_228           # config.TRAIN_QTY
    use_finish_all: bool = True         # config.USE_FINISH_ALL

class AutoShieldTask(TaskBase):
    enabled: bool = False
    interval: float = 20.0
    priority: int = 1                   # survival gate — highest (lowest number)
    react_within_s: float = 900.0       # 15*60
    reshield_margin_s: float = 600.0    # 10*60
    desired_cover_s: float = 28_800.0   # 8*3600
    proactive: bool = False

class DailySource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    min_interval_s: int
    priority: int
    enabled: bool = True

class DailyCollectTask(TaskBase):
    enabled: bool = False
    interval: float = 600.0
    priority: int = 30
    max_per_tick: int = 3
    sources: list[DailySource] = Field(default_factory=lambda: [
        DailySource(key="alliance_help",     min_interval_s=120,   priority=9),
        DailySource(key="city_resources",    min_interval_s=600,   priority=8),
        DailySource(key="mail",              min_interval_s=300,   priority=7),
        DailySource(key="tax",               min_interval_s=3600,  priority=7),
        DailySource(key="daily_quest_chest", min_interval_s=43200, priority=7),
        DailySource(key="bounty",            min_interval_s=1800,  priority=6),
        DailySource(key="eggs",              min_interval_s=3600,  priority=6),
        DailySource(key="patrol",            min_interval_s=3600,  priority=6),
        DailySource(key="wheel",             min_interval_s=86400, priority=6),
        DailySource(key="free_chest",        min_interval_s=14400, priority=5),
    ])

class AllianceTask(TaskBase):
    enabled: bool = False
    interval: float = 1800.0
    priority: int = 25
    donations_per_day: int = 20
    help_cooldown_s: float = 60.0
    # allowed_donation_costs is NOT user-editable: ("free","resource") is a gem-safe invariant.

class BaseDevTask(TaskBase):
    enabled: bool = False
    interval: float = 300.0
    priority: int = 20
    preferred_speedup_item: str | None = None
    min_speedup_remaining_s: float = 300.0    # 5*60

class GatherTask(TaskBase):
    enabled: bool = False
    interval: float = 120.0
    priority: int = 15
    reserved_for_rallies: int = Field(default=1, ge=0)   # ALWAYS-free march guard (kb/23)
    preferred_min_level: int = 1
    preferred_resource_types: tuple[str, ...] = ("ore", "stone", "lumber", "food")

class RallyJoinTask(TaskBase):
    enabled: bool = False
    interval: float = 60.0
    priority: int = 12
    only_boss: bool = True
    max_seconds_left: int = 300
    require_feasible: bool = True
    reserved_free_marches: int = Field(default=0, ge=0)

class MonsterTask(TaskBase):
    enabled: bool = False
    interval: float = 90.0
    priority: int = 14
    preferred_types: tuple[str, ...] = ()      # e.g. ("Ymir","Cerberus")
    max_level: int = 0
    min_stamina_reserve: int = 0

class Tasks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    training:      TrainingTask     = TrainingTask()
    auto_shield:   AutoShieldTask   = AutoShieldTask()
    daily_collect: DailyCollectTask = DailyCollectTask()
    alliance:      AllianceTask     = AllianceTask()
    base_dev:      BaseDevTask      = BaseDevTask()
    gather:        GatherTask       = GatherTask()
    rally_join:    RallyJoinTask    = RallyJoinTask()
    monster:       MonsterTask      = MonsterTask()

# ── vision ───────────────────────────────────────────────────────────────────
class Vision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ocr_first: bool = True                                # RapidOCR is primary (ORCHESTRATOR.md)
    holo_model: str = "mlx-community/holo1.5-7b-mlx"      # holo_vision._REPO
    holo_fallback_on: bool = False                        # screen_fsm.identify(holo_fallback=)
    holo_max_long_side: int = 960                         # holo_vision downscale cap
    holo_max_tokens: int = 256
    template_match_threshold: float = 0.82                # config.MATCH_THRESHOLD
    llm_fallback: bool = False                            # orchestrator.run(llm_fallback=)

# ── notify  (notify.py env channels) ─────────────────────────────────────────
class Notify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mac_banner: bool = True                    # EVONY_NOTIFY_MAC (default on)
    slack_webhook: str | None = None           # EVONY_NOTIFY_SLACK
    discord_webhook: str | None = None         # EVONY_NOTIFY_DISCORD

# ── engine (orchestrator.run parameters) ─────────────────────────────────────
class Engine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stuck_threshold: int = 6                    # orchestrator.run(stuck_threshold=)
    watchdog: bool = True
    idle_cap_s: float | None = None
    scheduler_retry_delay_s: float = 30.0       # scheduler.Scheduler(retry_delay=)

# ── root ─────────────────────────────────────────────────────────────────────
class KeepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = CONFIG_VERSION
    fleet:     Fleet     = Fleet()
    safety:    Safety    = Safety()
    humanize:  Humanize  = Humanize()
    macro:     MacroSchedule = MacroSchedule()
    tasks:     Tasks     = Tasks()
    vision:    Vision    = Vision()
    notify:    Notify    = Notify()
    engine:    Engine    = Engine()
```

### 1.3 `config.yaml` (rendered defaults, abbreviated)

```yaml
version: 1
fleet:
  active_account: main
  accounts:
    - {name: main, adb_serial: "127.0.0.1:5555", enabled: true, features: [training], notes: ""}
safety:
  gem_spend: false          # 🔒 LOCKED — validator rejects true
  disconnect_policy: stop_only
  humanize_required: true
  macro_required: true
humanize:
  delay_between_taps: {lo: 0.30, hi: 0.80}
  windmouse: {G0: 9.0, W0: 3.0, M0: 15.0, D0: 12.0}
  same_button_max: 12
  # … (full list in Appendix A)
macro:
  enabled: true
  sleep_len_h: {lo: 6.0, hi: 9.0}
  sleep_anchor_h: {lo: 1.0, hi: 4.0}
tasks:
  training:    {enabled: true,  interval: 6,    priority: 10, target_own: 1000000000, train_qty: 269228}
  auto_shield: {enabled: false, interval: 20,   priority: 1,  react_within_s: 900, desired_cover_s: 28800}
  gather:      {enabled: false, interval: 120,  priority: 15, reserved_for_rallies: 1}
  # … remaining tasks
vision: {ocr_first: true, holo_model: "mlx-community/holo1.5-7b-mlx", holo_fallback_on: false}
notify: {mac_banner: true, slack_webhook: null, discord_webhook: null}
engine: {stuck_threshold: 6, watchdog: true, scheduler_retry_delay_s: 30}
```

### 1.4 Module `from_config` wiring (refactor contract)

| Module | Today | After refactor |
|---|---|---|
| `humanize.Humanizer(cfg=…)` | already takes a `cfg` dict overlaying `DEFAULTS` | `Humanizer(cfg=config.humanize.to_legacy_dict())` — a thin adapter that turns `Range` back into tuples |
| `macro_schedule.MacroSchedule(cfg=…, seed_salt=…)` | takes `cfg` dict + `seed_salt` | build from `config.macro` |
| `ShieldPolicy(...)`, `AlliancePolicy(...)`, `BaseDevPolicy(...)`, `GatherPolicy(...)`, `RallyJoinPolicy(...)`, `MonsterPolicy(...)` | constructor kwargs | add `Policy.from_config(cfg.tasks.<name>)` classmethod, unchanged decision logic |
| `DailyCollector(sources=…, max_per_tick=…)` | takes both | `from_config(cfg.tasks.daily_collect)` |
| `orchestrator.default_tasks()` | hard-codes intervals/priorities/enabled | reads `cfg.tasks.<name>.{enabled,interval,priority}` and passes `policy=…from_config(...)` into each `make_task(...)` |
| `orchestrator.run(...)` | positional kwargs | `run(config: KeepConfig, control: ControlChannel)` |
| `notify.notify(...)` | reads env vars | keep env as fallback; the bridge exports `config.notify` into env before spawning, or passes an explicit `env=` dict |

The **decision policies and their unit tests do not change** — only how they are *constructed*.
The `[LIVE-CAPTURE]` `perceive`/`act` stubs stay loud (`NotImplementedError`) so a mis-enabled
task still fails safe.

---

## 2. REST + WebSocket API contract

All JSON, `application/json`. Base path `/api`. Errors use a consistent envelope:

```json
{ "error": { "code": "validation_error", "message": "…", "details": [ … ] } }
```

Standard codes: `400 bad_request`, `404 not_found`, `409 conflict` (e.g. run-now while paused),
`422 validation_error` (pydantic / gem-lock), `423 locked` (gem_spend or disconnect_policy
tamper), `500 internal`, `503 engine_unavailable` (ADB/device down).

### 2.1 Config

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/config` | full validated config as JSON |
| `GET` | `/api/config/raw` | raw `config.yaml` text (for the Raw-YAML view) |
| `PUT` | `/api/config` | replace whole config; validate; version-snapshot; hot-reload |
| `PATCH` | `/api/config` | JSON-merge-patch a subtree (e.g. one task); validate; hot-reload |
| `POST` | `/api/config/validate` | dry-run validate a candidate config, no write |
| `GET` | `/api/config/versions` | list snapshot ids `[{id, ts, note}]` |
| `POST` | `/api/config/revert` | `{version_id}` → restore a snapshot; hot-reload |

**`PUT /api/config`**
- Request: the full `KeepConfig` JSON.
- Response `200`: `{ "config": {…}, "version_id": "2026-07-21T14:03:11Z", "reload": "queued" }`
- Errors: `422` on any pydantic failure (body lists `details[]` with `loc`/`msg`);
  `423` specifically when `safety.gem_spend` or `safety.disconnect_policy` is tampered with,
  with `message: "gem_spend is locked"`.

**`PATCH /api/config`** — merge-patch, e.g. `{ "tasks": { "gather": { "reserved_for_rallies": 2 } } }`.
Same responses. The server re-validates the *merged* whole (so a patch can't smuggle in an
invalid cross-field combo).

### 2.2 Tasks

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/tasks` | list all 8 tasks with runtime state |
| `POST` | `/api/tasks/{name}/toggle` | flip `enabled` (persists to config + hot-reload) |
| `POST` | `/api/tasks/{name}/run-now` | force the task to run at the next tick |

**`GET /api/tasks`** → `200`:
```json
{ "tasks": [
  { "name": "training", "enabled": true, "interval": 6, "priority": 10,
    "wired": true, "runs": 294, "fails": 0,
    "last_run": "2026-07-21T14:02:58Z", "next_run": "2026-07-21T14:03:04Z",
    "state": "idle", "guard": {"target_own": 1000000000} },
  { "name": "gather", "enabled": false, "interval": 120, "priority": 15,
    "wired": false, "runs": 0, "fails": 0, "last_run": null, "next_run": null,
    "state": "not_wired", "guard": {"reserved_for_rallies": 1} }
]}
```
- `wired`: whether `perceive`/`act` are implemented (else the `[LIVE-CAPTURE]` stub) — drives the
  "(wire)" badge.
- `guard`: the safety-relevant fields surfaced on the row (gather `reserved_for_rallies`, monster
  caps, shield cover, etc.).

**`POST /api/tasks/{name}/toggle`** → `200 {"name":"gather","enabled":true,"reload":"queued"}`.
`404` on unknown name. `409` if enabling an unwired task while the engine is running and
`safety`/policy forbids running unwired (default: allowed, but the task will raise and the engine
notifies — the response includes `"warning":"task not wired; will fail loudly until perceive/act implemented"`).

**`POST /api/tasks/{name}/run-now`** → `202 {"name":"training","scheduled_for":"next_tick"}`.
`409 {"error":{"code":"conflict","message":"engine paused"}}` when paused/stopped.

### 2.3 Status

**`GET /api/status`** → `200`:
```json
{
  "engine": "running",                       // running | paused | stopped | disconnected | starting
  "account": "main", "device": "127.0.0.1:5555", "device_ok": true,
  "current_task": "training",
  "macro": { "state": "active", "seconds_until_change": 1840 },  // active | micro_break | sleep
  "screen": "training_idle",                 // last screen_fsm.identify() label
  "uptime_s": 44192, "ticks": 73810,
  "counts": { "own": 501481135, "food": 629000000, "gems": 4321, "batches": 294, "rate_per_min": 501234 },
  "safety": { "gem_spend": false, "disconnect_safe": true, "humanized": true, "macro_on": true },
  "last_event": { "ts": "2026-07-21T02:14:03Z", "level": "info", "msg": "macro schedule -> sleep" },
  "reload_pending": false
}
```
`503` with `engine_unavailable` if ADB is unreachable (`device_ok:false`).

### 2.4 Control

**`POST /api/control`** — body `{ "action": "start" | "pause" | "resume" | "panic_stop" | "reclaim_session", "confirm": false }`.

| action | effect | guard |
|---|---|---|
| `start` | construct engine from config, begin loop | `409` if already running |
| `pause` | idle at next tick boundary, no taps, session preserved | — |
| `resume` | leave pause | `409` if not paused |
| `panic_stop` | set stop event; loop returns `"stopped"`; **never taps Quit/Restart** | — |
| `reclaim_session` | after a disconnect, tap Restart to re-enter the account | **requires `confirm:true`** → `428 {"error":{"code":"confirm_required"}}` otherwise |

Response `200 {"engine":"paused","action":"pause"}`. `panic_stop` is idempotent (calling it while
stopped is `200`).

### 2.5 Logs / events / decisions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/logs?since=&level=&q=&limit=` | tail the rotating run log (ring buffer) |
| `GET` | `/api/events?since=&limit=` | notification history (disconnect/bot-tell/crash/attack) |
| `GET` | `/api/decisions?since=&limit=` | `llm_decisions.jsonl` entries |

**`GET /api/logs`** → `200`:
```json
{ "lines": [
  { "ts": "2026-07-21T14:02:58Z", "level": "info", "task": "training", "msg": "batch 294 ok own=501,481,135" }
], "cursor": "1721570578.412" }
```
`level` ∈ `debug|info|warn|alert`. `q` is a substring filter. `since` is the last `cursor`.
`events` items carry `{ts, level, channel_sent:["mac","slack"], msg}` mirroring `notify.notify`
return values. `404` never; empty ranges return `{"lines":[], "cursor":…}`.

### 2.6 Vision

All operate on **the latest captured frame** by default (shared frame buffer — see §3), or an
uploaded image via `multipart/form-data` `frame=@file`.

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/api/vision/ocr` | `{ "box": [x1,y1,x2,y2] \| null, "mode": "all"\|"number"\|"button", "label": "use" }` | OCR results |
| `POST` | `/api/vision/ground` | `{ "instruction": "the Train button" }` | grounded point |
| `POST` | `/api/vision/classify` | `{ "holo": true }` | screen label |

**`/api/vision/ocr`** (`mode:"all"`, from `ocr_read.read_all`) → `200`:
```json
{ "engine": "rapidocr", "results": [ { "text": "Train", "center": [540, 1588], "conf": 0.97 } ],
  "took_ms": 412 }
```
`mode:"number"` → `{ "value": 501481135, "took_ms": … }` (`ocr_read.read_number`);
`mode:"button"` → `{ "center": [540,1588] | null }` (`ocr_read.find_button`).

**`/api/vision/ground`** (`holo_vision.ground` via `perception.ground`) → `200`:
```json
{ "point": [714, 1134], "instruction": "the Train button", "engine": "holo1.5-7b-mlx", "took_ms": 1180 }
```
`point:null` when nothing grounded. First call is slow (lazy model load ~model-load-seconds);
response includes `"model_loaded": true|false` so the UI can show a "loading model…" state.

**`/api/vision/classify`** (`screen_fsm.identify` then `screen_id.classify` if `holo:true`) → `200`:
```json
{ "screen": "training_idle", "source": "template", "score": 0.93,
  "holo": { "label": "training_barracks", "description": "…", "score": 3 } }
```
`source` ∈ `template|holo`. All vision endpoints `503` if ADB can't produce a frame and none was
uploaded.

### 2.7 Templates (the `[LIVE-CAPTURE]` accelerator)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/templates` | list `templates/*.png` with size + preview URL |
| `GET` | `/api/templates/{name}.png` | raw PNG bytes |
| `POST` | `/api/templates/capture` | crop the current frame → save a named template |
| `DELETE` | `/api/templates/{name}` | remove a template (versioned trash, not hard delete) |

**`GET /api/templates`** → `200`:
```json
{ "dir": "templates/", "templates": [
  { "name": "train_btn_idle", "w": 260, "h": 96, "bytes": 47693, "used_by": ["training_idle"] }
]}
```
`used_by` cross-references `screen_fsm.ANCHOR_ORDER`.

**`POST /api/templates/capture`** — `{ "name": "shield_use_btn", "box": [x1,y1,x2,y2], "from": "current" }`
→ `201 { "name": "shield_use_btn", "path": "templates/shield_use_btn.png", "w":…, "h":… }`.
`409` if the name exists (pass `"overwrite": true` to replace, which snapshots the old one).
`422` if `box` is out of frame bounds.

### 2.8 WebSocket channels

| Path | Payload cadence | Message shape |
|---|---|---|
| `/ws/status` | on change + 2s heartbeat | the `GET /api/status` body (delta or full) |
| `/ws/logs` | as lines append | one `logs.lines[]` item per message; supports `?level=&q=` query |
| `/ws/screen` | frame push at `vision`-configured FPS | see below |

**`/ws/screen`** — two modes (client picks via `?mode=`):
- `mode=mjpeg` (default): the socket proxies the existing `live_stream.py` MJPEG so the front end
  can reuse it directly (or the front end just points an `<img>`/`<video>` at the MJPEG endpoint
  and skips the socket).
- `mode=frame`: base64 JPEG + metadata per message:
  `{ "seq": 40213, "ts": "…", "jpg_b64": "…", "screen": "training_idle", "overlay": {"ground": [714,1134]} }`
  so overlays (FSM label, last grounding point) ride with the frame.

Server→client control frames on `/ws/status`: `{ "type": "reload", "version_id": "…" }` when a
config reload lands, and `{ "type": "engine", "state": "disconnected" }` on state transitions, so
the UI reacts without polling.

---

## 3. Control bridge

The bridge is the object that owns the orchestrator lifecycle and mediates between async FastAPI
handlers and the blocking `orchestrator.run()` loop.

### 3.1 Thread, not subprocess

Run the orchestrator in **a dedicated daemon thread inside the FastAPI process**, not a
subprocess. Rationale:

- **Shared heavy state.** Holo1.5 (MLX, ~7B) and RapidOCR are lazy singletons that cost seconds
  and hundreds of MB to load. A subprocess would load a *second* copy for the vision endpoints;
  a thread lets `/api/vision/*` reuse the same in-memory models the engine already loaded.
- **Direct imports.** The plan's principle is "reuse, don't rewrite" — the bridge `import`s the
  policies and vision modules directly and constructs them from the config tree.
- **One game session, one ADB device.** There is exactly one emulator; a thread naturally
  serializes access to it. Subprocess IPC would add a marshaling layer for no benefit.

The trade-off is the GIL and blocking calls — addressed in §3.4.

### 3.2 Shared state object

```python
# control_bridge.py (sketch — structure, not final code)
class ControlChannel:
    def __init__(self):
        self._stop   = threading.Event()   # panic_stop
        self._pause  = threading.Event()   # pause/resume
        self._run_now = queue.Queue()      # task names forced to run next tick
        self._reload = None                # KeepConfig staged for tick-boundary swap
        self._lock   = threading.Lock()
        self.state   = "stopped"           # running|paused|stopped|disconnected|starting
        self.frame   = None                # latest BGR frame (shared with vision endpoints)
        self.status  = {}                  # last status dict, pushed to /ws/status
        self.logbuf  = collections.deque(maxlen=5000)  # ring buffer for /api/logs + /ws/logs

    # called by API handlers (async side)
    def pause(self):  self._pause.set()
    def resume(self): self._pause.clear()
    def panic_stop(self): self._stop.set()
    def request_run_now(self, name): self._run_now.put(name)
    def stage_reload(self, cfg):
        with self._lock: self._reload = cfg

    # called by the loop (engine thread) at the tick boundary
    def should_stop(self):  return self._stop.is_set()
    def should_pause(self): return self._pause.is_set()
    def take_reload(self):
        with self._lock:
            cfg, self._reload = self._reload, None
            return cfg
```

`orchestrator.run(config, control)` is refactored to consult `control` each tick (it already
accepts `should_stop`; add pause, reload, and run-now).

### 3.3 Tick-boundary hot reload (no session loss)

The reload is applied **at the top of the loop, between ticks**, never mid-tap:

```
loop tick:
  if control.should_stop():  return "stopped"          # panic
  cfg = control.take_reload()
  if cfg is not None:
      rebuild_from(cfg)   # new Scheduler tasks, MacroSchedule, Humanizer cfg — see below
  if control.should_pause():
      control.state = "paused"; idle_without_tapping(); continue   # session preserved
  if macro not active: idle; continue
  frame = screencap();  control.frame = frame           # publish for vision endpoints
  if disconnect(frame): return "disconnect"
  watchdog(frame)
  name = control.pop_run_now() or scheduler.pick_due()
  run(name)
```

`rebuild_from(cfg)`:
- **Tasks**: recompute each `Task.enabled/interval/priority` and rebuild policies via
  `from_config`. Enabling/disabling adds/removes from the `Scheduler`. Interval/priority changes
  reschedule in place. **The game session, ADB connection, and loaded models are untouched.**
- **Humanize**: replace `CTX.hz.cfg` with the new dict (cheap; next tap uses it).
- **Macro**: replace the `MacroSchedule` instance (day segments recompute lazily).
- **Requires-restart set**: `fleet.active_account` / `adb_serial` changes *do* change the session
  (a different device/account), so those are flagged `requires_restart:true` in the `PUT` response
  and the UI shows "apply needs an engine restart" instead of silently hot-swapping.

Because a reload is a whole validated `KeepConfig`, there is no partial-apply window: the loop
swaps atomically at the boundary.

### 3.4 GIL / vision contention

Two things must never run concurrently against one device or one model:

- **ADB frames.** Only the engine thread calls `fast_screenshot.grab`. Vision endpoints read
  `control.frame` (the last published frame) rather than grabbing their own — no ADB contention,
  and the frame the operator OCRs is the frame the engine just acted on.
- **Holo inference.** Wrap Holo/OCR calls in a single-slot `asyncio.Lock` (or a one-worker
  `ThreadPoolExecutor`) so a `/api/vision/ground` request and an engine `ctx.find(...)` can't
  drive two MLX generations at once. FastAPI handlers `await run_in_executor(vision_pool, …)` so
  the event loop stays responsive during the ~1.2s inference.

The engine thread holds the GIL during CPU-bound OpenCV template matching; those calls are short
(single `matchTemplate`), so status/log WebSockets stay smooth. If it ever bites, move template
matching to a worker too.

### 3.5 Gem-lock enforcement (server-side, defense in depth)

Four independent layers, any one of which stops a gem spend:
1. **Schema** — `safety.gem_spend` is `frozen=True` + validator; unloadable if true (`config.yaml`
   startup or `PUT` → `423`).
2. **Loaders** — `AlliancePolicy.from_config` never exposes `allowed_donation_costs` as editable;
   it stays `("free","resource")`. Base-dev / shield / daily loaders only wire item/free paths.
3. **Policies** — the decision logic itself refuses gem tiers (already unit-tested: alliance
   refuses `"gem"`, base_dev never emits finish/instant, shields use item "Use", daily is
   free-only).
4. **Act stubs** — `[LIVE-CAPTURE]` `act()` implementations must tap only item/free controls;
   `screen_fsm.ensure_training` explicitly closes the speedup modal rather than tapping Finish-All.

The UI's Safety page reads layer 1 as a read-only badge; it exposes **no control** that can flip
it.

### 3.6 Startup / shutdown

- **Startup**: FastAPI lifespan loads `config.yaml` → `KeepConfig` (fail fast on invalid),
  constructs the `ControlChannel`, and — if `engine.autostart` (a settings flag) — spawns the
  engine thread. Otherwise the engine starts on `POST /api/control {start}`.
- **Shutdown**: set stop event, join the thread with a timeout, flush the log ring buffer. Never
  send a Quit/Restart tap on shutdown.

---

## 4. Frontend

React + TypeScript + Vite, Tailwind + shadcn/ui (Radix). **React Query** for all REST (caching +
optimistic config edits), a **`useWS(channel)`** hook for the three sockets. No Redux — server
state lives in React Query, ephemeral UI state in local `useState`/`zustand` if needed.

### 4.1 Route / component tree

```
<App>                         // AppShell: left icon-rail + <StatusStrip/> + <Outlet/>
├─ /            <Dashboard>   StatusCard, SafetyBadges, LiveThumb, MiniCharts, EventsFeed, PanicStop
├─ /live        <Live>        LiveScreen(MJPEG), FsmOverlay, GroundingProbe, DevTapPad(gem-guarded)
├─ /tasks       <Tasks>       TaskTable → TaskRow → <ConfigForm> (policy params, Advanced fold)
├─ /config      <Config>      SectionNav, <ConfigForm> per section, DiffBar, RawYamlView, RevertMenu
├─ /schedule    <Schedule>    ScheduleTimeline (24h), SleepEditor, BreakCadenceEditor
├─ /fleet       <Fleet>       AccountList → AccountCard (device, features, status)
├─ /logs        <Logs>        LogTail(useWS), LevelFilter, SearchBox, EventsTab, DecisionsTab
├─ /vision      <Vision>      FrameCanvas, OcrPanel, GroundPanel, ClassifyPanel, TemplateCapture
├─ /knowledge   <Knowledge>   KbSidebar (kb/*.md list), MarkdownView
└─ /safety      <Safety>      InvariantList, GemLockBadge, DisconnectPolicyCard, PanicStop
```

### 4.2 Shared components

| Component | Role | Data source |
|---|---|---|
| `StatusStrip` | top bar: engine dot, current task, macro state, safety badges, **PanicStop** | `useWS('/ws/status')` |
| `TaskTable` / `TaskRow` | 8 tasks, toggle, interval/priority, last/next run, expandable policy form | `GET /api/tasks`, `POST …/toggle`, `…/run-now` |
| `ConfigForm` | schema-driven form (labels, types, ranges); inline validation; Advanced fold | `GET /api/config` + `POST /api/config/validate` |
| `ScheduleTimeline` | 24h SVG band: sleep block + micro-breaks, live "now" marker | `config.macro` + `status.macro` |
| `LiveScreen` | MJPEG `<img>`/`<video>` + click-to-ground overlay | `live_stream` MJPEG / `/ws/screen` |
| `LogTail` | virtualized live log list, level color, follow-tail toggle | `useWS('/ws/logs')` + `GET /api/logs` |
| `SafetyBadges` | 🔒 no-gems · disconnect-safe · humanized · macro-on | `status.safety` |
| `PanicStop` | big red button, confirm-dialog-free single click | `POST /api/control {panic_stop}` |

### 4.3 State approach

- **Reads**: `useQuery(['config'])`, `useQuery(['tasks'])`, etc. `status`, `logs`, `screen` come
  from `useWS` and are mirrored into the query cache so components read one source.
- **Writes**: `useMutation` with **optimistic update** for config edits + task toggles; on `422`
  roll back and surface `details[]` inline on the offending field. A dirty `ConfigForm` shows a
  `DiffBar` (changed fields) with **Save / Revert**; Save calls `PATCH /api/config`.
- **`useWS(channel)`**: opens the socket, auto-reconnects with backoff, exposes
  `{data, status:'open'|'connecting'|'closed'}`. On a `{type:"reload"}` control frame it
  invalidates `['config']` so the UI re-pulls.
- **Gem-lock in UI**: the Safety toggle for gems is rendered **disabled with a lock icon**; there
  is no code path that issues a mutation setting `gem_spend:true` (and the server would `423` it
  anyway).

### 4.4 Per-page wireframes

**Dashboard** `/`
```
┌────────────────────────────────────────────────────────────────────┐
│ ● Running · Training · 🔒 gem-safe · humanized · macro:active [Panic⏹]│
├──────────────────────────────┬─────────────────────────────────────┤
│ Keep · Warriors T2           │  ┌─ live ───────────────┐            │
│ Own 501,481,135              │  │   [emulator thumb]    │  screen:  │
│ Food 629M   ETA —            │  │                       │  training │
│ Batches 294  Rate 501K/min   │  └───────────────────────┘  _idle    │
│ ┌ mini charts ─────────────┐ │  ┌ Recent events ─────────────────┐  │
│ │ own ▁▂▃▄▅▆▇  food ▇▆▅▄▃  │ │  │ 02:14  macro → sleep           │  │
│ └──────────────────────────┘ │  │ 01:50  micro-break             │  │
│                              │  │ 00:03  batch 293 ok            │  │
└──────────────────────────────┴──┴────────────────────────────────┴──┘
```

**Live** `/live`
```
┌──────────────────────────── Live ──────────────────────────────────┐
│ ┌──────────────── MJPEG stream ────────────────┐  FSM: training_idle │
│ │                                              │  Holo: (off) [toggle]│
│ │      [ click a spot → "what's here?" ]       │  Last ground:        │
│ │        · overlay: ⌖ (714,1134)               │   (714,1134) "Train" │
│ │                                              │  ── Dev tap (guarded)│
│ └──────────────────────────────────────────────┘   x[   ] y[   ] Tap │
│ Probe: [ the Train button            ] (Ground)     🔒 no gem controls│
└─────────────────────────────────────────────────────────────────────┘
```

**Tasks** `/tasks`
```
┌───────────────────────────── Tasks ─────────────────────────────────┐
│ name          en  int   pri  last     next    state       guard      │
│ training      ●   6s    10   14:02:58 14:03:04 idle        target 1B  │
│ auto_shield   ○   20s   1    —        —        not_wired   cover 8h   │
│ gather        ○   120s  15   —        —        not_wired   reserve=1  │◀ expand
│   └ reserved_for_rallies [1]  min_level [1]  types [ore,stone,…]      │
│      preferred… [Advanced ▸]                   [Run now] [Save]        │
│ monster       ○   90s   14   —        —        not_wired   L≤0 rsv 0  │
└─────────────────────────────────────────────────────────────────────┘
```

**Config** `/config`
```
┌ sections ┬──────────────── humanize ───────────────────────────────┐
│ safety   │ delay_between_taps   lo[0.30] hi[0.80]                    │
│ humanize▸│ tap_duration_ms      lo[40]   hi[120]                     │
│ macro    │ deliberate_tap_prob  [0.10]                               │
│ tasks    │ same_button_max      [12]  (self-policing tell)           │
│ vision   │ ▸ Advanced (windmouse G0/W0/M0/D0, swipe_segment_px…)     │
│ notify   │                                                            │
│ engine   │ [ Raw YAML ]     changed: 1 field   [Revert] [Save]        │
└──────────┴────────────────────────────────────────────────────────┘
```

**Schedule** `/schedule`
```
┌──────────────────────────── Schedule (24h) ─────────────────────────┐
│ 00 02 04 06 08 10 12 14 16 18 20 22                                  │
│ ███░░░░░████▏▍██▏███▍██████▏████████████  ░=sleep ▏=micro-break      │
│         ▲ now                                                         │
│ sleep length  lo[6.0]h hi[9.0]h    anchor lo[1.0]h hi[4.0]h          │
│ break every   lo[20]m  hi[60]m     length lo[2]m   hi[8]m            │
│ awake window ≈ 15–18h/day                              [Save]         │
└─────────────────────────────────────────────────────────────────────┘
```

**Fleet** `/fleet`
```
┌──────────────────────────── Fleet ──────────────────────────────────┐
│ ● main       127.0.0.1:5555   features: training        [active]     │
│ ○ alt        127.0.0.1:5565   features: gather,daily     [enable]    │
│   note: keep separate from easy-bot.club accounts (kb/32)            │
│ [ + add account ]                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Logs** `/logs`
```
┌ Logs │ Events │ Decisions ─────────────────────────────────────────┐
│ level [all▾]  search[ own= ]                       ☑ follow tail    │
│ 14:02:58 info  training  batch 294 ok own=501,481,135              │
│ 14:02:41 warn  watchdog  stuck off known screens — recovering       │
│ 02:14:03 alert engine    DISCONNECT — stopped; will NOT tap         │
└─────────────────────────────────────────────────────────────────────┘
```

**Vision** `/vision`
```
┌──────────── frame ─────────────┬──────── tools ─────────────────────┐
│                                │ OCR   box[…] mode[number▾]  (Run)   │
│    [ current frame canvas ]    │   → 501,481,135  (412ms)            │
│    · drag a box to crop        │ Ground [ the Use button ] (Run)     │
│    · overlay boxes on results  │   → (540,1588) holo 1180ms          │
│                                │ Classify (holo☐)  → training_idle   │
│ ── Template Capture ──────────────────────────────────────────────  │
│  name[ shield_use_btn ]  box[…]  [Capture]  → templates/…png         │
└────────────────────────────────┴───────────────────────────────────┘
```

**Knowledge** `/knowledge` — left list of `kb/01…33`, right rendered markdown (read-only).
**Safety** `/safety` — invariant checklist (each ✅ enforced), gem-lock explainer, disconnect
policy card, humanization status, and a second PanicStop.

---

## 5. UI / design system

Dark-first (the bot runs overnight), light available. Neutral grays + one accent + semantic
green/amber/red. Follows practicaltypography.com: readable body size, generous line-height,
dark-gray (not pure black) text on screen, tabular figures everywhere numbers live.

### 5.1 Color tokens (CSS variables; Tailwind theme extension)

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0b0f14` | `#f7f8fa` | app background |
| `--surface` | `#131922` | `#ffffff` | cards, tables |
| `--surface-2` | `#1a2230` | `#eef1f5` | rows, wells |
| `--border` | `#243040` | `#dfe4ea` | hairlines |
| `--text` | `#e6e9ef` | `#1c2430` | body (dark-gray, not `#fff`/`#000`) |
| `--text-muted` | `#9aa6b6` | `#5b6675` | labels, captions |
| `--accent` | `#5b9dff` | `#2f6fed` | primary actions, focus ring, links |
| `--good` | `#4ade80` | `#16a34a` | running / ok |
| `--warn` | `#fbbf24` | `#d97706` | break / sleep / degraded |
| `--bad` | `#f87171` | `#dc2626` | disconnected / attack / panic |

Semantic mapping matches the plan: **green=running, amber=break/sleep, red=disconnected/attack**.
One accent only (blue); status colors are reserved for status, never decoration. Panic Stop is the
sole large `--bad` fill on the screen so it reads instantly.

### 5.2 Typography

- **Family**: Geist (UI) with Inter fallback; **Geist Mono / IBM Plex Mono** for numbers, coords,
  logs, and YAML. Stack: `Geist, Inter, ui-sans-serif, system-ui, sans-serif`.
- **Body**: 15–16px, line-height 1.5. Captions/labels 12–13px, uppercase labels get
  `letter-spacing: 0.06em` (per practicaltypography's all-caps tracking guidance).
- **Numbers**: `font-variant-numeric: tabular-nums` on every counter, coordinate, timer, and log
  timestamp so columns don't jitter as values change.
- **Headings**: one step up from body per level; page titles ~20–22px semibold. Bold **or**
  italic for emphasis, never both.
- **Measure**: content columns capped ~72ch; config forms are two-column on wide screens.

### 5.3 Spacing / layout

- 4px base scale (4/8/12/16/24/32). Card padding 16–20px; table row height 40px; rail width 56px.
- Left **icon rail** (56px) + top **StatusStrip** (48px) + content. Rail icons: Dashboard ▚,
  Live ⧉, Tasks ☰, Config ⚙, Schedule ⏱, Fleet ⚔, Logs ▤, Vision ◉, Knowledge ▤, Safety 🔒.
- Cards: 1px `--border`, 12px radius, subtle shadow in light / none in dark. Focus ring is a 2px
  `--accent` outline (keyboard-accessible via Radix defaults).
- Motion: 120–160ms ease for hovers/toggles; the engine dot pulses (1.7s) only when running;
  `prefers-reduced-motion` disables pulses and stream animations.

---

## 6. Phased backlog

Tickets are one-line deliverables. **P1 starts with the config-centralization refactor** — it is
the linchpin and independently improves the bot.

### P1 — MVP (view/edit + observe)

*Refactor (backend, no UI):*
- `P1-01` Add `config_schema.py` with the full `KeepConfig` pydantic tree (§1.2) + defaults.
- `P1-02` Add `config_store.py`: load/validate `config.yaml`, write with versioned snapshots, list/revert.
- `P1-03` `Humanize.to_legacy_dict()` adapter (Range→tuple) so `Humanizer(cfg=…)` is unchanged.
- `P1-04` `MacroSchedule.from_config`; wire `seed_salt`.
- `P1-05` `from_config` classmethods on Shield/Alliance/BaseDev/Gather/RallyJoin/Monster policies + `DailyCollector`.
- `P1-06` Refactor `orchestrator.default_tasks()` to build tasks from `cfg.tasks.*`.
- `P1-07` Refactor `orchestrator.run(config, control)` to accept a config object + `ControlChannel` (pause/reload/run-now/stop).
- `P1-08` Regression-run all 17 module self-tests unchanged; add a config round-trip test (defaults → yaml → load == defaults).

*Backend API:*
- `P1-09` FastAPI app skeleton (lifespan loads config, binds 127.0.0.1) + OpenAPI.
- `P1-10` `ControlChannel` + engine-thread supervisor (start/pause/resume/panic_stop).
- `P1-11` `GET/PUT/PATCH /api/config` + `/validate` + `/versions` + `/revert` with `422`/`423`.
- `P1-12` `GET /api/tasks`, `POST /api/tasks/{name}/toggle`, `/run-now`.
- `P1-13` `GET /api/status` + `POST /api/control`.
- `P1-14` `/ws/status` broadcaster from the bridge status dict.
- `P1-15` Log ring buffer + `GET /api/logs` + `/ws/logs`.

*Frontend:*
- `P1-16` Vite + Tailwind + shadcn scaffold, AppShell (rail + StatusStrip), routing.
- `P1-17` React Query client + `useWS` hook.
- `P1-18` Dashboard (StatusCard, SafetyBadges, EventsFeed, **PanicStop**).
- `P1-19` TaskTable with toggle + run-now + expandable policy `ConfigForm`.
- `P1-20` Config page (section nav, schema-driven `ConfigForm`, DiffBar, Save/Revert, Raw-YAML).
- `P1-21` Design tokens + typography (§5) as the Tailwind theme.

### P2 — observe deeper

- `P2-01` Wire `/ws/screen` to `live_stream.py` MJPEG; add `mode=frame` JPEG+meta push.
- `P2-02` Live page: LiveScreen + FSM overlay + click-to-ground probe (read-only).
- `P2-03` `/api/events` + `/api/decisions`; Logs page Events/Decisions tabs.
- `P2-04` Schedule page: ScheduleTimeline (24h band from `config.macro` + `status.macro`) + editors.
- `P2-05` Safety page: invariant checklist, gem-lock explainer, disconnect policy, second PanicStop.
- `P2-06` Reclaim-session flow: `POST /api/control {reclaim_session, confirm}` + confirm dialog (`428` guard).
- `P2-07` Tick-boundary reload polish: `{type:"reload"}` control frame invalidates `['config']`; requires-restart flagging for device/account changes.
- `P2-08` Status counters history (own/food/rate) persisted to a small ring for MiniCharts.

### P3 — power tools

- `P3-01` Vision playground: `/api/vision/{ocr,ground,classify}` on the shared frame + single-slot inference lock.
- `P3-02` Vision page UI: FrameCanvas crop-box, OCR/Ground/Classify panels, timings, model-loading state.
- `P3-03` Template Capture: `POST /api/templates/capture` + `GET /api/templates` + capture UI (grab→crop→name→save).
- `P3-04` `used_by` cross-ref against `screen_fsm.ANCHOR_ORDER`; template trash/versioning.
- `P3-05` Fleet/multi-account: per-account config + `active_account` switch (engine restart on switch).
- `P3-06` Knowledge page: render `kb/*.md` (read-only browser).
- `P3-07` Recharts troops/food/ETA history charts on Dashboard.
- `P3-08` Auth for remote: token / Cloudflare Access in front of the Cloudflare tunnel; never unauthenticated.

---

## 7. Risks & open decisions

### Carried forward from the plan (§10)

1. **Frontend stack** — React SPA (recommended, this spec assumes it) vs. HTMX/Alpine. *Decision
   assumed: React SPA.* Revisit only if JS surface area becomes a burden.
2. **Scope now** — single-account console first vs. Fleet from P1. *This spec ships single-account
   in P1 and defers real multi-account to P3, but the schema (`Fleet.accounts[]`) is present from
   P1 so nothing has to be re-modeled later.*
3. **Access** — local-only vs. remote via the Cloudflare tunnel with auth. *Local-only P1;* remote
   + auth is `P3-08` and must never be unauthenticated.
4. **Name** — *Murder Bot* (assumed).

### New risks surfaced (with mitigations)

- **[HIGH] Single game session concurrency.** There is exactly one emulator and one ADB channel.
  The engine thread and any vision/dev-tap request all contend for it. If a vision endpoint grabbed
  its own frame or a dev-tap fired mid-tick, taps could interleave and desync the game (or worse,
  land on the wrong control). *Mitigation:* only the engine thread touches ADB; vision reads the
  **last published frame** (`control.frame`); dev-taps are queued through the same `run_now`/tick
  path, never issued directly, and are gem-guarded. This is the single most important correctness
  constraint in the build.
- **[HIGH] Config hot-reload atomicity vs. a live tap.** A reload that swapped policies or the
  Humanizer *mid-tap* could corrupt an in-flight action or lose the session. *Mitigation:* reload
  is applied only at the tick boundary (§3.3), the swap is a whole validated `KeepConfig`, and
  device/account changes are flagged requires-restart rather than hot-swapped. Risk remains if a
  future task holds state across ticks — those tasks must expose a `reload_safe()` checkpoint.
- **[HIGH] Gem-lock must survive a hand-edited YAML.** The UI hiding the toggle is not enough.
  *Mitigation:* four independent layers (§3.5); layer 1 makes an invalid `config.yaml` refuse to
  load at startup, so the bot won't even start with `gem_spend:true`.
- **[MED] Holo/MLX memory + first-call latency in-process.** Loading a 7B MLX model inside the API
  process adds hundreds of MB and a multi-second first-call stall; two concurrent generations would
  thrash. *Mitigation:* lazy single-slot inference (one-worker executor + lock), surface
  `model_loaded` in responses, keep OCR (`ocr_first:true`) as the primary path. Decision to make:
  cap Holo to the Vision page only, or let the engine use it as a grounding fallback too (default:
  engine may use it, gated by `vision.holo_fallback_on`).
- **[MED] Unwired tasks enabled from the UI fail loudly.** Toggling `gather` on before its
  `[LIVE-CAPTURE]` `perceive/act` exist makes it raise every tick. *Mitigation:* `GET /api/tasks`
  exposes `wired:false`, the row shows "(wire)", toggle returns a `warning`, and the engine's
  existing fail-safe (NotReady + notify) contains it. Decision: hard-block enabling unwired tasks,
  or allow-with-warning (spec assumes allow-with-warning).
- **[MED] Watchdog vs. map/alliance screens.** `orchestrator.run`'s own comment warns that
  off-anchor recovery is only safe while training is the sole live task; enabling gather/monster
  (which visit un-anchored screens) could trigger a false app-refresh. *Mitigation:* before P3
  wiring of map tasks, add per-task "expected screens" so the watchdog's off-anchor threshold
  isn't tripped by a legitimate un-templated screen. This is a real correctness dependency, not
  just app polish.
- **[LOW] Template capture coordinate space.** The frame published for OCR/capture is
  full-resolution device space (1080×1920), but the MJPEG stream is downscaled to width 640
  (`live_stream.WIDTH`). Capture boxes drawn on the *stream* must be scaled back to device space
  before cropping. *Mitigation:* the Vision FrameCanvas operates on the full-res frame from
  `/ws/screen mode=frame` (which carries `seq` + native dims), not the downscaled MJPEG.
- **[LOW] Reclaim-session is the one deliberate tap on a dangerous screen.** It taps Restart after
  a disconnect. *Mitigation:* `confirm:true` required (`428` otherwise), mirrors the standing rule;
  it must never be automatable from config.

---

## Appendix A. Extracted real defaults

Verbatim from the code, so the schema and UI don't drift.

**`humanize.DEFAULTS`** — jitter_samples 3 · tap_box_shrink_px 6 · delay_between_taps (0.30,0.80)
· delay_after_menu (0.80,2.50) · delay_between_tasks (3.0,15.0) · reaction_floor 0.25 ·
tap_duration_ms (40,120) · deliberate_tap_ms (150,400) · deliberate_tap_prob 0.10 ·
windmouse {G0 9.0, W0 3.0, M0 15.0, D0 12.0} · swipe_segment_px 12 · click_window 15 ·
same_button_max 12 · alt_button_max 6.

**`macro_schedule.DEFAULTS`** — sleep_len_h (6.0,9.0) · sleep_anchor_h (1.0,4.0) ·
micro_break_every_min (20.0,60.0) · micro_break_len_min (2.0,8.0) · idle_poll_cap_s 300.0.
Constructor also takes `seed_salt=0`.

**`auto_shield.ShieldPolicy`** — react_within_s 900 (15m) · reshield_margin_s 600 (10m) ·
desired_cover_s 28800 (8h) · proactive False. Items: truce_1h/8h/24h/3d.

**`daily_collect`** — `DailyCollector(max_per_tick=3)`; `SOURCES` = alliance_help(120,9),
city_resources(600,8), mail(300,7), tax(3600,7), daily_quest_chest(43200,7), bounty(1800,6),
eggs(3600,6), patrol(3600,6), wheel(86400,6), free_chest(14400,5). `(key, min_interval_s, priority)`.

**`alliance.AlliancePolicy`** — donations_per_day 20 · help_cooldown_s 60.0 ·
ALLOWED_DONATION_COSTS ("free","resource") (gem tiers refused, not user-editable).

**`base_dev.BaseDevPolicy`** — preferred_speedup_item None · min_speedup_remaining_s 300 (5m).

**`gather.GatherPolicy`** — reserved_for_rallies 1 · preferred_min_level 1 ·
preferred_resource_types ("ore","stone","lumber","food").

**`rally_join.RallyJoinPolicy`** — only_boss True · max_seconds_left 300 · require_feasible True ·
reserved_free_marches 0.

**`monster.MonsterPolicy`** — preferred_types () · max_level 0 · min_stamina_reserve 0.

**`orchestrator.default_tasks()`** `(name, interval s, priority, enabled)` — training(6,10,✔) ·
daily_collect(600,30,✘) · alliance(1800,25,✘) · auto_shield(20,1,✘) · base_dev(300,20,✘) ·
gather(120,15,✘) · rally_join(60,12,✘) · monster(90,14,✘). *Lower priority number runs first.*

**`orchestrator.run(...)`** — device "127.0.0.1:5555" · stuck_threshold 6 · macro "default" ·
idle_cap_s None · watchdog True · llm_fallback False · should_stop None. Return codes:
`done`/`disconnect`/`stopped`. Exit codes (run_bot): 0 done · 2 disconnect · 3 stopped · 1 error.

**`scheduler`** — `Scheduler(retry_delay=30.0)`; `Task(name, func, interval, priority=10,
jitter=0.0, enabled=True)` tracks `runs`/`fails`/`next_run`.

**`config.py`** (train_to_1b) — DEVICE "127.0.0.1:5555" · TARGET_OWN 1_000_000_000 ·
TRAIN_QTY 269228 · SCREEN 1080×1920 · MATCH_THRESHOLD 0.82 · USE_FINISH_ALL True.

**`holo_vision`** — model "mlx-community/holo1.5-7b-mlx" · downscale ≤960 long-side ·
`ground(image, instruction, max_tokens=256)` · `describe(image, question, max_tokens=256)`.

**`screen_fsm`** — `ANCHOR_ORDER` thresholds mostly 0.85 (radial 0.80, city 0.60) ·
`is_disconnect(img, min_score=0.85)` · READY {training_idle, training_busy, cap_popup}.

**`live_stream`** — PORT 8088 · FPS 3.0 · WIDTH 640 · QUALITY 80; routes `/stream` (MJPEG),
`/seq`, `/stats`, `/hls/…`, `/hls.js`.

**`notify`** — env `EVONY_NOTIFY_MAC` (default on), `EVONY_NOTIFY_SLACK`, `EVONY_NOTIFY_DISCORD`;
levels info/warn/alert/ok; returns list of channels reached.

**Assets** — `templates/` 19 PNGs · `kb/` 33 markdown docs (01–33) · `game_brain/catalog.json`.

## Appendix B. Repo touch-map

| New file | Role |
|---|---|
| `config_schema.py` | the `KeepConfig` pydantic tree (§1) |
| `config_store.py` | load/validate/snapshot/revert `config.yaml` |
| `control_bridge.py` | `ControlChannel` + engine-thread supervisor (§3) |
| `api/` (FastAPI app) | routers: config, tasks, status, control, logs, vision, templates, ws |
| `web/` (Vite app) | React/TS frontend (§4) |
| `config.yaml` | the single source of truth (§1.3) |

| Existing file | Change |
|---|---|
| `orchestrator.py` | `run(config, control)`; `default_tasks()` reads `cfg.tasks.*`; consult `control` each tick |
| `humanize.py` | accept a config-derived cfg (already supported); add Range adapter |
| `macro_schedule.py` | `from_config` |
| `*policy* modules` | add `from_config` classmethods; **decision logic + tests unchanged** |
| `notify.py` | accept explicit `env=`/config; keep env fallback |
| `live_stream.py` | expose the MJPEG frame source to the bridge (reuse, don't fork) |

*This is a spec only — nothing here is implemented. `P1-01…P1-08` (the config-centralization
refactor) is the first real step and independently improves the bot.*
