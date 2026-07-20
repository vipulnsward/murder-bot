# Anti-Detection & Humanization — ADB Evony Bot (responsible, self-owned account)

Defensive/awareness reference for running gently on ONE self-owned account (not scale evasion).
Input/safety params are **confirmed** from primary source (WindMouse writeup, ALAS/pyclick code);
Evony operator-side detection is **community-reported/speculative** (flagged).

## Detection reality for Evony
- **Emulator-hiding is low value** — BlueStacks is an *officially supported* Evony platform; the app
  expects to run there. What leaks is the *automation tooling/behavior*, not the emulator.
- **No documented in-game captcha** (unlike Rise of Kingdoms, which has a verification gate).
  Evony enforcement is **manual/report-driven** (player reports, absurd anomalies, purchase fraud)
  — so "no captcha" ≠ safe 24/7; risk shows up later as a manual ban.
- **The real tells (distributions over time, not single taps):** superhuman/perfectly-regular timing
  (low variance is the tell), **identical repeated tap pixels**, **24/7 no-sleep uptime**, instant
  reactions, farm-cadence marches dispatched the instant a queue frees forever.
- **→ The macro schedule (sleep / active-hours / breaks) matters far more than per-tap jitter.**

## Humanized input (confirmed params)
- **WindMouse** (curved pointer path): G0=9, W0=3, M0=15, D0=12 (gravity toward target + random wind,
  damped within D0). Adapt to ADB by chaining `input swipe` micro-segments (~12px) along the path —
  but plain `input swipe` lifts between segments; **prefer maatouch/minitouch for a true continuous
  gesture** (why ALAS uses them).
- **Tap jitter (ALAS):** never the geometric center — pick a point inside the element box via a
  **3-sample pseudo-normal** (center-biased), shrink ~6px inside the box.
- **Delays: always a `[min,max]` range** drawn pseudo-normally, never a constant. Ranges: tap→tap
  0.3–0.8s; after opening a menu 0.8–2.5s; between tasks 3–15s; **never react to a screen change
  faster than ~0.25s**.
- **Tap duration:** vary 40–120ms normal, ~10% "deliberate" 150–400ms (do a variable-duration tap
  via `input swipe x y x y <ms>`).
- **Swipes:** cubic Bézier with ±10% perpendicular offset, non-uniform waypoints (slow-fast-slow).

## Macro schedule (highest value)
- **14–18 active hours/day** (not 24), start/stop jittered ±30–45 min.
- **Micro-breaks 2–8 min every 20–60 min**; one contiguous **6–9h "sleep" block/24h** anchored to a
  plausible local night, jittered ±60 min. Vary total daily footprint across days.
- Gate high-frequency tasks (gather/march) behind realistic cooldowns so the bot is **mostly idle
  waiting on timers** (ALAS's natural effect), not continuously acting. **Shuffle same-priority tasks.**

## Session hygiene
- **No mechanical hourly relogin** — that's the easy-bot.club failure mode (60-min relogs → disconnect
  spam, a server-visible signature). Stay logged in during a session; relogin only on real need
  (desync/unknown screen/network), or a **wide 3–8h jittered** interval.
- **One controller ↔ one instance ↔ one account** (two touch injectors race → phantom taps).
- **No proxy for a single local account** (proxies are for multi-accounting; add instability + can
  look worse). Don't expose the ADB port beyond what's needed.

## Fail-safe philosophy (ALAS self-policing = the safe pattern)
- **Detect your OWN bot-tells and stop:** rolling click window (15); ≥12 clicks on one button, or two
  buttons alternating ≥6 each → `TooManyClicks` → stop+notify. Stuck timer 60s (180s for long waits)
  → restart app; ≥3 consecutive task failures → human takeover.
- **Unknown screen → pause + notify, NEVER blind-tap** (our `screen_fsm` unknown state already does
  this; wire a Discord/Telegram notify).
- **Never auto-solve captchas/verification** (2captcha) — that's actively adversarial. If Evony ever
  shows a challenge, **pause and notify**. (Our disconnect handling already follows this.)

## `humanize` module for our bot (config + design)
Config: jitter_samples 3, tap_box_shrink 6px; delays as ranges (above); tap 40–120ms / deliberate
150–400ms @10%; windmouse {9,3,15,12}, swipe_segment 12px, curve_offset 0.10; active_hours [14,18],
micro_break every [20,60]min for [2,8]min, long_sleep [6,9]h; relogin [3,8]h; click_window 15,
same_button_max 12, alt_button_max 6, stuck 60/180s, max_consecutive_failures 3,
on_unknown_screen: pause_and_notify.
Module: `norm_int(a,b,n=3)` (avg of N uniforms), `jittered_point(box)`, `windmouse(...)`,
`Humanizer.tap(box)` (jitter+variable-duration via input swipe + record_click repeat-guard),
`.swipe(box_from,box_to)` (windmouse path, chained micro-swipes / maatouch), exceptions
TooManyClicks/GameStuck/UnknownScreen/RequestHumanTakeover; `daily_loop` (active session → micro-
breaks → long sleep). Full sketch in the research transcript.
→ Integrates with our orchestrator: wrap `ctx.tap/swipe` with the Humanizer; scheduler already
shuffles by next_run; add the notify + pause-on-unknown to the FSM unknown/disconnect paths.

Sources: ben.land WindMouse; ALAS (utils.py jitter/delays, minitouch/maatouch Bézier, device.py
stuck/too-many-clicks, alas.py + exception.py human-takeover); pyclick humancurve. Evony
operator-side detail community-reported (WebSearch unavailable this session).
