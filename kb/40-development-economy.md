# Development & Economy — Strategy Synthesis for base_dev / daily / gather (kb/40)

The decision layer that turns the evonyguidewiki.com city-development + events + economy pages into
policy for `base_dev.BaseDevPolicy`, `daily_collect.DailyCollector`, `gather.py`, and the
strategist's **expand** mode. Primary companion: **`data/guides/economy.jsonl` — 75 distilled records**
(one per page, schema `{title, url, category:"economy", summary, content}`) covering the 40
city-development buildings, 15 events, and ~20 item/resource/economy how-to pages. Also companion to
the generals catalog (kb/36 + `data/generals.jsonl`).

## Verification legend
- **Source of every fact here = evonyguidewiki.com English pages, captured LOCALLY** under
  `data/pages/*.md`; the per-page URL is in each `economy.jsonl` record's `url`. The synthesis was
  written from those local captures (no live fetch). The strategy layer additionally draws on
  adjacent local pages outside the 75-record set (troop-upgrade, troop-initial-stats,
  vip-benefits-list, march-size-per-level, how-to-get-more-march-slot, make-wounded-as-you-need,
  what-is-adv-dispatch, server-time-chart, server-merge, how-to-get-skillbook, how-to-get-runestone,
  pasture, dead-keep-power-list) — all present in `data/pages/`.
- **Numbers drift with game patches** (the wiki is itself patched; e.g. Keep/VIP tables edited
  2025-2026). Treat every level/%/threshold as `[VERIFY]` before hardcoding — same discipline as
  kb/27/kb/36. `[VERIFY]` also flags any single-page claim or a value the page itself hedged.
- **Gem-safe invariant carries over from kb/27**: none of the spend advice below ever taps gems for
  instant-finish, buy-resources, rent-builder, buy-tax, or gacha opens. Where a source's headline
  path is paid (King's Party/Royal Party, Ekaterina's Garden, event packs, tavern gem-refresh), it
  is flagged NOT-ACTIONABLE and kept only so the strategist knows to skip it.
- A couple of mechanics carried from an earlier network pass rely on pages NOT in the local set
  (troop rock-paper-scissors from `troop-type-en`; the Academy+Rally-Spot beginner order from
  `construction-en`); these are tagged `[VERIFY — not in local set]`.
- Cross-refs: **kb/27** base-dev automation · **kb/28** daily-collect + alliance loops · **kb/13**
  1B resource ceiling · **kb/14** food/tier economics · **kb/15** buff maximization · **kb/16** keep
  growth · **kb/23** gathering · **kb/24-25** rallies/monsters.

## Companion file
- **`data/guides/economy.jsonl` = 75 records**: 40 city-development buildings + 15 events + 20
  economy/item how-to pages (the exact city-development + events + economy scope). Full URLs inside.
- This doc is the strategy overlay; the jsonl is the fact store. The pages-read/skip ledger is at end.

---

## 1. Build/upgrade priority — feeds `base_dev.BaseDevPolicy.decide()`
Refines kb/27's priority table with the wiki's own guidance (`construction-en`, `academy-en`,
`upgrade-requirements-keep-en`, `embassy-en`, `military-academy-en`, `rally-spot-en`).
- **Beginner priority after every Keep-up: Academy + Rally Spot FIRST** (`construction-en` `[VERIFY —
  not in local set]`). Academy
  research drives nearly all buffs; Rally Spot sets base March Size → faster gather + stronger rallies.
- **Keep is the master gate** — almost every building's upgrade needs a min Keep level, and the Keep
  itself needs Walls + other facilities raised first. Max Lv50. So `base_dev` should treat a
  greyed/"Keep level not high enough" confirm as *capped → deprioritize* (already in kb/27).
- **Speed construction (all free/gem-safe):** Academy research `Construction → Adv → Super
  Construction` (+ `Typography → Super Typography` to speed the research itself); **Keep Duty Officer
  before starting a build (+20% base, hot-swappable per kb/27)**; **Strength Crown** monarch gear
  equipped before starting; **Alliance Science** (passive from being in an alliance); sub-city Culture
  = Europe adds a construction buff.
- **Two gem-safe builder sources (aim for 3 queues):** (a) Academy "Builder" research node =
  permanent 2nd builder (kb/27); (b) **VIP17 grants a FREE BUILDER +1** while VIP17+ is active
  (`vip-benefits-list-en`). Still never rent the gem builder.
- **Embassy is high-ROI for the help loop** (`embassy-en`): raising it increases the *number of
  construction-helps received* and *shortens help time* (free time before any speedup — kb/27). Keep-9
  gated, needs Market raised first, gates War Hall. Duty slot at Embassy **Lv27**.
- **Duty-officer slot unlock levels** (assign-before-task, then hot-swap — kb/27): Hospital 15, Keep
  16, Bunker/Academy 20, Archer Camp 21, Warehouse 23, Market 24, Barracks 25, Embassy 27, Workshop
  29, Research Factory 32, Stables 33, **Rally Spot 35**, Military Academy (from its Lv1). Military
  Academy's duty uniquely boosts **both** Military Academy and main-Academy research → set both.
- **Function disabled while THAT building upgrades — never mid-war** (`construction-en`): Hospital
  (no heal), Shrine (no general revive), Walls (no fire/repair), Academy + Military Academy (no
  research), Forge (no craft), Barracks/Archer Camp/Stables/Workshop (no training), Research Factory
  (no research stones), Bunker (no garrison). base_dev must not queue these during active war/heal.
- **Consuming Return Event becomes important at Keep 25+** — big upgrades then refund RSS + speedups
  (see §4). Time major Keep/Academy jumps to coincide.

## 2. Academy research priority (idle-Academy loop, kb/27)
`academy-en`: research disabled while Academy itself upgrades (check first). Milestones: Lv20 Duty,
Lv28 Military Advance, Lv33 Defense Advance, Lv41 Offensive/Defensive Mastery. Order (unchanged from
kb/27): **Construction/Adv/Super Construction → Typography/Super Typography** (snowball build+research
time) → **Coordination** (march size, §5) + gathering/economy (Advancement, up to +180% gather speed)
→ Military/Defense. **Military Academy** (Keep 36, hard-gates Keep 37) uses **Tactic Scroll + Gold**
(not Research Stone) for battle buffs; max Lv15, cost spikes at Lv5 then eases.

## 3. Troop tier economics — feeds gather/train + strategist expand
`troop-type-en`, `troop-upgrade-en`, `troop-initial-stats-en`, `arsenal-en`:
- **4 types, rock-paper-scissors** `[VERIFY — from troop-type-en, not in local set]` (equal tier/buff): Mounted > Ground > Ranged > Mounted; **Siege
  beats Ranged but loses to Mounted/Ground**, and is extremely strong (10-23x kill rate) vs any
  *lower-tier* troop. Mounted = best for PvE monster hunting (kb/24-25). **Siege + Ground carry the
  highest Load → the gathering troop types**; Ranged/Siege are long-range.
- **Max tier T17** (added 2025-10). **Arsenal (Keep 27) only converts existing troops T10→T14, one
  tier at a time; T15-17 must be trained fresh.** Troops below T9 can't be upgraded at all.
- **Build-new is cheaper than build-then-upgrade** — don't mass-train sub-T9. Start serious training
  at **T10 (Keep 25)**, ideally **T12 (Keep 30)**. Food upkeep scales ~80x T1→T17 while power ~155x
  → higher tiers are *more food-efficient per unit power* but cost far more food absolutely (fund via
  kb/14). `[VERIFY IN-GAME]` the T15-17 numbers.
- Upgrading troops does **not** count as "Troop Training" for event/activity score (except on a
  Power-Increase event day) — relevant when timing training-scored quests (§7).

## 4. Gem-safe speedup supply — what `base_dev` spends (`how-to-get-speed-up-items-en`)
Ranked free sources; save big ones for Keep/Academy milestones on double-value event days (kb/27):
- **Kill bosses (main daily source):** every boss drops speedups 100%; **Cerberus & Pan are by far
  the best** (Legendary Cerberus Lv4 chest ≈ 248h across Construction/Training/Healing/Research/Trap/
  Craft; Pan Lv5 ≈ 205h), then Ymir, then Griffin/Witch3/Warlord3/Hydra3/Phoenix. Higher boss level =
  more hours; best farmed via a high-rank alliance's active rallies (kb/24). Nathanael Greene general
  cuts stamina cost (kb/36) → more kills/day.
- **Consuming Return Event (biggest cumulative, gem-free via resources you'd build with anyway):**
  completing **2.5B RSS of all 4 types ≈ 640 days** of speedups, **10B ≈ 3,100 days, 35B ≈ 9,500
  days**. Approx Keep to complete-4-types: 125M≈K25, 500M≈K27, 1.25B≈K29, 2.5B≈K31, 5B≈K33, 10B≈K35.
  (The *gem*-consumption branch of the same event is NOT gem-safe — ignore it.)
- **Battle of Constantinople (SvS):** 50-220h speedup chests by personal score (≥50h even on a loss;
  1,200+ score → ~220h) — top-alliance content.
- **Random bonus chests:** Royal Chest (kill 3 Royal Thief) → 8h/24h/3-day/7-day; Viking Rescue Chest
  → healing speedups.

## 5. March size & speed — feeds expand/gather throughput
`how-to-increase-march-size-en`, `march-size-per-level-en`, `rally-spot-en`, `how-to-get-more-march-slot-en`:
- **March size = Rally Spot base (Lv1 ~800 → Lv45 ~860,000) × %/flat buffs.** Free levers: Academy
  **Coordination/Adv/Super/Supreme Coordination** (up to +100,000 flat & +100%); **Rank via prestige**
  (Knight +5,000 … Regent +100,000); **VIP** (+4,000 at VIP4 → +160,000 by VIP25, needs active VIP
  Time); march-size skillbook (+3-12%); innate-skill generals (King Arthur/Genghis Khan +15%); Rally
  Spot Duty Officer (Lv35, up to +30%/+70,000); Ideal Land ornaments; Imperial Seal civ treasure.
- **March slots:** base + **VIP5 grants +1 slot**; preset march slots at VIP5/10/13/15/18/20. More
  slots = more parallel gathers/rallies (raise the strategist's idle-march budget).
- Practical: keep **Rally Spot near Keep level** and push Coordination research — the single biggest
  free gather-throughput lever for expand mode.

## 6. Resource management — feeds gather + daily
`how-to-get-resource-en`, `warehouse-en`, `how-to-get-gold-efficiently-en`:
- **Resource item drops (`how-to-get-resource-en`):** ranked by quantity **Azazel 5M > Kraken 4M >
  Stymphalian Bird 3M > Ymir6 2.9M > Ammit 2.5M > Witch6/Warlord6 2.1M** (×4 RSS types); by
  stamina-efficiency **Azazel 400K/stam > Kraken 320K > Ymir6 290K** — so **Azazel is best on both**.
  **Cerberus drops 0 resources** (it's a speedup boss — pick the boss by what you need). Consuming
  Return also refunds RSS.
- **Keep RSS in unopened Resource Boxes** — boxed resources can't be plundered; only open them right
  before spending. **Don't buy RSS from the store; use Black Market only in emergencies.**
- **Troop Load is irrelevant to tile-gather yield** (common newbie mistake) — it only matters for
  *plunder* volume. Don't optimize Load for gathering.
- **Warehouse** protects a floor of resources from plunder (raise it as a safety buffer). **VIP All-
  Resources Production** scales +1%(VIP2)→+10%(VIP10)→+70%(VIP28); Keep level also raises in-city
  production + gather speed.

## 7. Gather doctrine — feeds `gather.py` (`how-to-get-resource-en` §B, kb/23)
Two independent buff families — apply both:
- **Yield ("Extra Resources"):** gatherer general (e.g. Queen Jindeok +40%); **Korean subordinate
  cities** (up to +135% with 9 epics); Culture=Korea + in-city sub-city quality (+15%); Monarch
  Talent Lv26 "Gathering Boost" (+20%); **Champion's Set(4) +10%**; Art Treasure +10%; Alliance
  research category.
- **Speed:** maximize the general's **Politics** stat; skillbook (+45%); **Advancement research
  (up to +180%)**; **Crystal monarch gear (+50%)**; King's Equipment; **gathering speedup items
  (+50%)**; alliance-hive buff (+25%); **gather high-level tiles (Lv12+, ~200K/h)**.
- **Equip-swap-on-arrival trick:** buffs lock in when the march *arrives* at the tile → send with
  King's Equipment / Crystal gear (speed) equipped, then swap to Champion's Set(4) (yield) after
  arrival to bank both. A gather workflow can automate this swap.

## 8. Events → time bot actions — feeds strategist expand-mode + daily
Many recurring events reward the exact actions the bot already does. Score them for free by *timing*
build/gather/kill/heal into their windows. Four buckets:

**A. Action-scoring — synchronize normal activity (highest value):**
- **Consuming Return Event (`consuming_return_event-en`) — the single most important economy event.**
  It *rebates* a share of resources/speedups/items you spend. The winning cycle: **hoard resources
  2+ weeks → START big construction during a RESOURCE-return window (burn resources → get days of
  speedups) → COMPLETE builds during a SPEED-UP-return window (burn speedups → get resources).** This
  is how F2P reaches Keep 35+. Tiers (complete all 4 RSS types): 2.5B ≈ 640 days speedups, 10B ≈
  3,100, 35B ≈ 9,500; Keep to afford: 125M≈K25, 500M≈K27, 1.25B≈K29, 2.5B≈K31, 5B≈K33, 10B≈K35. **Do
  not pre-build troops/traps before it.** Also rebates Tactic Scroll, Refining Stone, Blood of Ares
  (returns generals), dragon-feed and Lv7-material spends. Two rotations run at once (11d/3d cadence).
- **Alliance Competition (~10 days, `alliance-competition-en`):** personal score → alliance rank
  (MAX 2,600 Novice → 5,200 Epic). High-value quests that match bot actions (50-240 pts): Increase
  building power (City Development 300K=+240), Increase research power (450K=+240), Cultivate Generals
  (500×), Consume Runestones (1.5K), **Increase Power** (heal wounded — see make-wounded), **Gather
  RSS outside city** (54M one-type=+240), **Kill Bosses / Lv14+ Boss** (via alliance rallies), Consume
  Stamina, **Offer at Shrine**, Wheel spins, Consume Gems (500K=+240, skip — paid). Challenge slots
  are capped/non-refundable → **only start quests worth ≥140 (≥170 at Elite+); R4/R5 prune low ones.**
- **Dawn of Civilization (~10 days, ~2×/month, `dawn-of-civilization-en`):** cheapest route to the
  PvP **march effect + a golden historic general** (Aethelflaed, Narses, Merlin…). 40 quests across
  Gathering/Alliance/Ambition; f2p daily paces — gather, produce, cultivate 23×, refine 23×,
  shrine-offer 10×, rally 16×, donate 5×, speed-up-ally 10×, consume 240 stamina, train mass T1, heal
  80k, revive 80k souls (**Holy Palace Lv25+**), recall deserters, +70M power, plunder 18M. **No
  per-day theme split** — pace daily. Top-100 rankers also get Senior March Size Increase items.
- **Revelation of Horus (`revelation-of-horus-en`) — daily quest RACE scored by SPEED.** Each day's
  quest title is pre-revealed and completable during the hidden stage. Ranking = who completes soonest
  after start (~1h after server reset per DST). Quests are normal actions: Cultivate Generals, Refine
  Equipment, Increase troop power, Tax, Levy Gold, Offer at Shrine, Help Allies. **Winning play:
  pre-stage tributes/gold/generals and fire instantly at reset.** Coins don't expire; redeem for rare
  generals (Narses) / Meteoric Stone. Per-quest countdown — miss it and it can't be completed.
- **F2P currency-from-normal-actions events:** **Dwarf's Lucky Apple** (`dwarfs_lucky_apple-en`) —
  wishing coins from monster kills + gathering; spend on the 1-coin "Wealth" apple (most Pie chances)
  and hand every Pie to a Witch for the big gift. **Crazy Eggs** (`crazy_egg-en`) — hammers (from
  double-drop boss hunts + gathering) smash 4 eggs for gems/stamina/teleporters/artwork chests
  (~58-70 hammers for all four). **Cleopatra's Treasure** (`cleopatras_treasure-en`) — fragments from
  hunting (80/day) + gathering (20/day); the F2P play is to **DISASSEMBLE** fragments for resources
  (~120M each over a 10-day cap), NOT pay gems to open. **Lucky Composing** (`lucky-composing-en`) —
  cards from tiles + monsters; combine 3-of-a-color into the highest Lucky Box before the event ends.

**B. Free but self-contained (play the free allotment, no base timing):**
- **Treasure Hunt / Pyramid (`treasure-hunt-en`, ~10d):** huge free gem source (up to 189K at 500M
  score). Dispatch **weak marches, NO general** to dive Lv3-5 pyramids (20/day, 20 stamina each);
  a `gather`-style loop. **Pre-research the Academy "Mysterious Relic Exploration" + Adv (Alliance)**
  nodes — they raise per-dive score.
- **Hecate's Moon (`hecates-moon-en`):** 2 free Underworld Keys/day; solo monster hunt scored by
  beating the hardest survivable Trial Temple (pick SIEGE-type with strong ground/mounted). Torches
  expire after the event — spend them.
- **Revelation of Maya (`revelation-of-maya-en`):** 20-stage combat roguelike; **no base action helps,
  needs manual buff choices → LOW priority for an economy bot.**

**C. Spend/pay — bot SKIPS (spend-timing only, not action-scored):** **King's Party / Royal Party**
(`kings-party-en`, Basic-Gem "cake", $20-$5,000), **Ekaterina's Garden** (`ekaterina-garden-en`, same
mechanic, cheaper Civilization scrolls), **Limited Time Promotion** (`limited-time-promotion-en`),
event packs. Only Basic (directly-purchased) gems count — none F2P-viable.

**D. Reference/valuation (not scoring):** `contents-of-chest-event-en`, `event-pack-1-5-en`,
`eventpack-5vs1-en` (the $4.99 first pack is the value pick; buy many for gems/stamina/refining, buy
the full 5th set for the exclusive general/scrolls), `material-chest-bag-contents-en`, `auction-en`,
`exhibition-hall-reward-en` (filling Art Hall halls pays gems/stamina/speedups/teleporters).

**make-wounded exploit (`make-wounded-as-you-need-en`):** a monster battle wounds ≤10% of troops sent
(5% with Monarch Talent "Mortality") → send 10× (or 20×) the count you want wounded and **lose on
purpose** to hit "heal N troops" / Power-Increase quotas exactly. Feeds Alliance Competition + Dawn
"Increase Power" scoring. **Passive layer:** Server-Gift wall refreshes **free every server-hour**
(add to daily_collect).

## 9. What to spend vs save (gem-safe)
- **Never gems** (kb/27). **Speedups:** type-specific first, save "General" for emergencies; spend
  big ones on Keep/Academy milestones **on Construction/Research event days (double value)** and heal
  on Power-Increase days; free Alliance Help before any speedup; **the VIP free construction-speedup
  grant** (scales +1min→+4:30/level) is a free daily source to apply.
- **Keep RSS boxed**; open only to fund a queued upgrade. Warehouse as the plunder floor.
- Refining/blazon/monarch-gear detail lives in the wiki's GEAR/BUFF sections (out of scope for this
  ingest), but the two economy-relevant crowns already surfaced here: **Strength Crown** (construction)
  and **Intellect Crown** (research) — equip before starting the matching task.

## 10. Timing infra — feeds scheduler / daily reset
`server-time-chart-en`, `server-merge-en`: **server time = UTC; daily reset at server 00:00.**
Server-Gift wall items refresh every server-hour (free). **Server merges (~1-2×/yr, 10-day notice)
reset resource tiles, relics, and rankings** → rebuild gather/scout targets right after a merge.
`what-is-adv-dispatch-en`: "Adv Dispatch" is **not** an auto-dispatch feature — it is an Academy
Military-category **research** item (+1 march slot per level) that **hard-gates the Keep 14 upgrade**
(Adv Dispatch Lv1 required). Part of the +4-from-research march-slot chain (§5), not a gather helper.

---

## Direct hooks for our code
- **`base_dev.BaseDevPolicy` priority list** (gem-safe, from §1-2): Academy "Builder" research → Keep
  → Academy (+non-stop research: Construction/Typography) → Rally Spot (march size) → Embassy (help
  count) → troop buildings to Keep-required tiers → Warehouse/Hospital/Walls → resource buildings to
  Keep-min. Add VIP17 as an alt 3rd-builder trigger. Respect the disabled-while-upgrading list (§1)
  and Keep-cap deprioritize.
- **`daily_collect.DailyCollector` source additions** (all FREE): server-gift wall (server-hourly),
  VIP free construction speedup, tavern free daily pull, plus the tax/levy whose **counts scale with
  VIP** (Free Tax +3→+13, Gold Levy +5→+140). Keep the red-dot cooldown model.
- **strategist expand-mode timing:** raise idle-march gather budget as March Slots unlock (VIP5+);
  bias `base_dev` toward big Keep/Academy jumps during Construction/Research event days and Consuming
  Return (K25+); bias `monster`/`rally_join` toward Cerberus/Pan (speedups) or Ymir/Witch/Warlord
  (resources) by current need; treat King's Party / packs as non-actionable (never a "spend" target).

## Extra building detail now in `economy.jsonl` (used above)
This local pass captured full detail on several buildings that strengthen base_dev/expand decisions:
- **Holy Palace (Keep 11):** soul revival unlocks **Lv25**, consumes Soul Crystals — required for the
  Dawn "revive 80k souls" quest; gates Keep 38 + Victory Column.
- **Victory Column (Keep 35):** **+80% Construction, +80% Research, march-time reduction, general
  attribute buffs** — a top base_dev accelerator; its attribute buffs count toward duty-officer
  appointment requirements. Gates Keep 36.
- **Ideal Land (Keep 12):** Construction Speed + all-troop HP/Atk/Def buffs from building level;
  place Limited Ornaments (from Voyage to Civilizations) for more. Gates Triumphal Arch Lv6+.
- **Subordinate City (Keep 11):** development cultures **Korea** (gathering+warehouse), **China**
  (production+training), **America** (sub-city gold+research); up to 9 held, stacking. The main free
  economy multiplier for expand mode.
- **Forge (Keep 7):** **Champion's** 4-set (Lv13, +gathering) and **King's Ring** (Lv21, double-drop
  for gold/hammer/medal farming) are the economy-relevant equipment tiers.
- **Prison (Keep 11):** PvP captives → Labor (resources = 4h base production) or Release (50 Prestige).
- **Research Factory (Keep 21, Hospital-gated):** Materials + Research Stones + Historic Medals;
  stones rarely bottleneck research until ~Keep 33 (Military Advance category).

## Pages ledger — `economy.jsonl` (75) + strategy-layer local pages
- **`economy.jsonl` (75, the requested city-development + events + economy scope):** buildings
  (keep, academy, military-academy, research-factory, market, warehouse, farm, sawmill, quarry, mine,
  embassy, hospital, holy-palace, trap-factory, walls, watch-tower, wonder, wisdom_dome, ideal-land,
  art-hall, tavern, forge, arsenal, council-of-state, prison, bunker, triumphal-arch, victory-column,
  shrine, barracks, archer-camp, stables, workshop, army-camp, archer-tower, rally-spot, war-hall,
  subordinate-city-advantages); economy/items (how-to-get: resource, speed-up-items, gold, hammer,
  vip-time, gem, stamina, medal, badge, scroll, teleporter, march-speedup, march-size-increase,
  artwork-fragment; material-chest-bag-contents, server-gift, alliance-shop-item-list,
  battlefield-shop-item-list, auction, exhibition-hall-reward, limited-time-promotion,
  dawn-of-civilization); events (alliance-competition, consuming_return_event, hecates-moon,
  treasure-hunt, revelation-of-horus, revelation-of-maya, kings-party, cleopatras_treasure,
  dwarfs_lucky_apple, crazy_egg, ekaterina-garden, lucky-composing, contents-of-chest-event,
  event-pack-1-5, eventpack-5vs1). Full URLs in the jsonl.
- **Strategy-layer pages (local, cited above but outside the 75-record scope):** troop-upgrade,
  troop-initial-stats, vip-benefits-list, march-size-per-level, how-to-get-more-march-slot,
  make-wounded-as-you-need, what-is-adv-dispatch, server-time-chart, server-merge, how-to-get-skillbook,
  how-to-get-runestone, pasture, dead-keep-power-list — all in `data/pages/`.
- **Out of local set (facts tagged `[VERIFY]`):** construction-en (beginner priority), troop-type-en
  (rock-paper-scissors). Refining/blazon/monarch-gear sit in the GEAR/BUFF sitemap sections (out of
  scope for this ingest; see kb/15/kb/37).
