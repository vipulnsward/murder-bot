# Development & Economy — Strategy Synthesis for base_dev / daily / gather (kb/40)

Distilled from 77 evonyguidewiki.com pages (buildings, troops, items/resources, VIP, events,
mechanics) into `data/guides/economy.jsonl`. This doc turns those facts into decisions for
`base_dev.BaseDevPolicy`, `daily_collect.DailyCollector`, `gather.py`, and the strategist's
**expand** mode. Companion to the generals catalog (kb/36 + `data/generals.jsonl`).

## Verification legend
- **Everything here is sourced from evonyguidewiki.com** — per-page URL in each `economy.jsonl`
  record's `url`. Fetched 2026-07 via the reader-proxy (`crawl_evony.fetch`, Jina) because the site
  sits behind a JS challenge that blocks plain fetch/curl.
- `economy.jsonl` line schema: `{title, url, category:"economy", summary, content}`, one page/line.
- **Numbers drift with game patches** (the wiki is itself patched; e.g. Keep/VIP tables edited
  2025-2026). Treat every level/%/threshold as `[VERIFY IN-GAME]` before hardcoding — same discipline
  as kb/27/kb/36. Ranks/costs are the site's published values, not our derivation.
- **Gem-safe invariant carries over from kb/27**: none of the spend advice below ever taps gems.
  Where a source's headline path is paid (King's Party, packs, tavern gem-refresh), it is flagged
  NOT-ACTIONABLE for the bot and only kept so the strategist knows to skip it.
- Cross-refs: **kb/27** base-dev automation · **kb/28** daily-collect + alliance loops · **kb/13**
  1B resource ceiling · **kb/14** food/tier economics · **kb/15** buff maximization · **kb/16** keep
  growth · **kb/23** gathering · **kb/24-25** rallies/monsters.

## Counts (this pass)
- **77 pages fetched & recorded** (76 batch + Rally Spot); **3 rate-limited (429) then recovered**
  (embassy, barracks, workshop) — polite re-fetch with extra spacing succeeded, 0 permanent skips.
- Coverage of the 4 requested sitemap sections: CITY DEV/BUILDINGS/TROOPS, EVENTS, ITEMS/RESOURCES/
  ECONOMY, MECHANICS/MISC. Highest-value pages prioritized; deliberate lower-value skips listed at end.

---

## 1. Build/upgrade priority — feeds `base_dev.BaseDevPolicy.decide()`
Refines kb/27's priority table with the wiki's own guidance (`construction-en`, `academy-en`,
`upgrade-requirements-keep-en`, `embassy-en`, `military-academy-en`, `rally-spot-en`).
- **Beginner priority after every Keep-up: Academy + Rally Spot FIRST** (`construction-en`). Academy
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
- **4 types, rock-paper-scissors** (equal tier/buff): Mounted > Ground > Ranged > Mounted; **Siege
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
- **Resource item drops:** top resource bosses are **Ymir / Witch / Warlord** (Ymir best per-stamina;
  Azazel/Kraken highest raw yield 4-5M×4); **Cerberus drops 0 resources** (it's a speedup boss — pick
  the boss by what you need). Consuming Return also refunds RSS.
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
build/gather/kill/heal into their windows:
- **Alliance Competition (~10 days, `alliance-competition-en`):** personal score → alliance rank.
  High-value quests that match bot actions (50-240 pts): Cultivate Generals, Consume Runestones,
  **Increase Power** (heal wounded — see §make-wounded), **Gather RSS outside city**, **Kill Bosses /
  Kill Lv14+ Boss** (via alliance rallies), Consume Stamina, **Offer at Shrine** (pre-saved tribute),
  Wheel spins. Challenge slots are capped/non-refundable → **only start quests worth ≥140 (≥170 at
  Elite+); R4/R5 prune low ones.** Barbarian/CoC/sub-city attacks don't count as kills.
- **Dawn of Civilization (~10 days, ~2×/month, `dawn-of-civilization-en`):** 5,000 pts across
  Gathering/Alliance/Ambition; f2p daily paces — gather 6M+/day, produce 5M+/day, cultivate 23×,
  refine 23×, shrine-offer 10×, rally 16×, donate 5×, speed-up-ally 10×, buy 20 black-market items,
  consume 240 stamina (~12 kills), train mass T1, heal 80k, revive 80k souls (Holy Palace Lv25+),
  recall deserters, +70M power, plunder 18M. Rewards include cheap golden historic generals. **No
  per-day theme split** — pace daily, not day-specific.
- **make-wounded exploit (`make-wounded-as-you-need-en`):** a monster battle wounds ≤10% of troops
  sent (5% if Monarch Talent "Mortality") → send 10× (or 20×) the count you want wounded and **lose on
  purpose** to hit "heal N troops" / Power-Increase quotas exactly. Use non-ground troops for a
  reliable 10% cap. Feeds Alliance Competition + Dawn "Increase Power" scoring.
- **Passive-drop events:** Lucky Composing / Crazy Eggs turn normal gathering/monster drops into free
  bonus loot (zero extra action). Treasure Hunt (Pyramid, ~10d) is exploration/gather-adjacent (send
  troops, no combat). Server-Gift wall refreshes **free every server-hour** (add to daily_collect).
- **PURE-PAY — bot must SKIP (do not target):** **King's Party / Royal Party** (Basic-Gem "cake",
  ~2×/month/10d, $20-$2,000), **limited-time-promotion**, most purchase packs (`make-profit-purchase-
  pack-en`, `pay-cheap-en`). Kept only so the strategist never tries to "score" them.

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

## Pages read (77) & deliberate skips
- **Read:** all buildings (academy, keep, construction, embassy, barracks, archer-camp, stables,
  workshop, army-camp, military-academy, research-factory, arsenal, hospital, warehouse, walls,
  watch-tower, market, tavern, wonder, art-hall, shrine, bunker, trap-factory, pasture, farm, mine,
  quarry, sawmill, rally-spot); troops (type/upgrade/initial-stats); ref (dead-keep-power-list,
  ideal-land, art_treasure); items/economy (resource, gold, gem, speed-up-items, hammer, medal,
  monarch-exp, skillbook, teleporter, runestone, vip-time, prestige, material-chest, alliance-shop,
  black-market); march/VIP/spend (march-size, march-size-per-level, march-speed, general-power,
  max-generals, more-march-slot, vip, vip-benefits-list, pay-cheap, make-profit-purchase-pack,
  make-wounded, adv-dispatch, auction); events (category/event, kings-party, treasure-hunt,
  wisdom_dome, server-gift, dawn-of-civilization, exhibition-hall-reward, limited-time-promotion,
  lucky-composing, crazy_egg, tavern-level-and-drop-rates); mechanics (alliance-competition,
  server-merge, server-time-chart). Full URLs in `data/guides/economy.jsonl`.
- **Skipped (lower economy value; next crawl if needed):** buildings archer-tower, prison,
  holy-palace, victory-column, triumphal-arch, bacchus-tavern; items badge, scroll, soul-crystal,
  tactic-scroll, march-speedup, march-size-increase, arrest-warrant, artwork-fragment,
  ascension-fragment; events consuming_return_event (covered inside speed-up-items/resource),
  dwarfs_lucky_apple, cleopatras_treasure, civilization-treasure, revelation-of-horus/maya,
  shadow-of-dawn, hecates-moon, ekaterina-garden, ghost, mysterious-puzzle, event-pack-1-5,
  eventpack-5vs1, what-is-kill-event; misc how-to-change-server, make-sub-account, option,
  quiz_answer_list, term-translation-list, correct-translation-tips. Refining/blazon/monarch-gear
  pages sit in the GEAR/BUFF sitemap sections (out of scope for this ingest).
