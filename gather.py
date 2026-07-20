"""gather — reserve-safe resource-tile dispatch (kb/23).

GEM SAFETY: gathering has no gem path, so there is nothing to guard there.
Marches are the scarce resource: GatherPolicy always keeps reserved_for_rallies
march slots free so monster rallies can still launch.

Shipped + tested here (pure logic, no I/O): GatherPolicy.decide() selects the
resource tiles to gather from using the available march capacity, preferred
resource types, and highest tile levels.

[LIVE-CAPTURE] to wire on a clean session (kb/23 + kb/31):
  perceive(img) -> Perception
  dispatch(ctx, tile) -> bool
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Perception:
    idle_march_slots: int = 0
    total_march_slots: int = 0
    marches_out: int = 0
    available_tiles: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class GatherPolicy:
    reserved_for_rallies: int = 1
    preferred_min_level: int = 1
    preferred_resource_types: tuple[str, ...] = ("ore", "stone", "lumber", "food")

    def decide(self, perception: Perception):
        p = perception
        sendable = max(0, (p.total_march_slots - p.marches_out) - self.reserved_for_rallies)
        count = min(sendable, p.idle_march_slots, len(p.available_tiles))
        resource_rank = {res_type: rank for rank, res_type in enumerate(self.preferred_resource_types)}
        tiles = sorted(
            p.available_tiles,
            key=lambda tile: (
                resource_rank.get(tile[1], len(resource_rank)),
                tile[0] < self.preferred_min_level,
                -tile[0],
                tile[1],
            ),
        )
        return tiles[:count]


def _not_wired(*_a, **_k):
    raise NotImplementedError("[LIVE-CAPTURE] gather perceive/dispatch not wired see kb/23.")


def make_task(perceive=None, dispatch=None, policy=None, clock=None, notify=None, state=None):
    """Return run(ctx) for the orchestrator. perceive(img)->Perception;
    dispatch(ctx,tile)->bool. Both default to a [LIVE-CAPTURE] stub that raises."""
    policy = policy or GatherPolicy()
    perceive = perceive or _not_wired
    dispatch = dispatch or _not_wired
    state = state if state is not None else {}

    def run(ctx):
        img = ctx.screencap()
        perception = perceive(img)
        chosen = policy.decide(perception)
        for tile in chosen:
            dispatch(ctx, tile)
        ctx.log(f"gather: dispatched {chosen}")
        if chosen and notify:
            notify(f"gather: dispatched {len(chosen)} march(es)", "info")
        return None

    run.state = state
    return run


if __name__ == "__main__":
    ok = True
    P = GatherPolicy(reserved_for_rallies=2, preferred_resource_types=("ore", "food"))
    TILES = [(8, "ore"), (10, "food"), (12, "ore")]

    sent = P.decide(Perception(idle_march_slots=3, total_march_slots=6,
                               marches_out=3, available_tiles=TILES))
    blocked = P.decide(Perception(idle_march_slots=2, total_march_slots=5,
                                  marches_out=3, available_tiles=TILES))
    print(f"1 reservation guard -> sent={sent}, blocked={blocked}")
    ok &= len(sent) == 1 and blocked == [] and 6 - 3 - len(sent) >= P.reserved_for_rallies

    idle_limited = P.decide(Perception(idle_march_slots=2, total_march_slots=8,
                                       marches_out=0, available_tiles=TILES))
    tile_limited = P.decide(Perception(idle_march_slots=4, total_march_slots=8,
                                       marches_out=0, available_tiles=[(9, "ore")]))
    print(f"2 idle/tile caps -> idle={idle_limited}, tiles={tile_limited}")
    ok &= len(idle_limited) == 2 and len(tile_limited) == 1

    ordered = P.decide(Perception(idle_march_slots=5, total_march_slots=8, marches_out=0,
                                  available_tiles=[(10, "food"), (8, "ore"), (16, "stone"),
                                                   (12, "food"), (12, "ore")]))
    expected = [(12, "ore"), (8, "ore"), (12, "food"), (10, "food"), (16, "stone")]
    print(f"3 deterministic tile preference -> {ordered}")
    ok &= ordered == expected

    none = P.decide(Perception(idle_march_slots=0, total_march_slots=8,
                               marches_out=0, available_tiles=TILES))
    print(f"4 nothing idle -> {none}")
    ok &= none == []

    dispatched = []
    logs = []

    class FakeCtx:
        def screencap(self): return "frame"
        def tap(self, x, y, label=""): return None
        def swipe(self, *args, **kwargs): return None
        def log(self, message): logs.append(message)

    run = make_task(
        perceive=lambda img: Perception(idle_march_slots=2, total_march_slots=3,
                                        marches_out=0, available_tiles=[(8, "food"), (12, "ore")]),
        dispatch=lambda ctx, tile: dispatched.append(tile),
        policy=GatherPolicy(reserved_for_rallies=1, preferred_resource_types=("ore", "food")),
        clock=lambda: 1_000_000.0,
        state={},
    )
    result = run(FakeCtx())
    print(f"5 wired task -> dispatched={dispatched}, result={result}, logs={logs}")
    ok &= dispatched == [(12, "ore"), (8, "food")] and result is None and bool(logs)

    message = "[LIVE-CAPTURE] gather perceive/dispatch not wired see kb/23."
    perceive_raised = False
    dispatch_raised = False
    try:
        make_task()(FakeCtx())
    except NotImplementedError as error:
        perceive_raised = str(error) == message
    try:
        make_task(
            perceive=lambda img: Perception(idle_march_slots=1, total_march_slots=2,
                                            marches_out=0, available_tiles=[(10, "ore")])
        )(FakeCtx())
    except NotImplementedError as error:
        dispatch_raised = str(error) == message
    print(f"6a unwired perceive raises exact LIVE-CAPTURE = {perceive_raised}")
    print(f"6b unwired dispatch raises exact LIVE-CAPTURE = {dispatch_raised}")
    ok &= perceive_raised and dispatch_raised

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
