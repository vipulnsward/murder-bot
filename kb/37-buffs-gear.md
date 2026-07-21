# Buffs / Debuffs / Skills & Gear — Combat Strategy Synthesis

The combat-buff counterpart to kb/15 (which is economy-first). This doc distills the
buff/debuff math, skill-book + specialty priorities, and the whole gear stack (blazons →
red equipment → civilization gear → monarch gear → seals) into levers a bot or a human
operator can act on. Machine-readable source facts: `data/guides/combat.jsonl` (21 records).

## Verification legend
- **All figures here are sourced from evonyguidewiki.com** (21 pages listed below), fetched
  2026-07 via the Jina reader-proxy (`crawl_evony.fetch`) because the site sits behind a JS
  "verifying" wall that blocks plain curl/WebFetch. Load-bearing numbers (half-reduction rule,
  >2800%/-1100% maxima, specialty step-costs, blazon material counts, forge tier ladder,
  Achaemenidae −15%, refine 80% vs 100%) were re-grepped against the raw pages.
- `[VERIFY]` = tag anything to confirm against the live client before hardcoding.
- Pages read: buff_debuff_basic_guide, debuff-simulator, sub-city-buff-list, rank-buff,
  recommended-skills, skill-book-list, specialty, how-to-add-skill, blazon, how_to_get_blazon,
  monarch-gear, monarch-gear-level-up, how-to-use-monarch-gear, civilization-equipment,
  imperial-parthian-equipment, red-equipment-combination, red-equipment-compare, forge,
  forge-master-certificate, how-to-get-refining-stone, seal (each `/en/<slug>-en/`).
- **Cross-ref kb/15** (buff maximization — economy + the SLOT-dependency rule), kb/01 (combat
  mechanics), kb/09 (battle buffs/training), kb/36 (generals DB), kb/24-25 (rallies/monsters).

## The buff/debuff math (decides everything)
- **Buffs ADD across all sources.** Final stat = base × (Σbuff% + 100%). E.g. 220 × (200%+100%)
  = 660. src: buff_debuff_basic_guide.
- **Flat (absolute) buffs are applied AFTER % and are NOT reduced by enemy debuffs.** Flat is
  better for **t1–t11**, % is better for **t12+**. (Bot trains t1 — flat buffs matter for the
  meat-shield/trap meta.) src: buff_debuff_basic_guide.
- **Debuffs cut an enemy buff by HALF at most, never to 0.** −300% vs a 600% buff → 300%;
  −300% vs 800% → 500% (limited by your debuff size). So stacking debuffs past ~half the
  enemy's total buff is wasted. src: buff_debuff_basic_guide, red-equipment-combination.
- **Observed ceilings:** buffs over **+2800%**, debuffs over **−1100%**. src: buff_debuff_basic_guide.

## Buff-type activation matrix (which buffs fire in which fight)
Six in-game types: **Basic** (always on), **Marching/"Attacking"**, **In-City ("Defending
City")**, **Defense ("Defending~"** — only from Blazon / Military Academy / Castle Decoration),
**Outcity Defense** (only Idunn & Freyja), **Reinforcing**. Applied to YOUR troops:
- Solo/rally **attack** & camp-defense → Basic + Marching.
- **Own-city defense** → Basic + In-City + Defense.
- **Building/relic defense or reinforce** → Basic + Marching + Defense + Outcity.
- Alliance-city reinforce → Basic + In-City + Defense[?] + Outcity + Reinforcing. `[VERIFY]`
- This is the combat analogue of kb/15's slot rule: a buff that reads "Marching" does nothing
  on a city-defense general and vice-versa. src: buff_debuff_basic_guide.

## Debuff doctrine (mayors are the delivery system)
- **Mayor/sub-city BUFFS never reach main-city troops**; only mayor **DEBUFFS project** to a
  fight (matches kb/09). So equip sub-city mayors purely for debuffs. src: buff_debuff_basic_guide.
- **Solo defense: mayor debuffs STACK** (sub-city must be alive/in battle). **In a RALLY only
  the single strongest debuffer applies** (−70% + −140% → only −140%). So debuff-mayors shine on
  solo hits and city defense, not shared rallies (aligns with kb/24's rally caps). src: buff_debuff_basic_guide.
- **Debuff magnitudes** (debuff-simulator): red gear −33% to −40%/piece; Achaemenidae 6/6 =
  **All Troops Attack −15%**; specialty debuffs (Snipe/Sabotage/Suppress) Lv1→5 = −1/−2/−4/−6/−10%;
  blazon attack sets 2/6=−20%, 4/6=−20%/−20%; spiritual-beast single stat Gray −2% → Gold −30% →
  Red −52%; sub-city mayors −10% to −50% (Narses Ground Atk −50%). **Debuff priority order**
  (from kb/09): enemy ground HP+Def first, then archer Def/Atk, then mounted HP/Atk.
- More monarch **rank** and **prestige** = more subordinate-city slots = more stackable
  debuffers on solo/defense. Duke +5, Archduke +6. src: rank-buff.

## Skills & specialties
- **6 skill-book slots** per general (main+assistant combined); **Mayor & Duty Officer = 3**
  (no assistant). Troop-type buff books do NOT work on Mayor/Duty. src: recommended-skills.
- **"Develop Strengths":** Mounted→Attack, Ranged & Siege→**Range**, Ground→HP & Defense.
  **Range and Speed can ONLY come from skill books** → always high priority (Range = ranged/siege,
  Speed = mounted/ground). src: recommended-skills.
- **Numbers** (skill-book-list, Lv1/2/3/4): troop-type Atk/Def/HP **10/15/20/25%**; March Size
  3/6/9/12%; March Speed 10/15/20/25%; Range flat +25/50/75/100 (ranged), +50/100/150/200 (siege);
  Luck (double-drop) 5/10/15/**18%**; debuff books −2/−5/−9/−15%. **Siege HP/Def books only 25% →
  low priority.**
- **HP > Defense** on marches (fewer injuries); **Defense is near-useless vs bosses** (5000% Def
  barely dents boss damage). src: recommended-skills.
- **Adding skills is probabilistic:** 1st add 100%, 2nd 50%, 3rd 25%, and a **fail overwrites**
  an existing skill. Reliable method: **fill all 3 slots with Lv1 versions first, then overwrite
  each with Lv4** (higher level overwrites same skill at 100%). Some generals accept only Lv4
  (Khalid, Barbarossa) — trick fails there. Books = 3,000 gems each. src: how-to-add-skill.
- **Specialties:** gold generals have 4 (purple 3), unlock at general Lv25. Step-costs
  (runestones/gems): Green 200/4k, Blue 500/10k, Purple 1k/19,980, Orange 3k/60k, **Gold
  8k/160k**; maxing 4 = 50,800 runestones + ~1.02M gems. Immortal runestone (slot 4) is the
  ~10%-drop bottleneck. **F2P ≈ 2–3 years → pour runestones into ONE general first.** Flexible
  5th Specialty: unlocks when the 3 left are gold; **"Battle-Tested" is the F2P-friendly** pick.
  src: specialty.

## Blazons — the biggest F2P combat lever (cross-ref kb/15's blazon note)
- **48 blazons = 8 sets × 6 elements.** Equip at the four training facilities (stable / archer
  camp / barracks / workshop) from facility **Lv8**; 6 slots each at facility **Lv29**. Each troop
  type equips 2 blazons each of **Attack, Defense, HP**. Max blazon **Lv20** (3rd buff at Lv10,
  4th at Lv15). Page states **"nearly 100%"** Atk/Def/HP at Lv15. src: blazon.
- **Upgrade cost (feeding Lv1 blazons):** Lv1→10 = 119 pieces, →15 = **349**, →20 = 874 (Lv2+
  material returns 80% EXP). **Prioritize your main troop type** (bot trains ground → Ground
  sets Justice/Sacrifice). src: blazon.
- **F2P sourcing:** Trial of Sphinx (~1/kill, up to 12/day), Revelation of Horus daily ranking
  (up to 36/event), Alliance Duel shop (1/300 coins), daily Tavern. src: how_to_get_blazon.

## Gear stack — tiers, sets, refine priority
**Forge ladder (unlock by Forge level):** Lv5 Purple · Lv9 Orange · **Lv13 Champion's** · Lv17
General's · **Lv21 King's** · Lv27 Red **Dragon** · Lv30 **Ares/Imperial** · Lv33
**Achaemenidae/Parthian**. Forge built at Keep 7; Lv26+ needs Watchtower. Civilization gear is
crafted at the **Wonder** (Keep 33), not the Forge. src: forge, red-equipment-compare.

- **Red equipment = Dragon < Ares ≈ Achaemenidae < Imperial/Parthian < Civilization.** Only
  **Ares & Achaemenidae carry debuffs** — **Ares = attacking, Achaemenidae = defending + mayor
  debuffs**. src: red-equipment-compare.
- **Refine priority: DON'T refine Dragon gear** — its refine cap is **80%** vs **100%** on
  Ares/Achaemenidae; upgrade Dragon→Ares first (Dragon 4×+20%=80% vs Ares 4×+25%=100%). Refine
  caps are unchanged by the Imperial/Parthian upgrade (attack still 25%), so **refines carry
  over** — no need to re-roll after upgrading. src: red-equipment-compare, imperial-parthian.
- **Set bonuses:** full **Ares/Achaemenidae set = All Troops Attack +25% when attacking**
  (+25% Ground&Mounted vs monsters); **full Achaemenidae = −15% All Attack debuff** (LOST if you
  mix any Ares piece in). **Imperial** 6/6: Attacking Atk 15→18%, March Size 10→12%. **Parthian**
  6/6: All Atk 10→12%, Enemy Atk −15→−18%. src: red-equipment-combination, imperial-parthian.
- **Role builds (red):** Attack general = buff gear, Defense general = buff gear, **Mayor =
  debuff (Achaemenidae-only)**. Mayor craft order: Courageous Achaemenidae Ring → Helmet →
  Axe/Spear → rest. **Monster-hunt** build keeps the **Courageous Dragon Ring** (only ring with
  double-item-drop +20%), accepting a weaker +15% set buff. src: red-equipment-combination, red-equipment-compare.
- **Civilization (Star Atlas) = strongest tier;** own-set passives apply even when mixing, so
  **mixed builds win for most roles** (Ranged: Thebes+Plantagenet+Sassane 463% buff/320% debuff;
  Ground: Aztec+Furinkazan+Antonine 609%/410%). Unify for Siege (Heian/Abbas) and Defense
  (**Koryo 1170%**). F2P-vs-paid not stated on that page. `[VERIFY]` src: civilization-equipment.
- **Upgrade materials:** Imperial/Parthian need **Forge Master Certificate** (25/50 per piece)
  + Lv7 red materials + 100 Badges + 10M Gold. Certificate from Gather Troops event (≤40) and
  Vikings (Hard ≤10, Hell ≤20). **Refining Stones** (Ares refine = 200) from Crazy Eggs, boss
  guaranteed-chests, Gather Troops, Viking Hard. Use double-drop generals (Baibars + King's Ring)
  to farm. src: forge-master-certificate, how-to-get-refining-stone.

## Monarch gear (swap-per-activity — combat side of kb/15)
Level by **combining 3 same-level pieces**; NEVER build from the store (a Lv15 piece = ~957M
gems). Cheap path: **patrol constantly** → black market → daily Wheel of Fortune (~100 patrols =
30–40 pieces for ~1,000 gems). Combat pieces: **staff/grail/decoration** matched to your main
unit (ranged = Wind, monster-hunt cavalry = Thunder). **Timing rule:** a construction/research/
craft buff only counts if equipped **exactly when the action starts**; gather/carry buffs lock
in **when troops arrive** at the tile — both removable afterward. Save presets via the armor
icon. src: monarch-gear, monarch-gear-level-up, how-to-use-monarch-gear.

## Passive combat stacks (set-and-forget)
- **Spiritual-Beast Seals** work like research — **always-on buffs, no beast attached to a
  general** (no dragon slot cost). Only 2nd/3rd-gen beasts; unlock at beast Lv10. 5 Seals/beast
  to **Lv25** (cap raised 20→25 on 11/7/2025). Cost rises quadratically while gain flattens →
  **level ALL beasts evenly (10, then 15, then 20)**, don't max one. PvP-ranged: Otso/Hati/
  Thunderbird/Nine-Tailed Fox; PvP-defense: Hati/Chiron/Pegasus; monster: Tarasque/Chrysomallos/
  Nandi/Pegasus/Chiron. src: seal.
- **Sub-city cultures** (combat picks): **Japan** = stacked marching attack (offense), **Russia**
  = in-city defense attack + traps (defense); same-culture stacks additively. src: sub-city-buff-list.
- **Rank buffs** (Knight→Regent): Training/Healing/March/Traps +5→+70%; **March Size +5,000→
  +100,000**; sub-city slots +1→+6. Gate on prestige (Regent = 3,000,000) OR VIP13–19. src: rank-buff.

## Prioritized combat action list (F2P first)
**Tier S — cheap, permanent, high %:**
1. **Blazons** on the main troop type → push to Lv15 ("nearly 100%"). Biggest F2P lever.
2. **Skill books**: fill 6 slots per PvP lead with the Lv1-first→Lv4 method; always take Range/Speed.
3. **Beast Seals** leveled evenly across all beasts (always-on, no slot cost).
4. **Fill sub-city mayor debuff gear** (Achaemenidae) — debuffs project to fights and stack solo.

**Tier A — moderate grind:**
5. Push **Forge level** to unlock Champion's(13)/King's(21)/Dragon(27)/Ares(30)/Achaemenidae(33).
6. **Upgrade Dragon→Ares before refining**; refine to the 100% cap on Ares/Achaemenidae.
7. **Rank/prestige → Duke+** for march size + more debuff-mayor slots.
8. One **F2P specialty general** to Orange/Gold (Battle-Tested flexible specialty).

**Paid track:** Civilization (Star Atlas) mixed sets per role · Imperial/Parthian upgrades
(mayor Parthian first if Civ-rich) · gold-specialty runestone spend on one lead general first.

## Uncertainty register
- Alliance-city reinforce buff set (Defense component) `[VERIFY]`; exact per-level blazon buff
  tables have "?" cells on-page; Seal Lv20–25 gem/crystal costs listed as "?"; Chimera In-City
  +215% flagged by the source as a possible error; Civilization-gear F2P-vs-paid framing not
  stated on that page. Confirm all against the live client before hardcoding into bot logic.
