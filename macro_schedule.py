"""Macro activity schedule — the highest-value anti-detection layer (kb/30).

Per kb/30: the real bot-tell is the *distribution over time*, not any single tap.
Superhuman regularity and 24/7 no-sleep uptime are what get an account reported.
So this gates the orchestrator with a plausible human rhythm:

  - one contiguous "sleep" block per day (6-9h), anchored to local night, jittered,
  - micro-breaks (2-8 min) every 20-60 min of activity,
  - => a gross awake window of ~15-18h/day with the bot mostly *idle on timers*.

The day's boundaries are derived from a per-day seed, so they're **stable within a
day** (the bot doesn't flip-flop second to second) but **differ day to day** (no
fixed 02:00-10:00 signature). `clock` is injectable so it unit-tests with no real
time. This only decides active/idle; it never chooses game actions (gem-safe).
"""

import random
import time
from datetime import datetime

HOUR = 3600.0
DEFAULTS = {
    "sleep_len_h": (6.0, 9.0),        # one nightly block => awake window 24-len = 15-18h
    "sleep_anchor_h": (1.0, 4.0),     # local-clock hour the sleep block starts (early morning)
    "micro_break_every_min": (20.0, 60.0),
    "micro_break_len_min": (2.0, 8.0),
    "idle_poll_cap_s": 300.0,         # never sleep the loop longer than this in one go
}
ACTIVE, MICRO_BREAK, SLEEP = "active", "micro_break", "sleep"


class MacroSchedule:
    def __init__(self, cfg=None, clock=time.time, seed_salt=0):
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.clock = clock
        self.seed_salt = seed_salt
        self._day = None
        self._segments = None   # list of (start_epoch, end_epoch, state), contiguous

    # --- per-day determinism ---------------------------------------------
    def _rng(self, day_ordinal):
        return random.Random((day_ordinal * 2654435761 ^ (self.seed_salt & 0xFFFFFFFF)) & 0xFFFFFFFF)

    def _local_midnight(self, now):
        d = datetime.fromtimestamp(now)
        return datetime(d.year, d.month, d.day).timestamp(), d.toordinal()

    def _fill_active(self, segs, t0, t1, r):
        """Alternate active-runs and micro-breaks from t0 to t1 (exclusive end t1)."""
        every = self.cfg["micro_break_every_min"]
        blen = self.cfg["micro_break_len_min"]
        t = t0
        while t < t1 - 1:
            run = min(r.uniform(*every) * 60.0, t1 - t)
            segs.append((t, t + run, ACTIVE))
            t += run
            if t < t1 - 1:
                brk = min(r.uniform(*blen) * 60.0, t1 - t)
                segs.append((t, t + brk, MICRO_BREAK))
                t += brk

    def _build_day(self, now):
        midnight, ordinal = self._local_midnight(now)
        r = self._rng(ordinal)
        sleep_start = midnight + r.uniform(*self.cfg["sleep_anchor_h"]) * HOUR
        sleep_end = sleep_start + r.uniform(*self.cfg["sleep_len_h"]) * HOUR
        next_midnight = midnight + 24 * HOUR
        segs = []
        self._fill_active(segs, midnight, sleep_start, r)          # 00:00 -> sleep
        segs.append((sleep_start, sleep_end, SLEEP))
        self._fill_active(segs, sleep_end, next_midnight, r)       # wake -> next 00:00
        self._day, self._segments = ordinal, segs

    # --- query -----------------------------------------------------------
    def state(self, now=None):
        """Return (state, seconds_until_change) for `now` (defaults to clock())."""
        now = self.clock() if now is None else now
        _, ordinal = self._local_midnight(now)
        if self._day != ordinal or not self._segments:
            self._build_day(now)
        for start, end, st in self._segments:
            if start <= now < end:
                return st, max(0.0, end - now)
        # only reachable at an exact day boundary; rebuild and retry once
        self._build_day(now)
        for start, end, st in self._segments:
            if start <= now < end:
                return st, max(0.0, end - now)
        return ACTIVE, 60.0

    def is_active(self, now=None):
        return self.state(now)[0] == ACTIVE

    def idle_sleep_s(self, now=None):
        """If not active, how long the loop should idle (capped). 0.0 when active."""
        st, remaining = self.state(now)
        if st == ACTIVE:
            return 0.0
        return min(remaining, self.cfg["idle_poll_cap_s"])


if __name__ == "__main__":
    ok = True
    day0 = datetime(2026, 7, 21).timestamp()   # a fixed local midnight

    def at(epoch):
        return MacroSchedule(clock=lambda: epoch)

    # 1) contiguous, gap-free, full-day coverage
    m = at(day0)
    m._build_day(day0)
    segs = m._segments
    covers = abs(segs[0][0] - day0) < 1 and abs(segs[-1][1] - (day0 + 24 * HOUR)) < 1
    contiguous = all(abs(segs[i][1] - segs[i + 1][0]) < 1e-6 for i in range(len(segs) - 1))
    print(f"coverage ok={covers} contiguous={contiguous} segs={len(segs)}")
    ok &= covers and contiguous

    # 2) exactly one sleep block, length in [6,9]h
    sleeps = [(a, b) for a, b, s in segs if s == SLEEP]
    slen_h = (sleeps[0][1] - sleeps[0][0]) / HOUR if sleeps else 0
    print(f"sleep blocks={len(sleeps)} len={slen_h:.2f}h")
    ok &= len(sleeps) == 1 and 6.0 <= slen_h <= 9.0

    # 3) gross awake window (non-sleep) in [15,18]h; active-only (minus breaks) in [14,18]
    awake_h = sum(b - a for a, b, s in segs if s != SLEEP) / HOUR
    active_h = sum(b - a for a, b, s in segs if s == ACTIVE) / HOUR
    print(f"awake={awake_h:.2f}h active={active_h:.2f}h")
    ok &= 15.0 <= awake_h <= 18.01 and 13.5 <= active_h <= 18.0

    # 4) micro-break cadence [20,60]min and length [2,8]min
    runs = [(b - a) / 60.0 for a, b, s in segs if s == ACTIVE]
    brks = [(b - a) / 60.0 for a, b, s in segs if s == MICRO_BREAK]
    # last run of each active fill may be truncated by the boundary -> allow <=20 only there
    long_runs = [r for r in runs if r > 60.5]
    bad_brks = [b for b in brks if not (2.0 <= b <= 8.01)]
    print(f"runs n={len(runs)} max={max(runs):.1f}m  breaks n={len(brks)} range=[{min(brks):.1f},{max(brks):.1f}]m")
    ok &= not long_runs and not bad_brks

    # 5) during the sleep block -> state SLEEP; idle_sleep capped at 300s
    mid_sleep = (sleeps[0][0] + sleeps[0][1]) / 2
    st, rem = m.state(mid_sleep)
    idle = m.idle_sleep_s(mid_sleep)
    print(f"mid-sleep -> state={st} idle_cap={idle}")
    ok &= st == SLEEP and idle == 300.0

    # 6) determinism within a day, variation across days
    a1 = at(day0)._build_day.__self__ or None  # noqa (touch)
    s_day0 = [(a, b) for a, b, s in segs if s == SLEEP][0][0] - day0
    day1 = datetime(2026, 7, 22).timestamp()
    m2 = at(day1); m2._build_day(day1)
    s_day1 = [(a, b) for a, b, s in m2._segments if s == SLEEP][0][0] - day1
    print(f"sleep-start day0={s_day0/HOUR:.2f}h day1={s_day1/HOUR:.2f}h (should differ)")
    ok &= abs(s_day0 - s_day1) > 1.0
    # same now twice -> identical
    st_a = m.state(mid_sleep); st_b = m.state(mid_sleep)
    ok &= st_a == st_b

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
