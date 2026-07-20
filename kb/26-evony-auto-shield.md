# Evony Auto-Shield / Defense — Bot Reference

Reactive "bubble on incoming attack" (ESB-TKR's flagship) + proactive shield renewal. **Bot is
gem-safe: shield uses inventory items by default; gem-buy is strictly opt-in.** `[VERIFY IN-GAME]`
= confirm on the real client (Watchtower guides were network-blocked this session).

## Key finding
**No OSS Evony bot does reactive bubble-on-incoming.** But **`Jany-M/TaskEX`** (github) has a full
**proactive** auto-bubble on our exact stack (Python 3.12 + ADB + BlueStacks + OpenCV + Tesseract,
540×960) — reusable apply-shield code/coords. The **reactive trigger (Watchtower ETA → bubble just
before impact)** is the half to build new. `TungNC-echoes/auto-evony-v1` = offensive only, no defense.

## Shield item — "Truce Agreement", 4 durations
Use-Item list order: **8h / 24h / 3 Days / 7 Days** (7d needs one scroll). Live in Items inventory,
surfaced via **City Buff → Truce Agreement**. Each row's right side shows **"Use"** (own it) or a
**gem price** (out of stock, purchase-only). Longer/event bubbles (14d/Advanced) exist `[VERIFY]`.

## Incoming-attack detection `[VERIFY IN-GAME regions]`
- **Cheap pre-filter:** red screen-edge flash + alarm + a **red incoming-march banner/counter** on HUD.
- **Primary intel = Watchtower** → tap it (or the alert) → **incoming-march list**: per-march
  **ETA countdown** (the value to OCR), attacker name/alliance, troop count/types, general,
  attack-vs-scout. Higher Watchtower level reveals more. **Lead time = enemy march travel time**
  (~seconds adjacent → several minutes) — that window is what reactive shielding races.

## Apply-shield UI flow (from TaskEX, 540×960 — recalibrate coords)
1. Be on Alliance City / World Map; close any popup (top-right red X); guard the Android-back
   "exit game?" with Cancel.
2. Tap the **leftmost status circle under the portrait, top-left HUD** — **(40,105)** (fallback 40,115).
3. OCR title = **"City Buff"** (first card "Truce Agreement"); NOT "Use Item" → else retreat.
4. (Read current shield: OCR the green timer bar in the Truce card.)
5. Tap the **Truce Agreement row** → **Use Item** bubble list.
6. Pick duration by **fixed row order** (1=8h…4=7d, 7d scroll) — template match thr 0.85.
7. Right-side action: **"Use"** → tap (consume inventory). **Gem price → only tap if
   `allow_gem_purchase` explicitly on** (gem-safe default = never).
8. **Confirm** (green): 1 dialog if no active bubble, 2 if replacing one.
9. **Verify:** OCR the top countdown ≈ chosen duration (e.g. ~23:58 for 24h) = success proof.
10. Retreat (top-left back 40,105 / 35,30); Cancel any exit prompt.

## Timing logic (implement both)
- **Reactive (build new):** read smallest incoming ETA `t`; fire the apply flow when
  `t ≤ apply_latency + safety_margin` (apply_latency = measured screen-walk cost, ~8–15s on
  BlueStacks; margin ~5–10s). **Land the shield JUST before impact** (max window + avoids waste if
  attacker recalls). **Re-bubble/abort on recall:** if the ETA vanishes before you fire, conserve
  the shield. Default to the **shortest bubble (8h)** so spammed incomings don't burn 7-day shields.
- **Proactive renewal (TaskEX):** config `trigger_minutes` (default 60), `prioritize_existing`
  (inventory before gems), `allow_gem_purchase` (default **False**). Read remaining timer; if
  `> trigger`, **sleep until `expires_at − trigger − 60s`** (don't busy-poll); renew at threshold.
  Reconfirm any `≤threshold` or large upward OCR jump before acting (one bad frame ≠ wasted shield).

## Fallbacks (survival tree): shield → recall+ghost → recall+teleport
- **Recall:** tap arrows next to active marches → troops home instantly.
- **Ghost** (when you can't bubble): send **ALL** troops on **60-min rallies** → empty keep →
  attacker hits only traps/wall, **kills no troops**. Bubble for normal play; ghost for **SvS/
  Battlefields where "you cannot be bubbled."**
- **Teleport interaction (critical): you CANNOT teleport while ghosted** — recall first, then
  Advanced Teleporter to relocate out of range.
- Pre-attack: remove Duty Generals from at-risk buildings; unlink subordinate cities.
- **Verify-or-fallback:** if step-9 activation can't be confirmed and impact is imminent →
  immediately recall+ghost (a failed shield must NOT silently pass).

## Complementary survival
**Hospital capacity = survival cap** (over-capacity casualties die instead of wounded → healable);
upgrade Hospital + Medical research. **Box resources** into inventory items (unlootable) + stay under
warehouse-protected thresholds. Wall/traps add a layer.

## `auto_shield` task (gem-safe)
`poll: HUD alert (cheap) → if incoming or reactive mode: Watchtower list → OCR soonest ETA. Decide:
(1) incoming & unshielded → if ETA ≤ apply_latency+margin: apply_shield (item; verify) else
schedule recheck & watch for recall; if bubble unavailable (SvS/blocked) → recall+ghost. (1b) ETA
vanished → conserve shield. (2) proactive: shield_left ≤ trigger → renew; else sleep to
expires−trigger−60. Short poll (3–5s) when reactive-armed, long when proactive-only.`
**Gem-safety:** `allow_gem_purchase=False` default → inventory only; empty + not allowed → recall+
ghost, log it. Opt-in override adds a max-gems/day cap so a spammed attack can't drain gems.

## Reusable (github.com/Jany-M/TaskEX, master — same stack)
`features/logic/auto_bubble.py` (timer state machine + OCR parse + smart scheduling);
`utils/navigate_utils.py` (open/navigate bubble panel, confirm dialogs, verify remaining, back-guard,
HUD coords 40,105); `db/models/bubble.py` (4 types 8/24/72/168h); `assets/540p/bubbles/README.md`
(flow + gem opt-in rule); `get_auto_bubble_controls` (config schema).

VERIFY: Watchtower intel per level + exact ETA text/regions; realistic min lead time (feasibility of
reactive vs recall-only); gem prices; KE/event bubble hard-blocks; 14-day/Advanced Truce.
Sources: github Jany-M/TaskEX + TungNC-echoes/auto-evony-v1; evonytkrguide ghosting; onechilledgamer
pvp/troop; theriagames watchtower (costs only). Fandom/evonyguidewiki/reddit unreachable this session.
