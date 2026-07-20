"""daily_collect — the red-dot claim loop (kb/28), a differentiator niche.

Claims the free, recurring stuff a human would sweep each day: mail, in-city
resource bubbles, alliance help, the daily wheel, eggs, wall patrol, tax/levy,
bounty quests, tavern/VIP free chests, daily-quest chests. All FREE actions —
no gem path is ever touched (gem-safe by construction; the [LIVE-CAPTURE] claim()
must tap only the free option, never a gem-priced refresh/refill).

Shipped + tested here (pure logic): DailyCollector.due() decides WHICH sources to
claim this tick from a red-dot perception snapshot, honoring per-source cooldowns
(don't re-claim within an interval), priority order, and a per-tick cap (claim a
few and come back — humans don't clear 12 badges in two seconds).

[LIVE-CAPTURE] to wire on a clean session (kb/28 + kb/31):
  perceive(img) -> {source_key: has_red_dot(bool)}   (red-pixel-area per region;
                    pattern from 4x-game-agent screen_analyzer)
  claim(ctx, key) -> bool                              (tap the source's UI path
                    to its claim button; FREE tap only)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# (key, min_interval_s, priority). Higher priority claimed first when several are due.
SOURCES = [
    ("alliance_help", 120, 9),       # help allies — frequent, cheap goodwill/points
    ("city_resources", 600, 8),      # tap the resource bubbles that pop in-city
    ("mail", 300, 7),                # rewards/system mail
    ("tax", 3600, 7),                # sub-city tax / levy
    ("daily_quest_chest", 43200, 7), # daily-quest milestone chests
    ("bounty", 1800, 6),             # bounty/monarch quests
    ("eggs", 3600, 6),               # dragon/familiar eggs
    ("patrol", 3600, 6),             # wall patrol reward
    ("wheel", 86400, 6),             # daily turntable / lucky wheel
    ("free_chest", 14400, 5),        # tavern / VIP free chest (FREE draw only)
]
_PRI = {k: p for k, _, p in SOURCES}
_INTERVAL = {k: i for k, i, _ in SOURCES}


@dataclass
class DailyState:
    """Mutable per-run memory of when each source was last claimed."""
    last_claimed: dict = field(default_factory=dict)   # key -> epoch ts


class DailyCollector:
    def __init__(self, sources=SOURCES, max_per_tick=3):
        self.sources = sources
        self.max_per_tick = max_per_tick

    def due(self, perception, state: DailyState, now: float):
        """Ordered keys to claim now: red-dot present AND cooldown elapsed.
        `perception` maps source_key -> has_red_dot(bool). Cap = max_per_tick."""
        ready = []
        for key, interval, pri in self.sources:
            if not perception.get(key):
                continue                                   # no pending badge
            last = state.last_claimed.get(key)
            if last is not None and (now - last) < interval:
                continue                                   # claimed recently
            ready.append(key)
        ready.sort(key=lambda k: _PRI[k], reverse=True)
        return ready[: self.max_per_tick]


def _not_wired(*_a, **_k):
    raise NotImplementedError("[LIVE-CAPTURE] daily_collect perceive/claim not wired — see kb/28.")


def make_task(perceive=None, claim=None, collector=None, clock=None, notify=None, state=None):
    """Return run(ctx) for the orchestrator. perceive(img)->{key:bool}; claim(ctx,key)->bool.
    Both default to a [LIVE-CAPTURE] stub that raises (never taps blindly)."""
    import time as _t
    collector = collector or DailyCollector()
    clock = clock or _t.time
    perceive = perceive or _not_wired
    claim = claim or _not_wired
    state = state if state is not None else DailyState()

    def run(ctx):
        img = ctx.screencap()
        perception = perceive(img)
        due = collector.due(perception, state, clock())
        if not due:
            return None
        claimed = []
        for key in due:
            if claim(ctx, key):                 # FREE tap only — never a gem refresh
                state.last_claimed[key] = clock()
                claimed.append(key)
        if claimed:
            ctx.log(f"daily_collect: claimed {claimed}")
            if notify:
                notify(f"daily: claimed {', '.join(claimed)}", "info")
        return None

    run.state = state                            # expose for inspection/tests
    return run


if __name__ == "__main__":
    ok = True
    C = DailyCollector(max_per_tick=3)
    NOW = 1_000_000.0
    S = DailyState()

    # 1) red-dot + never claimed -> due
    due = C.due({"mail": True}, S, NOW)
    print(f"1 fresh mail -> {due}")
    ok &= due == ["mail"]

    # 2) no red-dot -> not due (even though never claimed)
    due = C.due({"mail": False, "wheel": False}, S, NOW)
    print(f"2 no badges -> {due}")
    ok &= due == []

    # 3) claimed within cooldown -> not due; after cooldown -> due
    S2 = DailyState(last_claimed={"mail": NOW - 100})   # mail interval 300s
    print(f"3a mail claimed 100s ago -> {C.due({'mail': True}, S2, NOW)}")
    ok &= C.due({"mail": True}, S2, NOW) == []
    print(f"3b mail claimed 400s ago -> {C.due({'mail': True}, S2, NOW + 300)}")
    ok &= C.due({"mail": True}, S2, NOW + 300) == ["mail"]

    # 4) several due -> priority order, capped at max_per_tick=3
    per = {"alliance_help": True, "city_resources": True, "mail": True, "wheel": True, "free_chest": True}
    due = C.due(per, DailyState(), NOW)
    print(f"4 many due -> {due} (expect top-3 by priority: alliance_help, city_resources, mail)")
    ok &= due == ["alliance_help", "city_resources", "mail"]

    # 5) end-to-end make_task: claims due, records timestamps, second tick respects cooldown
    claims = []
    run = make_task(
        perceive=lambda img: {"mail": True, "wheel": True},
        claim=lambda ctx, key: (claims.append(key) or True),
        clock=lambda: NOW,
    )
    class FakeCtx:
        def screencap(self): return "frame"
        def log(self, m): pass
    run(FakeCtx())
    print(f"5a first tick claimed -> {claims}")
    ok &= set(claims) == {"mail", "wheel"} and run.state.last_claimed.get("mail") == NOW
    claims.clear()
    run(FakeCtx())      # same NOW -> both within cooldown -> nothing
    print(f"5b second tick (same time) -> {claims} (expect none)")
    ok &= claims == []

    # 6) unwired task raises [LIVE-CAPTURE]
    raised = False
    try:
        make_task()(FakeCtx())
    except NotImplementedError as e:
        raised = "[LIVE-CAPTURE]" in str(e)
    print(f"6 unwired raises LIVE-CAPTURE = {raised}")
    ok &= raised

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
