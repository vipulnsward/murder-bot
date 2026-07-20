"""alliance — Embassy help, gift/treasure claim, and gem-safe tech donation (kb/28).

Shipped + tested here (pure logic): AlliancePolicy.decide() returns an ORDERED
list of actions from a perception snapshot — "help_all" (Embassy help-all hand),
"claim_gifts" (alliance gift/treasure chests), "donate" (alliance science/tech).

GEM SAFETY (non-negotiable, tested): NEVER donate a gem-priced tier. The policy
only ever returns "donate" when donation_cost_type is "free" or "resource" AND the
daily donation cap isn't reached. A "gem" cost type is refused outright. The
injectable act() must tap the free/resource donate control only, never a gem one.

[LIVE-CAPTURE] to wire on a clean session (kb/28 + kb/31):
  perceive(img) -> Perception   (help badge, gifts red-dot, donation availability + cost type)
  act(ctx, action) -> bool      (tap the action's UI path; free/resource donate only)
"""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED_DONATION_COSTS = ("free", "resource")   # gem tiers are refused


@dataclass
class Perception:
    help_pending: bool = False
    gifts_available: bool = False
    donation_available: bool = False
    donation_cost_type: str | None = None       # "free" | "resource" | "gem" | None
    donations_today: int = 0


@dataclass
class AlliancePolicy:
    donations_per_day: int = 20
    help_cooldown_s: float = 60.0

    def decide(self, *, perception: Perception, now: float, last_help: float | None = None):
        p = perception
        actions = []

        if p.help_pending and (last_help is None or (now - last_help) >= self.help_cooldown_s):
            actions.append("help_all")

        if p.gifts_available:
            actions.append("claim_gifts")

        if (p.donation_available
                and p.donation_cost_type in ALLOWED_DONATION_COSTS   # <-- gem tiers never qualify
                and p.donations_today < self.donations_per_day):
            actions.append("donate")

        return actions


def _not_wired(*_a, **_k):
    raise NotImplementedError("[LIVE-CAPTURE] alliance perceive/act not wired — see kb/28.")


def make_task(perceive=None, act=None, policy=None, clock=None, notify=None, state=None):
    """Return run(ctx) for the orchestrator. perceive(img)->Perception; act(ctx,action)->bool.
    Both default to a [LIVE-CAPTURE] stub that raises (never taps blindly)."""
    import time as _t
    policy = policy or AlliancePolicy()
    clock = clock or _t.time
    perceive = perceive or _not_wired
    act = act or _not_wired
    state = state if state is not None else {"last_help": None}

    def run(ctx):
        img = ctx.screencap()
        perception = perceive(img)
        actions = policy.decide(perception=perception, now=clock(), last_help=state.get("last_help"))
        done = []
        for a in actions:
            if act(ctx, a):                         # free/resource paths only — never a gem donate
                if a == "help_all":
                    state["last_help"] = clock()
                done.append(a)
        if done:
            ctx.log(f"alliance: {done}")
            if notify:
                notify(f"alliance: {', '.join(done)}", "info")
        return None

    run.state = state
    return run


if __name__ == "__main__":
    ok = True
    P = AlliancePolicy(donations_per_day=20, help_cooldown_s=60)
    NOW = 1_000_000.0

    # 1) help pending -> help_all
    a = P.decide(perception=Perception(help_pending=True), now=NOW)
    print(f"1 help pending -> {a}")
    ok &= a == ["help_all"]

    # 2) help on cooldown -> no help_all
    a = P.decide(perception=Perception(help_pending=True), now=NOW, last_help=NOW - 10)
    print(f"2 help within cooldown -> {a}")
    ok &= a == []

    # 3) gifts available -> claim_gifts
    a = P.decide(perception=Perception(gifts_available=True), now=NOW)
    print(f"3 gifts -> {a}")
    ok &= a == ["claim_gifts"]

    # 4) free / resource donation -> donate
    a = P.decide(perception=Perception(donation_available=True, donation_cost_type="free"), now=NOW)
    print(f"4a free donation -> {a}")
    ok &= a == ["donate"]
    a = P.decide(perception=Perception(donation_available=True, donation_cost_type="resource"), now=NOW)
    print(f"4b resource donation -> {a}")
    ok &= a == ["donate"]

    # 5) GEM donation -> REFUSED (gem-safe) — the critical case
    a = P.decide(perception=Perception(donation_available=True, donation_cost_type="gem"), now=NOW)
    print(f"5 GEM donation -> {a} (must NOT contain 'donate')")
    ok &= "donate" not in a

    # 6) daily donation cap reached -> no donate
    a = P.decide(perception=Perception(donation_available=True, donation_cost_type="free",
                                       donations_today=20), now=NOW)
    print(f"6 donation cap reached -> {a}")
    ok &= "donate" not in a

    # 7) everything pending -> ordered [help_all, claim_gifts, donate]
    a = P.decide(perception=Perception(help_pending=True, gifts_available=True,
                                       donation_available=True, donation_cost_type="resource"), now=NOW)
    print(f"7 all pending -> {a}")
    ok &= a == ["help_all", "claim_gifts", "donate"]

    # 8) nothing pending -> no actions
    a = P.decide(perception=Perception(), now=NOW)
    print(f"8 nothing -> {a}")
    ok &= a == []

    # 9) wired make_task: calls act for each action, records help time; refuses gem donate end-to-end
    called = []
    run = make_task(
        perceive=lambda img: Perception(help_pending=True, donation_available=True, donation_cost_type="gem"),
        act=lambda ctx, action: (called.append(action) or True),
        clock=lambda: NOW,
    )
    class FakeCtx:
        def screencap(self): return "frame"
        def log(self, m): pass
    run(FakeCtx())
    print(f"9 wired (gem donation present) acted -> {called} (help yes, donate NO)")
    ok &= called == ["help_all"] and run.state["last_help"] == NOW

    # 10) unwired -> raises [LIVE-CAPTURE]
    raised = False
    try:
        make_task()(FakeCtx())
    except NotImplementedError as e:
        raised = "[LIVE-CAPTURE]" in str(e)
    print(f"10 unwired raises LIVE-CAPTURE = {raised}")
    ok &= raised

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
