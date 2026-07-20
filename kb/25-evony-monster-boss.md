# Evony Solo Monster & Boss Hunting — Bot Reference

Solo attacks + how bosses are found. Rally = kb/24. Cited values have sources; `[VERIFY IN-GAME]`
= from gameplay knowledge, screenshot-confirm before hardcoding.

## Boss ladder (permanent map bosses B1–B23, by Power)
Zombie B1 36.5K · Griffin B10 17.9M · Ifrit B11 59.6M · Kamaitachi B12 89.4M · Fafnir B13 134M ·
Behemoth B14 187.7M · Phoenix B15 262.7M · Typhon B17 551.8M · Garmr B23 4.7B. **Botted sweet
spot = B10–B15** (solo-killable, good drops). Guides publish Power only (no HP) — treat power as
difficulty proxy. **Event bosses** (Ymir/Cerberus/Pan/Hydra/Witch/Warlord/Golem/Viking…) appear only
during events, 3–7 sub-levels; higher reward/stamina.

## Stamina
- **Start/max 100**, restored on daily server reset (VIP + Monarch Talent L18 raise it). Passive
  regen ~1/240s is reported but conflicts with the daily-reset model — `[VERIFY]`.
- **Cost per kill (confirmed):** Zombie B1 15 · Griffin B10 20 · Ifrit B11 30 · Kamaitachi B12 35 ·
  Fafnir/Behemoth/Phoenix B13–15 40 · Garmr B23 50 · Hydra L1/L2/L3/L4 = 20/30/30/45. Rule: bosses
  15–50 scaling with level. B2–B9 & B16–B22 `[VERIFY]` (old "~6 for normal" is dead — B1 is 15).
- **Refills:** daily reset (100 free); **Tavern 25×3/day** (03:30/09:30/12:30 free); **Store 50 =
  200→1,600 gems** (escalating); **Black Market 50 = 300 gems**; events (Crazy Egg/Consuming Return
  = 100 free). → Gem stamina-buy confirmed (this is what easy-bot.club does). Bot can trigger a
  Black-Market refill when stamina < cost (**but our bot is gem-safe — leave gem refills to the
  operator's stamina bot; ours pauses/waits for free refills**).
- Daily caps: Blood of Ares ≤3/day (Lv3+ monsters); Blood Crystals only from ≥200M-power bosses.

## Rewards (specialization)
Every kill: Monarch+General EXP, Prestige, Alliance Pts, a level-tagged Boss Chest + drops.
Speedups: Cerberus/Pan/Ymir/Griffin. Resources: Ymir (most)/Witch/Warlord. Refining stones:
Ymir/Pan/Witch/Golem/Viking. Runestones: Viking/Witch/Hydra L3+/Golem. Gold: Viking/Bayard.
Beast EXP: normal bosses L5+. B10 Griffin ≈ 3,500 Monarch/Gen EXP + Refining Stone + Beast EXP;
scales up to B15 Phoenix ≈ 6,000.

## Generals & troops (solo, zero-wound)
**Doctrine: send only your single highest tier of MOUNTED cavalry, one wave, to one-round-kill** →
zero wounded. Buff mounted attack first, count second. Hunting-general skill books: Mounted Atk vs
Monster L4 (+45%), Mounted Atk L4 (+25%), March Size L4 (+12%). Damage generals: Rostam/Marco Polo/
Tishtrya/Haakon/Hannibal/Martinus/Roland. Double-drop: Theodora +43%/Baibars +41%. **Stamina econ:
Nathanael Greene −25%** (best F2P farmer). Troop counts (T14 cav, buffed): Griffin ~150K, Ifrit
~200K, Kamaitachi ~1M, Behemoth ~1.6M, Phoenix ~2.2M. Rally-join = 1 general + 1 troop.

## UI flow — solo attack (`[VERIFY]` exact coords/labels via a screenshot pass)
1. City → **globe icon** (bottom-left) → World Map.
2. World Map → **Search magnifier** (left edge).
3. Search panel → **Monster tab** (top).
4. Tap monster-type icon + set **level (– / +)**.
5. **Search/Go** → map centers on nearest instance (highlighted).
6. Tap the **monster sprite** → info popup → **Attack** (vs Rally).
7. March/Deploy screen: general slot + troop tiers + **stamina cost shown**; game auto-suggests
   recommended troops. Set general + highest-tier cavalry.
8. **March** → auto-resolves → battle report; stamina deducted, rewards added.
Anchors: magnifier icon, Monster-tab, level stepper (OCR), Go/Attack/March buttons, stamina digits
(OCR top bar + march screen), report dismiss.

## Finding bosses (the scan to implement)
**Primary = Search panel → Monster tab → type+level → Go** (teleports to nearest instance — exact,
no manual scanning). Event/Viking bosses via Event Center `[VERIFY]`. Visual sprite template-match
while panning = fallback only. Map grid ~0–1200, center ~600,600 `[VERIFY server bounds]`.

## World Boss
Random weekly 48h; find via map/Event Center. **5 free attacks/day** then gems; **can't lose, zero
wounded**; rank by single-attack damage; treasure at HP 80/60/40/20/0%.

## Bot dispatch loop (solo farming)
`read stamina (OCR) → if < cost: wait for free refill (Tavern/reset) [gem refill is operator's
stamina bot, not ours] → world map → search → Monster tab → type+level → Go → template-match sprite
→ tap → Attack → set general+cav preset → verify stamina cost (OCR) → March → wait report →
dismiss+log → respect daily caps → jittered sleep.`

## Sources
evonyguidewiki (boss-power-list, how-to-get-stamina, per-boss how-to-kill, boss-drop-item-list,
world-boss, best-boss-monster-general); onechilledgamer (boss/event-monster/general guides);
theriagames (bosses, stamina). Pipeline validated by OSS bots **github.com/Jany-M/TaskEX** (Python
540p templates + OpenCV + Tesseract) and **sonpiaz/4x-game-agent** (pixel-classify + OCR → FSM →
taps). Fandom/EasyBotzy unfetchable. VERIFY: B2–B9/B16–B22 stamina, regen model, exact UI labels,
event-center entry, server coord bounds.
