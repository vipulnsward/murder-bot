"""Multi-task orchestrator for the Evony bot.

Wires the tested building blocks into one engine so features can be added as
plug-in tasks (the goal: replicate a full-service bot — training, gathering,
rallies, monsters, defense, alliance, daily — and run/improve it locally):

  - fast_screenshot  -> fast frames (raw screencap -> NumPy)
  - screen_fsm       -> "which screen am I on?" + account-disconnect guard
  - watchdog         -> crash/stuck detection + app_refresh recovery
  - scheduler        -> ALAS-style time-based task scheduling (priority + interval)

Each feature is a Task(name, interval, priority, enabled, run). `run(ctx)` does
ONE unit of work and returns an optional seconds-override for its next run.
Training is implemented (reuses train_to_1b, gem-safe). The rest are registered
as disabled stubs with the exact behavior to fill in once their UI templates are
captured on a clean session (see kb/18 for the prioritized roadmap).

GEM SAFETY: no task may tap a gem-spend path. Training uses item-based "Use".
DISCONNECT: on the account-disconnect screen the engine STOPS without tapping
(the account is shared with easy-bot.club, whose logins trigger it).
"""

import time

import fast_screenshot
import screen_fsm
import watchdog as wd
from scheduler import Scheduler, Task

DEVICE = "127.0.0.1:5555"


class Ctx:
    """Shared context handed to every task: device I/O + a logger.

    Taps/swipes go through the Humanizer (kb/30): jittered center-biased points,
    ranged delays, WindMouse curved swipes, and self-policing (repeated-tap tell
    -> humanize.TooManyClicks, which the run loop turns into a pause+notify)."""

    def __init__(self, device=DEVICE, logger=print):
        self.device = device
        self._log = logger
        import humanize
        self.hz = humanize.Humanizer(device)

    def screencap(self):
        return fast_screenshot.grab(self.device)

    def tap(self, x, y, d=0.3, label="", radius=10):
        self.hz.tap_point(x, y, radius=radius, label=label)   # humanized; may raise TooManyClicks

    def swipe(self, x1, y1, x2, y2, ms=400, d=0.3):
        r = 6
        self.hz.swipe((x1 - r, y1 - r, x1 + r, y1 + r), (x2 - r, y2 - r, x2 + r, y2 + r))

    def back(self, d=0.9):
        import subprocess
        subprocess.run(["adb", "-s", self.device, "shell", "input", "keyevent", "4"])
        time.sleep(_human_pause(d))

    def log(self, msg):
        self._log(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _human_pause(d):
    import random
    return max(0.0, d + random.uniform(-0.15, 0.35))


def _notify(msg, level="info"):
    """Best-effort push alert (macOS banner + any configured Slack/Discord). Never raises."""
    try:
        import notify
        notify.notify(msg, level=level)
    except Exception:
        pass


def llm_resolve(ctx, img, goal="reach the training screen"):
    """Escalate a stuck/unknown state to the LLM vision fallback (opt-in; costs
    API credits). Executes the ONE safe action it returns and logs the decision
    for later KB distillation. Returns the action dict, or None if unavailable."""
    try:
        import json
        import llm_agent
        act = llm_agent.decide(img, goal=goal)
    except Exception as e:
        ctx.log(f"llm_resolve unavailable: {e!r}")
        return None
    ctx.log(f"llm: {act.get('action')} ({act.get('reason','')[:60]})")
    a = act.get("action")
    if a == "tap" and act.get("x") is not None:
        ctx.tap(act["x"], act["y"])
    elif a == "swipe" and act.get("x2") is not None:
        ctx.swipe(act["x"], act["y"], act["x2"], act["y2"])
    elif a == "back":
        ctx.back()
    # tap "stop"/"done"/"wait" are non-actions here (caller decides)
    try:
        with open("llm_decisions.jsonl", "a") as f:
            f.write(json.dumps({"t": time.strftime("%H:%M:%S"), **act}) + "\n")
    except Exception:
        pass
    return act


class NotReady(Exception):
    """Task couldn't act this tick (e.g. not on the right screen); reschedule soon."""


def training_task(ctx):
    """One training batch, gem-safe (train_to_1b uses item-based 'Use')."""
    import train_to_1b as T
    r = T.train_one_batch()
    if r == "OK":
        return None            # keep the fast cadence
    if r in ("NAV", "SKIP", "NOFOOD"):
        raise NotReady(r)      # let the scheduler retry shortly
    return None


def _stub(feature, note):
    def run(ctx):
        raise NotImplementedError(
            f"{feature} not implemented yet. {note} "
            f"Needs UI templates captured on a clean session."
        )
    return run


# The task registry. Enable + implement top-down per the kb/18 roadmap.
def default_tasks():
    return [
        Task("training", lambda: training_task(CTX), interval=6, priority=10, enabled=True),
        # --- roadmap stubs (disabled until their UI templates exist) ---
        Task("daily_collect", lambda: _stub("daily_collect",
             "Claim mail, in-city resources, wheel, eggs, patrol, free chests on a timer.")(CTX),
             interval=3600, priority=30, enabled=False),
        Task("alliance", lambda: _stub("alliance",
             "Alliance Help auto-tap + Science donation + Gift claim, every ~4h.")(CTX),
             interval=14400, priority=25, enabled=False),
        Task("auto_shield", lambda: _stub("auto_shield",
             "Detect incoming attack/scout -> apply shield item (3d->24h->8h). Fixed UI.")(CTX),
             interval=20, priority=1, enabled=False),
        Task("gather", lambda: _stub("gather",
             "Dispatch idle marches to L14 food tiles; needs zoom-robust map nav.")(CTX),
             interval=120, priority=15, enabled=False),
        Task("rally_join", lambda: _stub("rally_join",
             "Join boss rallies filtered by <5min / boss-only / march-feasible.")(CTX),
             interval=60, priority=12, enabled=False),
        Task("monster", lambda: _stub("monster",
             "Attack monsters / auto-set boss rallies; needs map scan + presets.")(CTX),
             interval=90, priority=14, enabled=False),
    ]


CTX = None  # set by run()


def run(device=DEVICE, tasks=None, max_ticks=None, logger=print,
        llm_fallback=False, stuck_threshold=6):
    """Main loop. STOPS on the account-disconnect screen (never taps Quit/Restart).
    max_ticks bounds the loop for tests; None = run forever. If llm_fallback is on,
    a stuck deterministic layer escalates to the LLM vision agent (costs credits)."""
    global CTX
    CTX = Ctx(device, logger)
    sched = Scheduler()
    for t in (tasks or default_tasks()):
        if t.enabled:
            sched.add(t)
    watch = wd.Watchdog(device, grab_fn=CTX.screencap)
    CTX.log(f"orchestrator: {len([t for t in (tasks or default_tasks()) if t.enabled])} task(s) enabled"
            + (" + LLM fallback" if llm_fallback else ""))

    ticks = 0
    stuck = 0
    while max_ticks is None or ticks < max_ticks:
        ticks += 1
        img = CTX.screencap()
        if screen_fsm.is_disconnect(img):
            CTX.log("DISCONNECT (account taken — likely easy-bot.club). Stopping; will NOT tap.")
            _notify("DISCONNECT — account taken (easy-bot.club?). Stopped; will NOT tap Quit/Restart.", "alert")
            return "disconnect"
        try:
            ran = sched.run_due()
            stuck = 0 if ran else stuck
        except Exception as e:
            import humanize
            cause = getattr(e, "cause", e)
            if isinstance(cause, humanize.TooManyClicks):
                CTX.log(f"SELF-DETECTED BOT-TELL ({cause}) — pausing for human (kb/30 fail-safe).")
                _notify(f"Self-detected bot-tell ({cause}) — paused for human.", "alert")
                return "stopped"
            stuck += 1
            CTX.log(f"task not ready ({stuck}/{stuck_threshold}): {e}")
            ran = None
        if stuck >= stuck_threshold:
            if llm_fallback:
                act = llm_resolve(CTX, img)
                if act and act.get("action") == "stop":
                    CTX.log("LLM said stop — halting for human/deterministic.")
                    return "stopped"
            else:
                CTX.log("stuck; LLM fallback off — deterministic recovery only.")
            stuck = 0
        if ran is None:
            nxt = sched.seconds_until_next() or 0.5
            time.sleep(min(nxt, 1.0))
    return "done"


if __name__ == "__main__":
    import sys

    # dry-run self-test: fake device I/O, verify scheduling + disconnect guard,
    # no ADB, no real taps.
    log = []
    calls = {"train": 0}

    def fake_training(ctx):
        calls["train"] += 1
        return None

    # a disconnect appears on tick 8
    frame = {"n": 0}
    class FakeCtx(Ctx):
        def __init__(self): self.device = "test"; self._log = log.append
        def screencap(self):
            frame["n"] += 1
            return "DISCONNECT_FRAME" if frame["n"] >= 8 else "OK_FRAME"

    import screen_fsm as F
    F.is_disconnect = lambda img, min_score=0.85: img == "DISCONNECT_FRAME"
    import watchdog as W
    W.Watchdog = lambda *a, **k: type("W", (), {"tick": lambda s: "ok"})()

    tasks = [Task("training", lambda: fake_training(None), interval=1, priority=10, enabled=True)]

    CTX = FakeCtx()
    clock = {"t": 1000.0}
    sched = Scheduler(clock=lambda: clock["t"])
    for t in tasks:
        sched.add(t)
    ticks = 0
    result = None
    while ticks < 30:
        ticks += 1
        img = CTX.screencap()
        if F.is_disconnect(img):
            result = "disconnect"; break
        sched.run_due()
        clock["t"] += 1.0

    ok = result == "disconnect" and calls["train"] >= 5
    print(f"training ran {calls['train']}x before disconnect at tick {ticks}")
    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
