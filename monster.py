"""monster — solo monster and boss target selection (kb/25).

Shipped + tested here (pure logic): MonsterPolicy.decide() chooses the highest
configured target within the level cap, stamina budget, and idle-march limit.

[LIVE-CAPTURE] to wire: perceive(img) reads map targets, stamina, and idle
marches; act(ctx, target) attacks or rallies with a saved preset. Gem-safe:
actions use marches and stamina items only, never a gem refill path.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Perception:
    """A snapshot from the game (produced by the [LIVE-CAPTURE] perceive())."""
    available_targets: list = field(default_factory=list)
    current_stamina: int = 0
    idle_march_slots: int = 0


class MonsterPolicy:
    def __init__(self, preferred_types=(), max_level=0, min_stamina_reserve=0):
        self.preferred_types = tuple(preferred_types)
        self.max_level = max_level
        self.min_stamina_reserve = min_stamina_reserve

    def decide(self, perception: Perception):
        """Best preferred affordable target within capability, or None."""
        if perception.idle_march_slots <= 0:
            return None
        stamina_budget = perception.current_stamina - self.min_stamina_reserve
        eligible = [
            target for target in perception.available_targets
            if target.get("kind") in ("monster", "boss")
            and target.get("type") in self.preferred_types
            and target.get("level", 0) <= self.max_level
            and target.get("stamina_cost", 0) <= stamina_budget
        ]
        if not eligible:
            return None
        return min(
            eligible,
            key=lambda target: (
                self.preferred_types.index(target["type"]),
                -target["level"],
            ),
        )


def _not_wired(*_a, **_k):
    raise NotImplementedError("[LIVE-CAPTURE] monster perceive/act not wired — see kb/25.")


def make_task(perceive=None, act=None, policy=None, clock=None, notify=None, state=None):
    """Return run(ctx) for the orchestrator. perceive(img)->Perception;
    act(ctx,target)->bool. Both default to a loud [LIVE-CAPTURE] stub."""
    policy = policy or MonsterPolicy()
    perceive = perceive or _not_wired
    act = act or _not_wired

    def run(ctx):
        target = policy.decide(perceive(ctx.screencap()))
        if target is None:
            return None
        if act(ctx, target):
            ctx.log(f"monster: dispatched {target['type']} level {target['level']}")
            if notify:
                notify(f"monster: dispatched {target['type']} L{target['level']}", "info")
        return None

    return run


if __name__ == "__main__":
    ok = True
    P = MonsterPolicy(preferred_types=("Ymir", "Cerberus"), max_level=3,
                      min_stamina_reserve=10)
    targets = [
        {"kind": "boss", "type": "Cerberus", "level": 3, "stamina_cost": 20},
        {"kind": "boss", "type": "Ymir", "level": 2, "stamina_cost": 20},
        {"kind": "boss", "type": "Ymir", "level": 3, "stamina_cost": 30},
    ]
    chosen = P.decide(Perception(available_targets=targets, current_stamina=40,
                                 idle_march_slots=1))
    print(f"1 preferred+highest -> {chosen['type']} L{chosen['level']}")
    ok &= chosen["type"] == "Ymir" and chosen["level"] == 3

    too_high = P.decide(Perception(
        available_targets=[{"kind": "boss", "type": "Ymir", "level": 4, "stamina_cost": 20}],
        current_stamina=100,
        idle_march_slots=1,
    ))
    print(f"2 above level cap -> {too_high}")
    ok &= too_high is None

    too_expensive = P.decide(Perception(
        available_targets=[{"kind": "boss", "type": "Ymir", "level": 3, "stamina_cost": 31}],
        current_stamina=40,
        idle_march_slots=1,
    ))
    print(f"3 below stamina reserve -> {too_expensive}")
    ok &= too_expensive is None

    no_march = P.decide(Perception(available_targets=targets, current_stamina=100,
                                   idle_march_slots=0))
    print(f"4 no idle march -> {no_march}")
    ok &= no_march is None

    class FakeCtx:
        def screencap(self): return "frame"
        def log(self, m): pass

    raised = False
    try:
        make_task()(FakeCtx())
    except NotImplementedError as e:
        raised = "[LIVE-CAPTURE]" in str(e)
    print(f"5 unwired raises LIVE-CAPTURE = {raised}")
    ok &= raised

    attacked = []
    run = make_task(
        perceive=lambda img: Perception(available_targets=targets, current_stamina=40,
                                        idle_march_slots=1),
        act=lambda ctx, target: (attacked.append(target) or True),
        policy=P,
    )
    run(FakeCtx())
    print(f"6 wired task attacked -> {attacked[0]['type']} L{attacked[0]['level']}")
    ok &= len(attacked) == 1 and attacked[0]["type"] == "Ymir"

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
