# Evony Base Development Automation — Bot Reference (OUR unique niche)

Building upgrades, Academy research, duty officers, queues + speedups, alliance help. **No public
Evony bot does this** (easy-bot.club/ESB-TKR = farming/rally only) — this is our differentiator.
**Gem-safe: never spend gems** — every accelerator is item-based or free. `[VERIFY IN-GAME]` /
`[CAPTURE TEMPLATE]` = confirm on the real client before hardcoding.

## Construction queues (builders)
- **Builder 1** free (default). **Builder 2 = permanent, via Academy research node "Builder"**
  (5,000 gold / ~5 min / Academy Lv1) → **research this FIRST**, huge ROI.
- **3rd builder = rent for 300 gems/3 days → bot NEVER buys it.** Gem-safe max = **2 builders**.
- Golden rule: **never let a builder idle** — track 2 timers, refill whichever is free.

## Upgrade flow + state detection
Flow: tap building → radial menu → **Upgrade** (up-arrow/hammer) → detail dialog (level/cost/time)
→ confirm. If short on resources or both builders busy → game offers **gem fill / rent** → **bot
detects & cancels** (treat as fail, move on). Then request **Alliance Help** (hand icon) + optional
item speedup.
**Detect upgradeable:** floating **green up-arrow badge** above the building `[CAPTURE TEMPLATE]` →
`template_match.find_all("green_up_arrow", thr≈0.8)` returns ALL upgradeable buildings in one pass.
Busy = countdown timer/animation (OCR HH:MM:SS). Maxed/capped = no arrow + no timer; the Upgrade
dialog's greyed confirm / "Keep level not high enough" = capped by Keep → deprioritize.
Caution: **Hospital/Shrine/Wall disable healing/revive/repair while upgrading** — don't mid-war.

## Academy research flow
tap Academy → **Research** (disabled while Academy itself upgrading — check first) → pick tree tab
→ node → **Research** confirm (resources/stones, never gems) → alliance help + research speedup.
Node states: available (enabled) / locked (grey+padlock, "Requires…") / in-progress (single
research queue, timer) / maxed ("X/X"). Rule: never let the Academy idle.
**Research priority: Construction → Adv → Super Construction → Typography → Super Typography**
(cut ALL build/research times → snowball), then economy/gathering, then Military/Defense.

## Duty officers (assign BEFORE the task — key mechanic)
A duty general buffs the task (~+20% construction on Keep, ~+20% research on Academy, training on
troop bldgs). **The buff locks into the started task — you can REMOVE the general right after
starting.** So one strong general is **hot-swapped**: Keep→start build→move to Academy→start
research→move to Barracks→start training. Flow: building menu → **Duty** button (visible once slot
unlocked) → pick general → Appoint → start task → (dismiss to reuse). Slots unlock: Keep Lv16,
Academy Lv20 (Military Academy Lv1), Barracks Lv25, Archer Lv21, Workshop Lv29, Stables Lv33.

## Speedups (item-based, gem-safe)
5 categories: Construction / Research / Training / Healing / General. Use type-specific first, save
General for emergencies. Apply: tap active timer → **Speed Up** → select **item rows** → Use.
**Gem-safe guard: only tap item rows; NEVER the bottom gem "instant finish."** Gates: don't speedup
<5min timers; **Alliance Help (free) always before speedups**; save big speedups for Keep/Academy
milestones + Construction/Research events (double value).

## Alliance Help (free time)
Request: tap the **hand icon above** a building/Academy with a running timer (one help/member/task).
Give: tap the **Embassy hand** = help everyone in one tap. ~10–15 min/help early; Embassy Lv32+ →
up to 50+ helps/task. Eligible: construction, research, healing, gear crafting. **Bot: request help
right after starting any task; tap Embassy hand periodically — free time before any speedup.**

## Priority (gem-safe F2P)
1. Research "Builder" (2nd builder) first. 2. Keep (master gate) on Builder 1. 3. Academy + its
research non-stop on Builder 2. 4. Construction/Typography research nodes first. 5. Troop buildings
(Barracks/Archer/Stables/Workshop/Rally Spot) to Keep-required levels. 6. Embassy (raises help
count!)/Hospital/Warehouse/Wall. 7. Resource buildings only to Keep minimum.

## Auto-develop task design (adapt 4x-game-agent, MIT — the blueprint)
5 layers: Perception (adb screenshot + cv2 template_match green-arrow/buttons + PaddleOCR
levels/timers/costs) → State FSM (classify screen + dismiss popups) → **World model** (per-building
{level,upgrading,timer_end} + cached_positions → predict next-free → proactive wake, don't
busy-poll) → Workflows (upgrade/research/duty/speedup/alliance_help — each: ensure screen → tap seq
→ VERIFY re-screenshot → update model) → Strategy (priority table + phase goals).
Two loops: `keep_builders_busy()` (idle builder → find_all(arrow) → rank → afford-check no-gems →
Keep duty officer → Upgrade → cancel any gem prompt → alliance help → optional item speedup) and
`keep_academy_busy()` (research idle → priority node → Academy duty → Research → help).
**Gem-safe invariants (hard guards):** never tap gem instant-finish / buy-resources / rent-builder;
only item rows in speedup panel; a gem-costing confirm = fail+skip; alliance help before speedups.
**Verify discipline:** after every action re-screenshot + classify; mark success only when expected
next state observed; record failures for retry — never assume a tap worked.

## Reusable OSS (the blueprint)
**sonpiaz/4x-game-agent (MIT)** — Python+ADB+OpenCV+PaddleOCR+FSM+world-model; its Kingshot code
DOES build/research/train (`template_match.py` find_all, `building_finder.py` tap→OCR-name→cache,
`workflow_engine.py` verify-after-act, `world_model.py`, `strategy.py`) — near-drop-in to adapt for
Evony (listed "planned"). Other Evony bots (auto-evony-v1, williamdai8, GargIT) do NOT do base dev.

Sources: evonyguidewiki (academy/construction/duty-officer); gamesguideinfo (Builder research);
empirebuildacademy (research/beginner); evonytkrguide (alliance help); BlueStacks (speedups);
github sonpiaz/4x-game-agent. VERIFY: green-arrow art, speedup denominations, per-general duty %,
duty-slot levels, Keep-cap behavior.
