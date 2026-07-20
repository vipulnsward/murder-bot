# Food Acquisition & Tier Economics — funding 500M→1B

Researched answer to the constraint in `kb/13`: 1B needs ~108–110B food and we're ~80B short.
Where does that food come from, and is T2-to-1B even the right play? Sources are inline.

## Confirmed per-troop cost (ground)

| Tier | Food | Stone | vs T2 |
|------|-----:|------:|-------|
| T1 (Warrior) | **160** | **0** | −27% food, **no stone** |
| T2 (Conscript) | **220** | **40** | current build |
| T3 | **320** | **80** | +45% food, +100% stone |

271,766 × 220 = 59.79M food and × 40 = 10.87M stone per T2 batch — matches the measured
figures exactly. 500M→1B (+498.5M troops) = **~109.7B food + ~19.9B stone**.
Sources: onechilledgamer.com/evony-troop-guide, bluestacks EKR army guide.

## Big correction: Safe Food is spendable (kb/13 assumption resolved)

"Safe resources" are the **same resource as normal food**, merely protected from **plunder,
troop upkeep, and transport** — otherwise fully usable to train troops/build/etc. Opening a
**1M Safe Food** box adds 1M spendable food. Our in-game count is `1M Safe Food · Use(19,364)`
= **19,364 boxes ≈ 19.4B food** (boxes, confirmed from the resource screen, not units).

So **usable food today ≈ 9.4B (1M Food) + 19.4B (Safe Food) ≈ 28.4B** → ~475 batches →
**+129M troops → ~629M reachable right now**, not the 544M in kb/13. Safe Food is in fact
*better* than normal food (upkeep can never touch it). The bot only needs to also open the
"1M Safe Food" row when the "1M Food" row is exhausted.
Source: theriagames.com/guide/evony-safe-resources, topgamesinc launch announcement.

## Troops never starve; training is a one-time cost

- A food deficit **does not destroy troops** — "troops will never starve." Upkeep only
  subtracts from *net production* (siege units have **no upkeep**). So you can't *stockpile*
  city food at 500M–1B troops, but already-trained troops are safe and cost nothing further.
- **Resource items in inventory are upkeep-immune** until opened. Correct workflow (what the
  bot already does): hold food as 1M/1M-Safe items, open just-in-time per batch.
- **No mechanic reduces the per-troop food cost.** Research / generals / sub-cities cut
  training *time*, not resource cost. Treat 220 food/T2 (160/T1) as fixed.
Sources: evony.fandom.com/wiki/Food, onechilledgamer troop guide, evony Warehouse wiki.

## Sourcing the ~80B gap (ranked by yield/effort)

1. **World-map food gathering — the main free, automatable lever.** Optimized accounts pull
   **~300–400M resources/day** across all marches; dedicated to food, plan **~200–350M
   food/day**. Best tiles: **L14 farm** (~7M base, up to ~18M/haul with load+general bonuses).
   Stack multipliers: Queen Jindeok (+40% world tiles), Shimazu (+30% farms/+10% speed),
   Korea gold sub-cities (+15% each), gathering research, 24h city gathering buff (+50%
   speed), Monarch Lv26 talent (+20%). Siege carries the most load and has no upkeep — ideal
   gatherers. **At ~300–500M food/day the 80B gap ≈ 5–9 months.**
   Sources: evonytkrguide gathering guide, onechilledgamer gathering guide, evonybuilds.
2. **Paid resource packs / Consumption-Return rebate events** — the only way to get tens of
   billions in days, but costs money. Consumption-Return refunds a share of resources spent,
   so time big training pushes to those windows. Source: bluestacks resource-farming guide.
3. **Surprise Safe Resource Boxes / Ymir chests** — steady free trickle, ~2.8B safe
   resources/month random type (~0.7B food/mo). Source: theriagames safe-resources.
4. **Farm production — effectively neutralized** at 500M–1B troops (upkeep ≥ output; net → 0).
   Do not rely on production for bulk. Source: evony.fandom.com/wiki/Food.
5. **Monarch/alliance gifts, daily/login, boss drops** — modest (tens of M/day), auto-claimable.

## Should it even be T2? (tier reconsideration)

- For a **count / wall / power-number** goal (what "1B ground" implies), **T1 is strictly
  better**: 160 food (−27%) and **0 stone**. Retargeting the remaining ~371M (from ~629M) to
  T1 cuts the outstanding bill to ~59B food and **removes the entire ~15–20B stone blocker**.
  The standard meta meat-shield at 500M–1B is T1 anyway.
- **T3 is the worst** choice for the goal (more food, double stone, marginal power).
- For **actual combat power**, low-tier ground (T1/T2/T3) is filler/absorption, not damage —
  real strength is high tier (T12–T14). So pushing *any* low tier to 1B is a count play, not
  a strength play. Sources: evonytkrguide troop-layers, onechilledgamer troop guide.

## Automation-friendly food loop (for a future bot extension)

ETKR has no native auto-gather, but the loop is scriptable and is the most scalable free
source: keep **5 marches on L14 food tiles** at all times (dispatch → auto-return → redispatch),
build enough siege to fill them, auto-open the free trickle (Safe Boxes, Ymir, gifts, dailies),
and open food items just-in-time. Assign a duty officer to the **Warehouse** to protect any
in-city food from upkeep. This turns the trainer into a self-feeding gatherer+trainer.
Sources: evonytkrguide gathering guide, evony Warehouse wiki.

## Bottom line

- **Free upside now:** wire the bot to also spend **Safe Food** → ceiling jumps 544M → **~629M**
  with zero new resources.
- **1B is realistic only as a months-long automated gathering grind** (~5–9 months at
  300–500M food/day), or compressed to weeks by **buying resource packs** (money). Farms won't
  fund it.
- **Cheaper path to a big count:** switch the remainder to **T1** (−27% food, no stone) — also
  clears the secondary ~20B stone constraint that T2/T3 impose.
