"""rally_join — alliance rally joining (kb/24).

Shipped + tested here (pure logic): RallyJoinPolicy.decide() filters perceived
rallies by boss preference, countdown, feasibility, open slots, and available
marches, then orders them by soonest launch.

[LIVE-CAPTURE] to wire: perceive(img) reads the Alliance War list and idle
march count; act(ctx, rally) joins through the saved march preset. Gem-safe:
joining uses marches only and never follows a gem path.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Perception:
    """A snapshot from the game (produced by the [LIVE-CAPTURE] perceive())."""
    rallies: list = field(default_factory=list)
    idle_march_slots: int = 0


class RallyJoinPolicy:
    def __init__(self, only_boss=True, max_seconds_left=300,
                 require_feasible=True, reserved_free_marches=0):
        self.only_boss = only_boss
        self.max_seconds_left = max_seconds_left
        self.require_feasible = require_feasible
        self.reserved_free_marches = max(0, reserved_free_marches)

    def decide(self, perception: Perception):
        """Ordered joinable rallies, capped to available unreserved marches."""
        joinable = []
        for rally in perception.rallies:
            seconds_left = rally.get("seconds_left", 0)
            if self.only_boss and not rally.get("is_boss"):
                continue
            if seconds_left <= 0 or seconds_left > self.max_seconds_left:
                continue
            if self.require_feasible and not rally.get("march_feasible"):
                continue
            if not rally.get("slots_open"):
                continue
            joinable.append(rally)
        joinable.sort(key=lambda rally: rally["seconds_left"])
        available = max(0, perception.idle_march_slots - self.reserved_free_marches)
        return joinable[:available]


def _not_wired(*_a, **_k):
    raise NotImplementedError("[LIVE-CAPTURE] rally_join perceive/act not wired — see kb/24.")


def make_task(perceive=None, act=None, policy=None, clock=None, notify=None, state=None):
    """Return run(ctx) for the orchestrator. perceive(img)->Perception;
    act(ctx,rally)->bool. Both default to a loud [LIVE-CAPTURE] stub."""
    policy = policy or RallyJoinPolicy()
    perceive = perceive or _not_wired
    act = act or _not_wired

    def run(ctx):
        perception = perceive(ctx.screencap())
        joined = []
        for rally in policy.decide(perception):
            if act(ctx, rally):
                joined.append(rally)
        if joined:
            ctx.log(f"rally_join: joined {len(joined)} rallies")
            if notify:
                notify(f"rallies: joined {len(joined)}", "info")
        return None

    return run


if __name__ == "__main__":
    ok = True
    P = RallyJoinPolicy(max_seconds_left=300)
    rallies = [
        {"is_boss": True, "seconds_left": 240, "march_feasible": True, "slots_open": True},
        {"is_boss": True, "seconds_left": 30, "march_feasible": True, "slots_open": True},
        {"is_boss": False, "seconds_left": 20, "march_feasible": True, "slots_open": True},
        {"is_boss": True, "seconds_left": 0, "march_feasible": True, "slots_open": True},
        {"is_boss": True, "seconds_left": 60, "march_feasible": False, "slots_open": True},
        {"is_boss": True, "seconds_left": 90, "march_feasible": True, "slots_open": False},
        {"is_boss": True, "seconds_left": 301, "march_feasible": True, "slots_open": True},
    ]
    chosen = P.decide(Perception(rallies=rallies, idle_march_slots=4))
    print(f"1 filters+orders -> {[r['seconds_left'] for r in chosen]}")
    ok &= [r["seconds_left"] for r in chosen] == [30, 240]

    many = [
        {"is_boss": True, "seconds_left": seconds, "march_feasible": True, "slots_open": True}
        for seconds in (40, 30, 20, 10)
    ]
    capped = P.decide(Perception(rallies=many, idle_march_slots=2))
    print(f"2 idle-march cap -> {[r['seconds_left'] for r in capped]}")
    ok &= len(capped) == 2 and [r["seconds_left"] for r in capped] == [10, 20]

    reserved = RallyJoinPolicy(reserved_free_marches=1).decide(
        Perception(rallies=many, idle_march_slots=2)
    )
    print(f"3 reserve one march -> {len(reserved)} join")
    ok &= len(reserved) == 1

    class FakeCtx:
        def screencap(self): return "frame"
        def log(self, m): pass

    raised = False
    try:
        make_task()(FakeCtx())
    except NotImplementedError as e:
        raised = "[LIVE-CAPTURE]" in str(e)
    print(f"4 unwired raises LIVE-CAPTURE = {raised}")
    ok &= raised

    joined = []
    run = make_task(
        perceive=lambda img: Perception(rallies=many, idle_march_slots=1),
        act=lambda ctx, rally: (joined.append(rally) or True),
    )
    run(FakeCtx())
    print(f"5 wired task joined -> {len(joined)}")
    ok &= len(joined) == 1

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
