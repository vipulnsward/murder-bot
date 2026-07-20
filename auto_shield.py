"""auto_shield — reactive + proactive Truce/shield application (kb/26).

GEM SAFETY (non-negotiable): shields are ITEMS, applied via the "Use" button.
This module never touches a gem-priced "Buy & Use" / instant option. The apply
step is injectable and the default is a no-op that must be wired to the item path.

What ships HERE, fully unit-tested (pure logic, no UI risk):
  - ShieldPolicy.decide(...) — WHEN to shield and WHICH item to spend, given a
    perception snapshot (incoming? ETA? already shielded until?). Handles:
      * already-covered  -> hold (never waste an item re-shielding)
      * reactive         -> incoming attack within react_within_s -> apply
      * proactive        -> keep a shield up when unshielded (opt-in)
      * item selection    -> smallest item that covers desired_cover_s (thrift),
                            else the largest available; none available -> hold.

What needs a CLEAN SESSION to wire ([LIVE-CAPTURE], see kb/26 + kb/31):
  - perceive(img) -> Perception: read the Watchtower "enemy incoming" banner + ETA
    (OCR) and the current shield timer; detect which truce items you own.
  - apply_shield(ctx, item): City -> Items/Buff -> Truce -> the item -> "Use".
Wire those two, flip the orchestrator Task to enabled=True, and it runs on the
scheduler at high priority (survival gate for unattended play).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Truce items, (key, seconds). Ordered short -> long for thrift selection.
SHIELD_ITEMS = [
    ("truce_1h", 1 * 3600),
    ("truce_8h", 8 * 3600),
    ("truce_24h", 24 * 3600),
    ("truce_3d", 3 * 24 * 3600),
]
_DUR = dict(SHIELD_ITEMS)


@dataclass
class Perception:
    """A snapshot from the game (produced by the [LIVE-CAPTURE] perceive())."""
    incoming: bool = False
    eta_s: float | None = None            # seconds until enemy lands, if known
    shielded_until: float | None = None   # epoch ts the current shield expires, if any
    available_items: list = field(default_factory=list)  # keys present in SHIELD_ITEMS, owned


@dataclass
class Decision:
    action: str                 # "apply" | "hold"
    item: str | None = None     # which shield item, when action == "apply"
    reason: str = ""


class ShieldPolicy:
    def __init__(self, react_within_s=15 * 60, reshield_margin_s=10 * 60,
                 desired_cover_s=8 * 3600, proactive=False):
        # react to attacks landing within react_within_s; treat a shield with more
        # than reshield_margin_s left as "already covered"; when applying, aim to
        # cover desired_cover_s (e.g. an away/sleep block).
        self.react_within_s = react_within_s
        self.reshield_margin_s = reshield_margin_s
        self.desired_cover_s = desired_cover_s
        self.proactive = proactive

    def choose_item(self, available, desired_cover_s=None):
        """Smallest owned item that covers desired_cover_s; else the largest owned; else None."""
        desired = self.desired_cover_s if desired_cover_s is None else desired_cover_s
        owned = [(k, _DUR[k]) for k in SHIELD_ITEMS_keys() if k in available]
        if not owned:
            return None
        adequate = [(k, d) for k, d in owned if d >= desired]
        if adequate:
            return min(adequate, key=lambda kd: kd[1])[0]     # smallest adequate (thrift)
        return max(owned, key=lambda kd: kd[1])[0]            # else biggest we have

    def decide(self, *, perception: Perception, now: float) -> Decision:
        p = perception
        covered = p.shielded_until is not None and (p.shielded_until - now) > self.reshield_margin_s
        if covered:
            return Decision("hold", reason=f"already shielded ~{int((p.shielded_until - now)/60)}m")

        threat = p.incoming and (p.eta_s is None or p.eta_s <= self.react_within_s)
        if threat:
            item = self.choose_item(p.available_items)
            if item is None:
                return Decision("hold", reason="INCOMING but no truce items owned — NOTIFY human")
            return Decision("apply", item=item, reason=f"incoming (eta={p.eta_s}) -> {item}")

        if self.proactive and (p.shielded_until is None or p.shielded_until <= now):
            item = self.choose_item(p.available_items)
            if item is not None:
                return Decision("apply", item=item, reason=f"proactive keep-shielded -> {item}")
            return Decision("hold", reason="proactive but no items")

        return Decision("hold", reason="no threat / safe")


def SHIELD_ITEMS_keys():
    return [k for k, _ in SHIELD_ITEMS]


def _not_wired(*_a, **_k):
    raise NotImplementedError("[LIVE-CAPTURE] auto_shield perception/apply not wired — see kb/26.")


def make_task(perceive=None, apply_shield=None, policy=None, clock=None, notify=None):
    """Return a run(ctx) callable for the orchestrator.

    perceive(img) -> Perception ; apply_shield(ctx, item) -> bool. Both default to
    a [LIVE-CAPTURE] stub that raises, so a mis-enabled task fails loudly (NotReady)
    rather than tapping blindly. Gem-safe: apply_shield must use the item "Use" path.
    """
    import time as _t
    policy = policy or ShieldPolicy()
    clock = clock or _t.time
    perceive = perceive or _not_wired
    apply_shield = apply_shield or _not_wired

    def run(ctx):
        img = ctx.screencap()
        p = perceive(img)
        d = policy.decide(perception=p, now=clock())
        ctx.log(f"auto_shield: {d.action} ({d.reason})")
        if d.action == "apply":
            ok = apply_shield(ctx, d.item)   # MUST tap item "Use", never a gem option
            if notify:
                notify(f"Shield applied: {d.item}", "warn")
            return None if ok else None
        if "NOTIFY human" in d.reason and notify:
            notify("INCOMING attack but no truce items — manual action needed!", "alert")
        return None

    return run


if __name__ == "__main__":
    ok = True
    P = ShieldPolicy(react_within_s=900, reshield_margin_s=600, desired_cover_s=8 * 3600)
    NOW = 1_000_000.0
    ALL = SHIELD_ITEMS_keys()

    # 1) already covered (shield with > margin left) -> hold, no item spent
    d = P.decide(perception=Perception(incoming=True, eta_s=60, shielded_until=NOW + 3600,
                                       available_items=ALL), now=NOW)
    print(f"1 covered -> {d.action} ({d.reason})")
    ok &= d.action == "hold" and d.item is None

    # 2) shield about to lapse (< margin) + incoming -> apply
    d = P.decide(perception=Perception(incoming=True, eta_s=120, shielded_until=NOW + 60,
                                       available_items=ALL), now=NOW)
    print(f"2 lapsing+incoming -> {d.action} item={d.item}")
    ok &= d.action == "apply" and d.item is not None

    # 3) incoming within window, thrift pick = smallest item covering 8h desired = truce_24h
    #    (8h item only covers exactly 8h; desired 8h -> 8h adequate -> picks truce_8h)
    d = P.decide(perception=Perception(incoming=True, eta_s=300, available_items=ALL), now=NOW)
    print(f"3 incoming -> apply item={d.item} (expect truce_8h, smallest >= 8h)")
    ok &= d.action == "apply" and d.item == "truce_8h"

    # 4) incoming but only a 1h item owned -> no item covers 8h -> fall back to largest owned (1h)
    d = P.decide(perception=Perception(incoming=True, eta_s=30, available_items=["truce_1h"]), now=NOW)
    print(f"4 only-1h -> apply item={d.item} (expect truce_1h fallback)")
    ok &= d.action == "apply" and d.item == "truce_1h"

    # 5) incoming, NO items -> hold + flag for human
    d = P.decide(perception=Perception(incoming=True, eta_s=30, available_items=[]), now=NOW)
    print(f"5 incoming+no-items -> {d.action} ({d.reason})")
    ok &= d.action == "hold" and "no truce items" in d.reason

    # 6) attack too far out (eta beyond react window) and not proactive -> hold
    d = P.decide(perception=Perception(incoming=True, eta_s=3600, available_items=ALL), now=NOW)
    print(f"6 far-attack -> {d.action}")
    ok &= d.action == "hold"

    # 7) proactive mode, unshielded, safe -> apply to keep a shield up
    Pp = ShieldPolicy(proactive=True, desired_cover_s=24 * 3600)
    d = Pp.decide(perception=Perception(incoming=False, shielded_until=None, available_items=ALL), now=NOW)
    print(f"7 proactive-unshielded -> apply item={d.item} (expect truce_24h)")
    ok &= d.action == "apply" and d.item == "truce_24h"

    # 8) proactive but already covered -> hold
    d = Pp.decide(perception=Perception(shielded_until=NOW + 2 * 3600, available_items=ALL), now=NOW)
    print(f"8 proactive-covered -> {d.action}")
    ok &= d.action == "hold"

    # 9) make_task default perception is a loud [LIVE-CAPTURE] stub (never taps blindly)
    run = make_task()
    class FakeCtx:
        def screencap(self): return "frame"
        def log(self, m): pass
    raised = False
    try:
        run(FakeCtx())
    except NotImplementedError as e:
        raised = "[LIVE-CAPTURE]" in str(e)
    print(f"9 unwired task raises LIVE-CAPTURE = {raised}")
    ok &= raised

    # 10) make_task wired with mocks: incoming -> apply_shield called with the chosen item (gem-safe path)
    applied = {}
    run2 = make_task(
        perceive=lambda img: Perception(incoming=True, eta_s=60, available_items=ALL),
        apply_shield=lambda ctx, item: applied.setdefault("item", item) or True,
        clock=lambda: NOW,
    )
    run2(FakeCtx())
    print(f"10 wired task applied item={applied.get('item')}")
    ok &= applied.get("item") == "truce_8h"

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
