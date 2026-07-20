"""base_dev — gem-safe building, Academy research, and item speedups (kb/27).

Shipped + tested here (pure logic, no UI risk): BaseDevPolicy.decide() picks
the next action from a perception snapshot. Free builders upgrade the highest
priority building, idle Academy research runs next, and construction speedups
use owned ITEMS only when enough build time remains.

GEM SAFETY (non-negotiable): this module never emits finish, instant, or any
gem-spend action. With no owned speedup item it idles. The injectable act()
must use item rows only and never the gem instant-finish control.

[LIVE-CAPTURE] to wire on a clean session (kb/27 + kb/31):
  perceive(img) -> Perception
  act(ctx, decision) -> bool
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Perception:
    upgradable: list = field(default_factory=list)
    free_build_slots: int = 0
    in_progress: list = field(default_factory=list)
    research_available: bool = False
    speedup_items: list = field(default_factory=list)


@dataclass
class Decision:
    action: str
    building: str | None = None
    item: str | None = None
    reason: str = ""


@dataclass
class BaseDevPolicy:
    preferred_speedup_item: str | None = None
    min_speedup_remaining_s: float = 5 * 60

    def decide(self, *, perception: Perception, now: float) -> Decision:
        if perception.free_build_slots > 0 and perception.upgradable:
            buildings = [self._building(entry) for entry in perception.upgradable]
            key, level, priority = min(buildings, key=lambda b: (-b[2], b[0], b[1]))
            return Decision("upgrade", building=key,
                            reason=f"priority={priority} level={level} at {now}")

        if perception.research_available:
            return Decision("research", reason=f"Academy available at {now}")

        builds = [self._running(entry) for entry in perception.in_progress]
        builds = [build for build in builds if build[1] >= self.min_speedup_remaining_s]
        item = self._speedup_item(perception.speedup_items)
        if builds and item is not None:
            building, remaining_s = min(builds, key=lambda b: (-b[1], b[0]))
            return Decision("speedup", building=building, item=item,
                            reason=f"{remaining_s}s remaining; owned item {item}")

        return Decision("idle", reason="no safe base-development action")

    @staticmethod
    def _building(entry):
        if isinstance(entry, dict):
            return str(entry["key"]), entry["level"], entry["priority"]
        key, level, priority = entry
        return str(key), level, priority

    @staticmethod
    def _running(entry):
        if isinstance(entry, dict):
            return str(entry.get("key", entry.get("building"))), entry["remaining_s"]
        key, remaining_s = entry
        return str(key), remaining_s

    def _speedup_item(self, items):
        owned = sorted(((str(key), seconds) for key, seconds in items if seconds > 0),
                       key=lambda item: (item[1], item[0]))
        if self.preferred_speedup_item is not None:
            preferred = next((key for key, _ in owned
                              if key == self.preferred_speedup_item), None)
            if preferred is not None:
                return preferred
        return owned[0][0] if owned else None


def _not_wired(*_a, **_k):
    raise NotImplementedError("[LIVE-CAPTURE] base_dev perceive/act not wired — see kb/27.")


def make_task(perceive=None, act=None, policy=None, clock=None, notify=None, state=None):
    """Return run(ctx) for the orchestrator with injectable perception and action."""
    import time as _t
    policy = policy or BaseDevPolicy()
    clock = clock or _t.time
    perceive = perceive or _not_wired
    act = act or _not_wired
    state = state if state is not None else {}

    def run(ctx):
        img = ctx.screencap()
        perception = perceive(img)
        decision = policy.decide(perception=perception, now=clock())
        ctx.log(f"base_dev: {decision.action} ({decision.reason})")
        if decision.action != "idle":
            acted = act(ctx, decision)
            if acted and notify:
                notify(f"base_dev: {decision.action}", "info")
        return None

    run.state = state
    return run


if __name__ == "__main__":
    ok = True
    NOW = 1_000_000.0
    P = BaseDevPolicy(preferred_speedup_item="construction_5m",
                      min_speedup_remaining_s=300)

    d = P.decide(perception=Perception(
        upgradable=[("farm", 10, 5), ("academy", 9, 10), ("keep", 9, 10)],
        free_build_slots=1,
    ), now=NOW)
    print(f"1 free slot -> {d.action} building={d.building} (expect academy)")
    ok &= d.action == "upgrade" and d.building == "academy"

    d = P.decide(perception=Perception(
        upgradable=[("keep", 10, 10)],
        free_build_slots=0,
    ), now=NOW)
    print(f"2 no free slot -> {d.action} (expect no upgrade)")
    ok &= d.action != "upgrade"

    d = P.decide(perception=Perception(
        upgradable=[("keep", 10, 10)],
        free_build_slots=0,
        research_available=True,
    ), now=NOW)
    print(f"3 Academy available -> {d.action} (expect research)")
    ok &= d.action == "research"

    d = P.decide(perception=Perception(
        in_progress=[{"key": "keep", "remaining_s": 3600}],
        speedup_items=[("general_1m", 60), ("construction_5m", 300)],
    ), now=NOW)
    print(f"4 owned item -> {d.action} item={d.item} (expect construction_5m)")
    ok &= d.action == "speedup" and d.item == "construction_5m"

    d = P.decide(perception=Perception(
        in_progress=[("keep", 3600)],
        speedup_items=[],
    ), now=NOW)
    gem_action = any(word in d.action for word in ("gem", "finish", "instant"))
    print(f"5 zero items -> {d.action} item={d.item} gem_action={gem_action}")
    ok &= d.action == "idle" and d.item is None and not gem_action

    acted = []
    run = make_task(
        perceive=lambda img: Perception(research_available=True),
        act=lambda ctx, decision: (acted.append(decision.action) or True),
        clock=lambda: NOW,
    )

    class FakeCtx:
        def screencap(self): return "frame"
        def tap(self, x, y, label=""): return None
        def swipe(self, *args, **kwargs): return None
        def log(self, message): return None

    run(FakeCtx())
    print(f"6 wired task called act -> {acted}")
    ok &= acted == ["research"]

    raised = False
    try:
        make_task()(FakeCtx())
    except NotImplementedError as e:
        raised = str(e) == "[LIVE-CAPTURE] base_dev perceive/act not wired — see kb/27."
    print(f"7 unwired raises LIVE-CAPTURE = {raised}")
    ok &= raised

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
