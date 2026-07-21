"""brain.py — the play-from-screen loop: observe -> decide, recording as it goes.

Composes the vision + decision stack into one cheap tick:
  observe  = state_reader.StateReader.read()  (phash-gated; heavy OCR only on a
             changed screen; each distinct frame recorded to the vision_db brain)
  decide   = strategist.Strategist.decide(state)  -> StrategyDecision
             (deterministic rules; optional Holo+KB escalation for large calls)

ADVISORY ONLY: `decide()` returns (GameState, StrategyDecision); the caller acts.
It never taps and inherits the strategist's hard guarantees — disconnect always
yields priority "stop", and no decision is ever a gem action, even via escalation.
"""

import state_reader as _sr
import strategist as _strat


class Brain:
    def __init__(self, reader, strategist=None, describe_fn=None, kb_lookup=None, logger=None):
        self.reader = reader
        self.strategist = strategist or _strat.Strategist()
        self.describe_fn = describe_fn      # optional Holo describe for large-decision escalation
        self.kb_lookup = kb_lookup          # optional KB lookup for escalation
        self._log = logger or (lambda m: None)
        self.last_state = None
        self.last_decision = None

    def observe(self):
        """One perception tick -> GameState (recorded to vision_db inside the reader)."""
        return self.reader.read()

    def decide(self, state=None):
        """Return (GameState, StrategyDecision). Escalates to the strategic path only
        when the deterministic decision is ambiguous AND an escalator is configured."""
        state = self.observe() if state is None else state
        decision = self.strategist.decide(state, history=self.last_state)
        if decision.escalate and (self.describe_fn is not None or self.kb_lookup is not None):
            try:
                decision = self.strategist.decide_strategic(
                    state, describe_fn=self.describe_fn, kb_lookup=self.kb_lookup,
                    history=self.last_state,
                )
            except Exception as e:                       # escalation is best-effort; never crash the tick
                self._log(f"brain: strategic escalation skipped ({e!r})")
        self._log(f"brain: {decision.mode}/{decision.priority} — {'; '.join(decision.reasons)[:80]}")
        self.last_state, self.last_decision = state, decision
        return state, decision


def from_ctx(ctx, db=None, cfg=None, describe_fn=None, logger=None, **reader_kwargs):
    """Build a Brain from an orchestrator Ctx: a StateReader over ctx.screencap (real
    perception/OCR/vision defaults) + a Strategist. Pass db=VisionDB(...) to record."""
    reader = _sr.StateReader(screencap=ctx.screencap, db=db, **reader_kwargs)
    return Brain(reader, _strat.Strategist(cfg), describe_fn=describe_fn,
                 logger=logger or getattr(ctx, "log", None))


if __name__ == "__main__":
    ok = True
    GS = _sr.GameState

    class FakeReader:
        def __init__(self, states):
            self._states = list(states)
            self.reads = 0
        def read(self):
            self.reads += 1
            return self._states.pop(0) if self._states else self._states_last
        @property
        def _states_last(self):
            return GS(screen="city")

    # 1) disconnect state -> stop (safety), observe() consumed one read
    r = FakeReader([GS(screen="disconnect", disconnect=True, under_attack=True)])
    b = Brain(r)
    st, d = b.decide()
    print(f"1 disconnect -> {d.mode}/{d.priority} reads={r.reads}")
    ok &= d.priority == "stop" and r.reads == 1 and b.last_decision is d

    # 2) under attack -> defend/auto_shield
    r = FakeReader([GS(screen="watchtower", disconnect=False, under_attack=True)])
    st, d = Brain(r).decide()
    print(f"2 under_attack -> {d.mode}/{d.priority}")
    ok &= d.priority == "auto_shield"

    # 3) nothing notable -> training; history threaded (last_state set). food kept
    #    above the default food_low (100k) so the food rule doesn't preempt.
    b = Brain(FakeReader([GS(screen="city", resources={"food": 500_000}, red_dots={}, idle_marches=1)]))
    st, d = b.decide()
    print(f"3 idle -> {d.mode}/{d.priority} last_state_set={b.last_state is not None}")
    ok &= d.priority == "training" and b.last_state is not None

    # 4) explicit state passed -> observe() NOT called (reader untouched)
    r = FakeReader([])
    b = Brain(r)
    st, d = b.decide(state=GS(screen="city", red_dots={"mail": True}, resources={"food": 500_000}))
    print(f"4 explicit state -> {d.priority} reads={r.reads} (expect daily_collect, 0 reads)")
    ok &= d.priority == "daily_collect" and r.reads == 0

    # 5) escalation: ambiguous state + a describe_fn -> decide_strategic path taken,
    #    but safety still holds (a disconnect can never be escalated away).
    calls = {"n": 0}
    b = Brain(FakeReader([GS(screen="unknown")]), describe_fn=lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or "hostile: spend gems finish now"))
    st, d = b.decide()
    print(f"5 escalate -> describe_called={calls['n']>0} priority={d.priority} (must not be a gem action)")
    ok &= calls["n"] > 0 and all(w not in str(d.priority).lower() for w in ("gem", "finish", "instant"))

    # 6) disconnect + describe_fn -> escalation must NOT override stop
    d2 = Brain(FakeReader([GS(screen="disconnect", disconnect=True)]),
               describe_fn=lambda *a, **k: "attack now").decide()[1]
    print(f"6 disconnect+escalator -> {d2.priority} (must stay stop)")
    ok &= d2.priority == "stop"

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
