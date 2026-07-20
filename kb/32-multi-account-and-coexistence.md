# Multi-Account Operation + Coexistence with a Cloud Bot

How to run **several Evony accounts locally** (N BlueStacks instances on one Mac, one ADB port each,
round-robin scheduled) **while** a cloud service (easy-bot.club / "EasyBot") also bots **some** of
your accounts from its own servers. Extends `orchestrator.py` (today single-device,
`DEVICE = "127.0.0.1:5555"`) to a fleet.

**Bottom line:**
1. **One account per emulator instance** beats in-game account-switching for a bot. Every mature
   OSS bot does it this way (ALAS = one config per instance, TaskEX = one BlueStacks port per
   instance, TungNC = one MEmu per account, batazor = one device→profile map).
2. **Separate accounts per controller.** Give easy-bot.club the **farm/gather/rally** accounts;
   keep **main/build/train** accounts on the local bot. No account ever has two controllers →
   **zero login contention by construction.** Time-slicing a shared account is fragile; don't.
3. Evony enforces **one active session per account**. A second login (the cloud, from its server)
   kicks the first with the "logged in elsewhere" popup — the exact `disconnect_popup` our FSM
   already guards (`screen_fsm.is_disconnect`, `orchestrator.py:164`). That popup is a **kick, not
   an error to fight.**

---

## 1. Multiple instances vs in-game account-switching — which is more reliable?

| | **N instances, 1 account each** (recommended) | **1 instance, switch accounts in-game** |
|---|---|---|
| Session stability | Each account is a **long-lived logged-in session**; bot never re-authenticates | Every switch is a fragile multi-step UI walk (Settings→Account→Switch→pick FB/Google→character-select→load) |
| FSM complexity | Simple: bot never leaves the account | Must template + verify the whole switch flow; re-login can surface consent/2FA/captcha/"new device" screens |
| Parallelism | True concurrency across devices | Serialized — one account at a time |
| Device isolation | Own ADB serial per account → clean `-s <serial>` targeting | Shared serial; state bleeds across accounts if a step mis-fires |
| Failure blast radius | One stuck device ≠ others | A mis-tap can log into the **wrong** account or strand the client |
| Cost | Heavy: RAM/CPU/GPU per instance | Light: one emulator |
| Behavioral tell | None extra | The relogin cadence itself is a tell, and **triggers the "logged in elsewhere" kick** if that account is also on the cloud |

**Verdict:** default to **one account per instance**. Use in-game switching **only** as a
resource-saving fallback for a *rotation of low-stakes farm alts* that tolerate infrequent,
serialized visits (e.g. a daily-collect sweep) — and then treat the switch as a **first-class FSM
sub-routine** with post-switch identity verification (OCR the profile name/ID against the expected
`game_id`) before any action. Never switch a `main`. `[VERIFY IN-GAME]` the current
switch-account button path — Evony moves Settings around between versions.

---

## 2. Fanning out to N ADB devices (BlueStacks multi-instance on a Mac)

**Each instance = its own ADB endpoint.** BlueStacks 5's **Multi-Instance Manager (MIM)** clones
instances; each exposes a distinct `127.0.0.1:<port>`.

- **Find the port reliably:** each instance → **Settings → Advanced → Android Debug Bridge (ADB)**
  shows its port. Then `adb connect 127.0.0.1:<port>`; `adb devices` enumerates all connected
  serials. **Enumerate, don't assume.**
- **The "+10" heuristic** (first `5555`, then `5565`, `5575`, …) is a common pattern but modern
  BlueStacks 5 assigns ports **per-instance and not always predictably** — read them from Advanced
  settings once, then pin them in the profile file. `[VERIFY ON-MACHINE]`
- **Robust discovery in code:** run `adb devices`, filter `emulator-*` / `127.0.0.1:*` lines, and
  map each serial to a profile by port. This is what TaskEX and TungNC do (auto-detect via ADB).

**Mac resource budget** — Evony is a **3D-map, GPU-heavy** app, heavier than 2D games:

| Mac | Realistic concurrent Evony instances |
|---|---|
| 16 GB / 8-core | **2–3** |
| 32 GB / 10-core (M-series) | **4–6** |
| 64 GB+ | **8–10** |

Rule of thumb: budget **~2 vCPU + ~2.5–4 GB RAM per smooth Evony instance**, plus GPU headroom;
leave 25–30% for macOS. Lower per-instance cost by running instances at **540p** (TaskEnforcerX
does — kb/17), capping FPS, and setting Evony to low graphics; lighter frames also mean lighter
templates. `[VERIFY ON-MACHINE]` — map rendering is the swing factor.

**Apple-Silicon caveat:** BlueStacks 5 MIM is an **Intel-Mac** product; on Apple Silicon the native
build is **BlueStacks Air**, whose multi-instance maturity is newer/limited `[VERIFY]`. Serious
multi-accounting (dozens) is traditionally a **Windows + MEmu** setup — which is exactly why
**TungNC-echoes/auto-evony-v1** targets MEmu. For >4–5 accounts, consider a Windows box or splitting
the fleet across machines rather than overloading one Mac.

---

## 3. How OSS bots fan out to N devices (patterns to steal)

| Repo | Multi-instance model | What to steal |
|---|---|---|
| **Jany-M/TaskEX** (BlueStacks, our stack) | Per-**port** instances; default ports `[5555, 5556]`; SQLite `db/task_ex.db` stores each instance's **`{id, name, port, profile}`**; CLI `--list-instances`, `--start-instance "Ant Alt"`, `--stop-instance 5575`; per-instance feature modes (Auto Bubble / Join Rally / Auto Gather = auto / manual / off) **persisted per instance** | **Instance registry keyed by port + per-instance task toggles persisted to a DB** — this is our profile file + per-account task set, exactly. https://github.com/Jany-M/TaskEX |
| **TungNC-echoes/auto-evony-v1** (MEmu) | "EVONY Auto – Multi Device Manager": auto-detects connected **MEmu** devices via bundled ADB (`adb_tools/`), GUI to **select the target device**, then per-device `actions/` (rally join, meat/food buy, war, boss); modules `main3_gui.py`, `actions/`, `utils/` (ADB+image) | **Bundle ADB, auto-detect devices, pick device → run per-device action set.** The concrete multi-MEmu reference. https://github.com/TungNC-echoes/auto-evony-v1 |
| **LmeSzinc/AzurLaneAutoScript (ALAS)** | **One config file per instance** (`config/alas.json`, `alas2.json`, …); each config carries its own `Emulator.Serial` (`127.0.0.1:5555`…); GUI instance dropdown; run more by adding config copies, each its own scheduler/process | **One config = one serial = one scheduler.** Our `Fleet` is N ALAS-configs in one process. `[VERIFY]` exact field names. https://github.com/LmeSzinc/AzurLaneAutoScript (kb/17) |
| **MaaXYZ/MaaFramework** | Library: instantiate **one controller per ADB address**; each controller drives one device independently | **N controllers, N serials, one host process.** https://github.com/MaaXYZ/MaaFramework (kb/17) |
| **batazor/whiteout-survival-autopilot** | "bot-farm support"; `db/devices.yaml` (`cp db/devices.example.yaml`), set `device_id` from `adb devices`; schema is **`devices → profiles(email) → gamer(id, nickname)`** | **The profile schema below is modeled on this** — device → account(login email) → character(id). https://github.com/batazor/whiteout-survival-autopilot |
| **sonpiaz/4x-game-agent** | **Single-account** (OCR→FSM→World-Model→Workflows→LLM); no multi-account layer | Borrow the **FSM + World-Model**, not multi-account — it has none. https://github.com/sonpiaz/4x-game-agent |

**Convergent lesson:** everyone binds **one account ⇆ one device serial ⇆ one scheduler**, and
stores a small **instance/profile registry** (SQLite in TaskEX, `devices.yaml` in batazor). Nobody
account-switches in production. Our disconnect guard already assumes one controller per instance
(kb/30: *"One controller ↔ one instance ↔ one account; two touch injectors race → phantom taps"*).

---

## 4. Per-account profile schema

Model: **device serial → account(login identity) → task set**. Store in `profiles.yaml`.
Credentials are **not** in the repo (see note).

```yaml
# profiles.yaml — the fleet inventory (local + cloud accounts, one place)
accounts:
  - name: main-1
    controller: local              # local | cloud | shared(discouraged)
    role: main                     # main | farm
    serial: "127.0.0.1:5555"       # BlueStacks instance ADB port (read from Advanced→ADB)
    instance: "Evony-Main"         # BlueStacks MIM label — for --start/--stop-instance
    login: google                  # google | facebook | apple | topgames  (IDENTITY ONLY, no password)
    game_id: 12345678              # in-game id — OCR-verify after any switch; used in logs
    active_hours: [8, 23]          # per-account wake window (kb/30 macro schedule)
    tasks:                         # names match orchestrator's task registry
      training:      {interval: 6,     priority: 10}
      auto_shield:   {interval: 20,    priority: 1}
      daily_collect: {interval: 3600,  priority: 30}
      alliance:      {interval: 14400, priority: 25}

  - name: farm-1
    controller: cloud              # OWNED BY easy-bot.club — never driven locally
    role: farm
    game_id: 87654321              # listed for inventory only; no serial (runs server-side)

  - name: farm-2
    controller: cloud
    role: farm
    game_id: 87654322
```

**Credentials handling (important — Evony logins are FB/Google/Apple/TopGames linked):**
- **Local accounts:** the bot **never authenticates**. The BlueStacks instance stays logged in
  (persistent session); the profile carries only the **identity** (`login` provider + `game_id`)
  for logging and post-switch verification. **Zero passwords in the repo.**
- **Cloud accounts:** you hand credentials to **easy-bot.club's own web UI**, not to this repo. They
  live server-side. Our `profiles.yaml` lists cloud accounts for **inventory only** and the fleet
  **skips** them.
- If you ever use in-game switching, still rely on the **emulator's cached FB/Google session** —
  never store the password.

---

## 5. Round-robin scheduler across N instances

ADB taps are blocking `subprocess` calls and effectively **serialized** on one host, so a
**single-threaded round-robin over N devices** is the clean design (no thread/ADB contention, one
log, deterministic). Reuse the existing `Scheduler`/`Task` **per account**; add a device dimension
by sweeping accounts and running each one's most-due task.

Key policy difference from single-device: on a **local** account, the disconnect popup means
**someone else logged in** — a human, or a **misconfigured** cloud takeover. A correctly-separated
local account should *never* see it. So: **yield that one device with a backoff, keep the fleet
running, and notify** (don't kill everything, don't tap).

```python
# fleet.py — extends orchestrator.py to N devices (design sketch)
import time
import screen_fsm
import watchdog as wd
from orchestrator import Ctx
from scheduler import Scheduler

class Account:
    def __init__(self, p, logger=print):
        self.name, self.role = p["name"], p["role"]
        self.controller = p["controller"]                 # local | cloud | shared
        self.serial = p.get("serial")
        self.game_id = p.get("game_id")
        self.ctx = Ctx(self.serial, logger=lambda m, n=self.name: logger(f"[{n}] {m}"))
        self.sched = Scheduler()
        self.watch = wd.Watchdog(self.serial, grab_fn=self.ctx.screencap)
        self.backoff_until = 0.0

def build_local_fleet(profiles, tasks_for, logger=print):
    """One Account per LOCAL profile. Cloud/shared accounts are skipped -> zero contention."""
    fleet = []
    for p in profiles["accounts"]:
        if p["controller"] != "local":
            logger(f"skip {p['name']}: controller={p['controller']} (owned elsewhere)")
            continue
        acc = Account(p, logger)
        for t in tasks_for(p, acc.ctx):                   # per-profile task set (name->interval/priority)
            if t.enabled:
                acc.sched.add(t)
        fleet.append(acc)
    logger(f"fleet: {len(fleet)} local device(s)")
    return fleet

def run_fleet(profiles, tasks_for, logger=print, notify=lambda m: None, backoff=900):
    fleet = build_local_fleet(profiles, tasks_for, logger)
    while True:
        now = time.time()
        acted = False
        for acc in fleet:                                 # fair round-robin sweep
            if now < acc.backoff_until:
                continue
            due = acc.sched.seconds_until_next(now)
            if due is None or due > 0:
                continue                                  # nothing due on this device yet
            img = acc.ctx.screencap()                     # screencap only devices we're about to touch
            if screen_fsm.is_disconnect(img):
                # LOCAL account should have NO other controller. Kick here == human or mis-set cloud.
                acc.ctx.log("DISCONNECT on a LOCAL account (logged in elsewhere). Yielding; NOT tapping.")
                notify(f"{acc.name}: unexpected takeover — check controller separation")
                acc.backoff_until = now + backoff         # re-probe later, don't fight
                continue
            try:
                if acc.sched.run_due():
                    acted = True
            except Exception as e:
                acc.ctx.log(f"task not ready: {e}")
        if not acted:
            waits = [a.sched.seconds_until_next() for a in fleet if now >= a.backoff_until]
            nxt = min([w for w in waits if w is not None] or [1.0])
            time.sleep(min(max(nxt, 0.2), 1.0))
```

**Fairness:** each sweep advances every device by at most one task; a device with a hot cadence
(e.g. `training` @6s) naturally runs more often because its `next_run` comes due more often, while
`auto_shield` @20s / `daily_collect` @1h stay sparse — the existing `Scheduler` priority/`next_run`
model does the within-device ordering unchanged. **Cap the fleet at what the Mac can render**
(§2) — over-subscribing instances makes *every* device laggy and mis-taps rise.

---

## 6. Multi-account orchestrator design (extending `orchestrator.py`)

`orchestrator.py` today: one global `DEVICE`, one global `CTX`, one `Scheduler`, `run()` loops one
device and `return "disconnect"` on the popup. The fleet keeps all of that per-account and adds a
thin outer loop. Concretely:

| Concern | Single-device today | Fleet change |
|---|---|---|
| Device | module-level `DEVICE` | `Account.serial` from `profiles.yaml`; discover/validate via `adb devices` |
| Context | global `CTX` | one `Ctx(serial)` per account (already parameterized — `Ctx(device, logger)`) |
| Scheduler | one `Scheduler` | one per account; outer round-robin sweep (§5) |
| Task set | `default_tasks()` (global) | `tasks_for(profile, ctx)` builds the account's set from `profiles.yaml` (roles differ) |
| Disconnect | `return "disconnect"` (stop whole bot) | **per-device yield + backoff + notify**; fleet keeps running (§5) |
| Watchdog | one | one per serial (crash/relaunch is per-instance) |
| Gem-safety | global rule | unchanged — still applies to every task on every device |

`tasks_for` is where **role** matters: a `main` gets `training + auto_shield + alliance +
daily_collect`; a local `farm` (rare — most farms go to the cloud) gets `gather + daily_collect`
only. Reuse the existing `Task(name, func, interval, priority, enabled)` and the kb/18 roadmap
registry verbatim — the only new thing is *selecting per profile*.

Migration is additive: `orchestrator.run()` stays as the single-device path; `fleet.run_fleet()`
is the N-device path. `train_to_1b.py` and every task keep working unchanged.

---

## 7. Coexistence with easy-bot.club — the rules

### The mechanism (confirmed)
- **easy-bot.club is a cloud/SaaS bot.** Its site is a bare **login portal** ("Easy Bot / Login to
  EasyBot") with **no download** — it runs **server-side** and logs into your account from **its**
  IPs. https://easy-bot.club
- **Evony enforces one active session per account.** When the cloud client authenticates, the game
  server **invalidates your older session** and the local client shows the **"logged in on another
  device"** popup — the standard MMO single-session kick.
- **That popup is exactly `disconnect_popup`** in our FSM. The code already treats it as an
  easy-bot.club takeover and **stops without tapping**: `orchestrator.py:20` & `:164–166`,
  `screen_fsm.is_disconnect`, and kb/19 ("*the account is shared with easy-bot.club, whose logins
  cause it*").
- **Cadence:** kb/30 records the cloud re-logging in roughly **every ~60 min**, producing recurring
  kicks on any shared account. `[VERIFY]` — observed/community, not vendor-documented.

### The three strategic options

**(a) SEPARATE ACCOUNTS — cloud owns farms, local owns mains. ← STRONGLY RECOMMENDED.**
Each account has exactly **one** controller, so the "logged in elsewhere" event **can never fire**
between your two bots. This is the only option that removes contention *by construction* rather than
managing it. It also matches the ecosystem: farm accounts are a first-class Evony concept, and
commercial bots advertise "multi-account (dozens)" precisely so each account is single-purpose
(kb/17). Reasoning stack:
- **No lost work.** A kick mid-`training`/mid-`Finish All` can waste speedups/food; separation
  eliminates the whole failure mode.
- **No behavioral tell.** Hourly relogin storms are a server-visible signature (kb/30);
  concentrating them on cloud-owned farms keeps your **main's** session clean and human-shaped.
- **Blast-radius isolation.** If a farm gets actioned for botting, your **main is a different
  account** — you never handed its credentials to a third party, and you never botted it hard.
- **Ops simplicity.** Local fleet skips every `controller: cloud` account (§5) — no coordination
  logic to get wrong.

**(b) Time-slice one shared account. ← DON'T.** You'd have to synchronize two independent
controllers, one of which (the cloud) relogins on **its own ~hourly clock you can't set**. Result:
constant mutual kicks, work lost at the boundary, and the relogin churn is itself the tell. Fragile
and low-yield.

**(c) FSM detects the takeover and yields. ← safety net, not a strategy.** Already implemented
(§5 backoff, the disconnect guard). If you're *forced* to share an account, (c) + a **long backoff**
(re-probe every 15–30 min, act only when the account is idle) is the least-bad — but you cede most
local uptime whenever the cloud owns the account. Use it as the fallback that makes a
misconfiguration safe, **not** as the plan.

**What multi-bot users actually do:** **(a).** The farm-account meta exists so you can dedicate
whole accounts to single-purpose 24/7 automation; hobby setups run the main themselves (locally or
by hand) and point the cloud bot at farms. `[Partly inferred from ecosystem — flag]`

---

## 8. Farm-account vs main-account division of labor

| | **Main / build account** → **local bot** | **Farm / alt account** → **cloud bot** |
|---|---|---|
| Purpose | Keep growth, research, buildings, **troop training** (our `train_to_1b` loop), power, VIP, rally leadership, event points, monster hits for the main | High-volume **resource gathering** (RSS tiles), transporting/reinforcing resources to the main (market / alliance / rally reinforce), soaking **gather events**, occasional reinforce |
| Traits | High value, needs judgment, event timing | Repetitive, low-risk, high-volume, tolerant of 24/7 |
| Who runs it | **You** (local bot + manual) — never hand its login to a cloud service | The **cloud** (24/7 gathering is exactly what easy-bot sells) |
| If banned | Catastrophic → protect it | Replaceable → acceptable risk |

Evony's community treats **alts/farms** as gather-and-feed accounts for a main (theria: "*Increasing
March Speed for Alts*" — https://theriagames.com/guide/increasing-march-speed-for-alts/; evonytkrguide
gathering guide — https://www.evonytkrguide.com/). This split maps **one-to-one** onto the
coexistence split in §7: **local = main (build/train), cloud = farms (gather/rally)** —
`role: main` vs `role: farm` in the profile drives both the task set (§6 `tasks_for`) and the
controller assignment.

---

## 9. Account-linking / ban-association risk (many accounts, one IP)

Evony (Top Games) enforcement is **manual/report-driven, no in-game captcha** (kb/30) — but
operators still **associate** accounts by shared **device fingerprint**, shared **IP**, shared
**payment method**, and cross-account **resource-transfer patterns**. Running many accounts from one
home IP + one machine forms a **linkage cluster**: if one is actioned for botting,
guilt-by-association bans on the rest are a real risk in mobile 4X. `[VERIFY — community/inferred,
not documented by Top Games]`

Risk-management notes (responsible use on **self-owned** accounts; automation violates ToS
regardless — kb/30 framing):
- **Keep the main out of the automation cluster:** don't bot the main hard, don't share its login,
  keep its behavior human-shaped (kb/30 macro schedule).
- **Cloud farms originate from easy-bot's IPs, not yours** — a mild plus (your home IP isn't the one
  showing bot-cadence gathering), but easy-bot's server IP is **shared across its customers**, which
  is its *own* association surface. Trade-off, not a free win.
- **Don't over-cluster:** if you care about the main, avoid running a dozen local accounts from one
  IP alongside it. Fewer, well-separated accounts > many linked ones.
- **Payment hygiene:** don't fund throwaway farms and the main from the same card if you're worried
  about linkage. `[VERIFY]`

---

## Open items to verify
- Exact BlueStacks-5 per-instance ADB ports on **this Mac** (read Advanced→ADB, then pin) `[VERIFY ON-MACHINE]`.
- easy-bot.club relogin cadence — assumed ~60 min from kb/30 `[VERIFY]`.
- Apple-Silicon BlueStacks Air multi-instance ceiling `[VERIFY ON-MACHINE]`.
- In-game switch-account button path in the current Evony version `[VERIFY IN-GAME]`.
- Top-Games account-association / multi-account ban behavior `[VERIFY]`.

## Sources
- Local codebase: `orchestrator.py` (single-device + disconnect guard, `:20`, `:164–166`),
  `screen_fsm.py` (`is_disconnect`, `disconnect_popup` template), `scheduler.py` (`Task`/`Scheduler`),
  `config.py` (`DEVICE`), kb/17 (OSS survey), kb/19 (orchestrator architecture), kb/30 (anti-detection:
  one-controller-per-instance, ~60-min easy-bot relogin, macro schedule).
- OSS: https://github.com/Jany-M/TaskEX · https://github.com/TungNC-echoes/auto-evony-v1 ·
  https://github.com/LmeSzinc/AzurLaneAutoScript · https://github.com/MaaXYZ/MaaFramework ·
  https://github.com/batazor/whiteout-survival-autopilot · https://github.com/sonpiaz/4x-game-agent
- Cloud bot: https://easy-bot.club (login-gated → cloud/SaaS, server-side login).
- Evony farm/alt strategy: https://theriagames.com/guide/increasing-march-speed-for-alts/ ·
  https://www.evonytkrguide.com/ (gathering guide).
</content>
</invoke>
