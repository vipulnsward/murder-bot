# Murder Bot — PvP Combat Brain

Synthesized model of Evony: The King's Return PvP combat, built from web research (evonyplayersguide,
server806, theriagames, evonyguru, onechilledgamer, empirebuildacademy, evony-battle-simulator) plus
patterns learned from NeoIsTlatoani's own parsed battle reports (Postgres `report_extracts`).
All combat numbers are community reverse-engineering (Evony never published the formula) — directional,
not exact. Version-dependent; re-check periodically.

Commander: NeoIsTlatoani (NFG, K49). Profile: siege-anvil defender, strong Ground; 75% low-tier fodder,
real high-tier army ~530M, T17 unbuilt.

---

## 1. The counter triangle — what kills what

Rock-paper-scissors among the three field types, Siege is a 4th special piece.

- **Mounted → Ground** (1.2x). Ground→Mounted only 0.7x.
- **Ground → Ranged** (1.2x). Ranged→Ground 0.8x.
- **Ranged → Mounted** (1.2x). Mounted→Ranged 0.8x.
- **Ground / hi-tier(T11+) Mounted → Siege** (1.1–1.2x). Siege→anything only 0.3–0.6x.

Damage multiplier matrix (attacker row → target col), T1–T10 (T11–16: Mounted→Siege 1.1, Siege→Siege 0.6):

| Atk ↓ / Tgt → | Ground | Ranged | Mounted | Siege |
|---|---|---|---|---|
| Ground  | 1.0  | **1.2** | 0.7 | 1.1 |
| Ranged  | 0.8  | 1.0 | **1.2** | 1.1 |
| Mounted | **1.2** | 0.8 | 1.0 | 0.9 |
| Siege   | 0.35 | 0.4 | 0.3 | 0.5 |

**Target priority (#1 target = the type it counters):**
- Ground → Ranged → Siege → Ground → Mounted
- Ranged → Mounted → Ranged → Ground → Siege
- Mounted → Ground → Siege → Mounted → Ranged
- Siege → Siege → Ranged → Ground → Mounted

Within a priority level: highest tier first, then largest count.

**Damage model:** `damage = count × ATK × modifier × ATK/(ATK+DEF)`; `kills = damage / target_HP` (capped at target count).
High ATK + favorable modifier vs low DEF/HP → kills; high DEF/HP → blunted into WOUNDED instead.
**Overkill cliff:** survivors counter-attack; wiping a stack to exactly zero prevents all return damage → concentrate fire, highest-tier first.

---

## 2. Range, rounds, how a battle resolves

- **Range decides who fires first:** Siege (900→1400 by tier) > Ranged (500, flat) > Ground/Mounted (~50 melee).
  Siege fires first and unanswered, then Ranged, before melee closes.
- Battle runs in server-side **rounds** (never shown): Movement → Unit Battle → Fortification. Phase order
  Siege → Ranged → Mounted → Ground; attacker before defender; higher tier before lower.
- **No fixed round cap** (15 is a myth). Runs until one side is wiped (or a march retreats).
- **Win/Loss = wipe:** the side with zero surviving troops loses. NOT decided by power on paper.
  "Attacks Won" = you wiped the defenders; "Defenses Won" = you wiped the attackers.

---

## 3. Tiers + layering (the dominant edge)

- Base per-troop stats scale **~1.3x per tier per stat** (ATK/DEF/HP together). T1→T14 ≈ 35x. Each tier ≈ doubles effective power. (12,500 T14 = 100,000 T11 for the same kill.)
- Archetypes: **Mounted** highest ATK; **Ground** highest DEF+HP (anvil); **Ranged** high-ATK/low-HP DPS; **Siege** longest range, paper HP, weak counter-mult (wins by range+stats, not the triangle).
- **Layering is the real advantage:** each troop type+tier targets ONE enemy type+tier per round. An army with many populated tiers + thin decoy layers of other types forces the enemy to waste rounds chewing junk while your top tier keeps firing (a full-layer march gains ~50 rounds of targeting advantage over a single-tier one).
- **Attack march:** 25–40% top tier, 25–40% 2nd, 10–40% 3rd, 0.25–2% each remaining tier, +1–10k of every OTHER type as sacrificial decoys.
- **Power is a poor predictor** — use effective stats after buffs + tier composition + matchup.

---

## 4. Decoding the report casualty fields

- **Killed** — permanently lost (except SvS-revivable, or converted to Souls/Deserters below).
- **Wounded** — survived but need Hospital. DEFENDING: casualties go to Wounded up to **Hospital/Wounded Capacity**, then overflow is Killed. **ATTACKING (PvP, marching out): losses are ~ALL KILLED — 0% wounded, no hospital** — unless you carry a death-to-survival buff. (The ~10% wounded cap is a MONSTER-only rule, NOT PvP.) So a *lost attack = permanently dead troops*, while a lost defense = recoverable wounded — a hard reason offense is far riskier than defense for you.
- **Survived / "Turned death to survival"** — survival-rate buffs convert would-be deaths straight to alive (free, best outcome).
- **Deserter** — troops that fled the march (not dead); recalled FREE at the Holy Palace (has capacity).
- **Holy Palace Troop Soul** — a share of KILLED become souls, revived at the Holy Palace (unlock L25; 10 soul crystals → 3,000,000 power; must be built BEFORE deaths).
- **Captured** — troops/resources seized by the winner.

This is why a **siege-anvil defender is efficient**: with big Hospital + Holy Palace capacity + Medical-Aid research, most defensive "deaths" are recoverable → absorb repeated attacks cheaply, as long as wounded capacity isn't exceeded.

---

## 5. Buffs & debuffs (the dominant battle lever)

- **Buff wording gates context:** "Marching…"/"Attacking Troop…" fire when troops leave the city; "In-City…"/"Defending Troop…" fire only when defending in the keep; unqualified ("Siege Attack") fire in both.
- **In-city siege attack ≠ marching siege attack** — different non-overlapping pools. The wall (Main City Defense) general's skill fires ONLY in-city (e.g. Zhou Yu +40% ranged/siege atk in-city). Build a defender and an attacker separately.
- **Debuffs** reduce enemy buffs, capped at ~50% of the enemy's total for that stat. 1000–2000% siege HP/Def/Atk debuffs come from **subordinate-city mayors** (skill + gear + debuff beast), stacked across 6–8+ sub-cities. They collapse the attacker's siege/ranged buffs toward the 50% floor → the attacker's on-paper power massively overstates real power. **Sub-cities must stay garrisoned** or they die and stop debuffing.

---

## 6. Rally & reinforcement

- **Rally:** leader's buffs + general apply to the WHOLE force; joiners contribute troops only. Resolved as ONE battle. PvP: joiners fill capacity with strong layers.
- **Reinforcement into a defended keep:** troops stack; each reinforcer keeps their own NON-marching buffs (loses "Marching…" buffs). Wounded fill the host's hospital.
- Max 6 march slots; march size scales with Rally Spot level (raise it first — % buffs multiply the base).

---

## 7. Applied to NeoIsTlatoani (learned from your reports)

**Your defense-battle buffs (all-type, from 8 defense battles vs [ViG]Katar/Viper2302, most-common value):**
Siege atk 5,861 / def 4,680 / hp 4,851 (your strongest branch, tops all three). Ranged atk 5,162. Ground atk 3,498 / def 4,545. Mounted atk 3,798.

**Why your Ground did the most killing in the observed rally (595M+):** Ground counters Ranged (1.2x) AND Siege (1.1x) and hunts enemy Ranged first — so against a Ranged/Siege-heavy enemy, your Ground shreds. Your siege wins by range+stats (fires first, tanks), not by the triangle.

**Win/Loss record (parsed reports):**
- Winning: [ViG]Katar 3–1, [DTP]Polaris 2–1, [ViG]Viper2302 2–1.
- **Losing: [DTP]Karu 0–2, [DTP]Tekeshi 0–1, [NFG]ETopshOt 0–1.** → priority to analyze once stat extraction is clean (need their troop composition + buffs to see WHY).

**Defense investment priority (K49 siege anvil), highest ROI first:**
1. Koryo civilization set (unify) on the wall general — +25% in-city def/hp, +50% ranged/siege atk, ~+1170% total. (Heian is for a MARCHING siege attacker, not the wall.)
2. Dedicated wall general fully ascended: Takenaka Shigeharu (pure siege anvil) or Zhou Yu (siege+ranged) or Stephen II.
3. Subordinate-city debuff network (6–8 sub-cities, each debuff general + beast + gear) — collapse attacker buffs to the 50% floor. Keep them garrisoned.
4. Hospital + Holy Palace capacity + Medical-Aid research — maximize recoverable wounded vs permanent killed.
5. Defensive beast on the wall general: Nandi (in-city HP + ranged/siege atk + enemy ground-HP debuff) or Behemoth King (pure siege).
6. Sacrifice-type defending blazons + Advanced-Refine defensive gear.
7. Full defensive layers (all tiers) + a T1-mounted trap front layer so high-tier siege/ranged aren't hit first.

**Not a gap:** your siege ATTACK (5,861%) is already strong. The real remaining lever is **enemy siege HP/Def debuffs** from the sub-city network to KILL what your anvil tanks, not just survive.

---

---

## 8. Defense loadout — close the debuff gap (specific names)

Your siege buffs already exceed every floor. The one real gap is **debuffing incoming siege/ranged**. Priority:

1. **Sub-city debuff layer (biggest ROI).** Push to **9 sub-cities**; set debuff mayors, best vs siege+ranged: **Cimon** (SA-40/SD-30/SH-30/RA-40, best single) → **Gilgamesh** (SD-40/RD-40) → **Jan Karol Chodkiewicz** (SD-30/SH-30) → **Zizka** (RA-40, broad) → **Baldwin IV** (RA-35/SA-25) → **Flavius Aetius** (SA-20), then Pachacuti/Cixi. Debuffs STACK across all 9 (verified: mayor DEBUFFS apply to the whole keep; mayor BUFFS do not). Put **debuff gear + a debuff spiritual beast** on every mayor (specific "Achaemenidae/Parthian" gear sets are unconfirmed — the debuff comes from the mayor's skill+specialty+equip). Keep sub-city reinforcement to the keep ON — a wiped sub-city (and its mayor) dies and stops debuffing; sub-city troops die outright, not wounded. (Base numbers ~double at your maxed level; the 9-mayor sum is the ~1,500-2,000% aggregate.)
2. **Debuff beasts onto the mayors** (one each): **Jormungandr** (Siege HP -52%), **Otso** (Siege Def -52%), **Tarasque** (Siege Atk -104% defending), **Chimera** (Siege Def -52%), **Chrysomallos / Burning Godzilla** (Ranged Def).
3. **Wall general:** **Zhou Yu** (+4,096%, all types) if you can 5-star him, else **Takenaka Shigeharu** (+3,856%, and he brings Enemy Siege Atk -10%). Put **Dragon of Thebes** on the wall (beasts go to mayors). Niccolo Piccinino is the #1 ground/assistant if leaning ground.
4. **Koryo civ gear 6/6** on the wall (Armor→Helmet→Leg→Weapon/Ring refine): +1,170%, Siege Atk +235/Def +135/HP +75, +15% siege range, and it carries 235% enemy debuff itself. Heian is siege *marching* offense only.
5. **Defending blazons:** **Humility** (siege) + **Sacrifice** (ground) + **Compassion** (ranged), substats rolled to Defending Def/HP.
6. **Validate:** Monarch → Detail — watch your Enemy Siege Def/HP + Ranged Atk/Def totals climb as you add mayors.

## 9. Counter the attacker (scout, then adapt)

Scout with **Watchtower** (L8 numbers, L21 types, L30 their buffs, L37 their generals, L41 reinforcement buffs). Then reinforce the type that beats their lead + match traps:

| They bring | Weakness they exploit | Reinforce with + trap |
|---|---|---|
| Siege (Presley O'Bannon; opens at max range on your siege/ranged) | Outranges + kills your siege first | Mounted/ranged to close on their fragile siege; deeper meat-shield; **Fire-Arrow traps (anti-siege)**. Win by debuffing their siege HP/Def. |
| Ground (Lafayette, Vercingetorix) | Strong vs your ranged | **Mounted** + ranged behind a ground buffer; **Trap (anti-ground)** |
| Ranged (Marcian, Charles VI) | Strong vs your mounted | **Ground** lead + your ranged; **Fire Arrow traps**; enemy-ranged debuff (Chrysomallos/Zizka) |
| Mounted-heavy | Overruns ground, closes on siege | **Ranged** + ground layer; **Abatis traps (anti-mounted)** |
| Debuff-stacked | Cuts your buffs up to 50% | **Flat-refine T1-10** (debuff-immune); stack return debuffs |

**Diagnose a loss from the report** (top-down Summary → Troop Buff → Battle Detail): buffs cut = they debuffed you (flat-refine + return debuffs); a whole tier/type missing in Battle Detail = layer gap (fill all tiers); one tier wiped = wrong matchup (reinforce the counter); all-killed/0-wounded = **hospital capacity overflow** (raise Hospital level + Medical research + an **Arabia sub-city**); a sub-city did nothing = it died (keep ≥1 troop alive). **When NOT to defend:** if their buffs beat yours even after your 50% debuffs, or wounded-cap < their damage → shield/port/ghost.

---

---

## 10. Advanced mechanics (the not-easily-understood core)

**Effective-stat formula:** `stat = base_tier × (1 + max(Σbuff% − Σdebuff%, 0.5×Σbuff%)) + flat`.
- Every % buff source (research, general skill+specialty, gear, refine%, beast, dragon, civ set, blazon, monarch, alliance, VIP, SvS) **adds** into one pool per stat; only ONE multiply. FLAT refines are added *after* the multiply → **immune to debuffs** (base and flat are never touched, debuffs only bite the buff-% pool).
- **50% debuff cap:** you can remove at most half the enemy's buff for a stat. e.g. enemy +5,000% siege atk, you stack −3,000% → capped at −2,500 → they keep 2,500% (×26). **The last 500% is wasted** — stacking debuff past 50% of their buff has zero value. ("Half your debuff value" is a myth; the cap is a floor on THEIR buff.)
- **Flat beats % for tiers up to ~T11** (crossover base = flat/percent) AND is debuff-proof → why the low-tier wall is flat-refined.
- **Your sub-city mayor debuffs STACK additively across all 9 cities** (apply to the whole keep). Debuffs from separate *reinforcers* do NOT stack (highest applies, contested) → stack debuff on your own mayors, not on reinforcements.
- Displayed buff numbers lie: Monarch/Detail omits general skills; the battle-report buff line is pre-debuff. Neither is the number in the formula.

**Round resolution:** action order is by **speed** (Ground→Mounted→Ranged→Siege; defender wins same-speed ties), but who *hits first* across opening rounds is by **range** (Siege 900-1400 > Ranged 500 > melee 50). Each populated **layer** fires once per round at its single highest-priority target; shots/round = number of your layers.
- **Overkill cliff:** counter-fire happens only if survivors > 0. Wipe a stack to **exactly 0 → it throws NO return volley**; leave a sliver → near-max counter. Size attacks to exactly wipe dangerous layers. Melee (range 50) can't counter Ranged/Siege shooting from range → glass-cannons farm melee free early.
- **Layering advantage** = overkill-waste avoidance + priority distraction: decoys only absorb enemy fire from types whose priority chain ranks the decoy ABOVE your main force (a mounted decoy soaks enemy Ranged + Mounted, not Ground/Siege).

**Casualty pipeline:** raw losses → **survival conversion** (death-to-survival buff, free, first) → **wounded/killed split** (DEFENSE: wounded up to Hospital capacity, overflow Killed → "all killed / 0 wounded" = capacity overflow; PvP ATTACK: ~ALL KILLED, no hospital unless death-to-survival buff; MONSTER: ≤10% wounded, ≤5% w/ Mortality) → Killed → **Souls** (revive, 10 crystals→3M power, rate stacks to 100%) + **Deserters** (free recall). Overflow beyond Holy Palace capacity = permanently lost.

**Scoring is tier-weighted, not power-weighted:** CoC points per 1M killed — T1=4, T5=44, T10=128, **T15=280** (a T15 kill ≈ 70× a T1 kill). Plus objectives score continuously. That's why you can lose the power exchange but win on points (kill fewer high-tier, or hold buildings). SvS makes killed troops revivable (Revive tab, +50% capacity).

## 11. Event play — where a defense anvil scores (verified)

Scoring scales DIFFER per mode (not one table). **The exploit for a defense build: battlefield instances (Clash of Civilizations, Battle of Constantinople/Gaugamela) FREE-HEAL every loss** — killed troops become wounded, heal free, and auto-recover after the event → **zero permanent troop loss**. CoC even regenerates troops mid-battle (Auxiliary Buff, by current count incl. wounded).
- **CoC = your best mode.** Tank aggressively, and **HOLD objective buildings** — Rally Hall / Battlefield Hospital / Empire Turret at **500 pts/min = 30,000/hr**, which dwarfs troop kills. Your anvil holds them while allies farm kills; enemies breaking on your wall = free kill points. Never leave early (score resets to 0). CoC troop kill points: T1=4 … T15=280 (table stops at T15; T16/17 points are boss monsters only — Jormungandr 400, Typhon 420).
- **Open-map SvS / Kill Event = highest caution.** No free heal → losses past hospital capacity die permanently AND feed the enemy server's score. Bubble/ghost when idle; **reinforce allies** (your siege HP soaks rallies → attacker losses score for YOUR server); max hospital capacity. Don't open-field a defense build.
- **Occupation >> kills for a defender** in every instanced mode. Throne War (1,500/sec holding, no bubbles) is also built for anvils.

## Simulator-verified (cloned battle-engine on your real roster)
- You DEFEND vs a DTP T16 attacker → you **wipe them every time**, losing 5–25%; **sub-city debuffs cut your losses ~65%** (83M→30M). Even under a −2,000 enemy debuff you still win (losses rise to ~49%). A **mono-ranged attacker is easiest** (12% losses — your Ground counters their Ranged); mono-siege easy too.
- You ATTACK Polaris with a real march-size-capped force → you **lose** (your marching buffs are far weaker than their in-city, and a single march is a fraction of your army). Confirms: **don't attack; make them come to you.** (Sim is a fan model — directional, not exact.)

## 12. Build targets, counter table, and when to ghost (verified)

**Your buff/debuff targets (K40 siege defender) vs where you are:**

| Stat | K40 aim | You | |
|---|---|---|---|
| Siege Attack / HP / Def | 2,200 / 2,000 / 2,000 | 5,861 / 4,851 / 4,680 | ✅ 2–3× above |
| Enemy Attack debuff | 1,500 | ~gap | ← build this |
| Enemy HP / Def debuff | 500 / 500 | ~gap | ← build this |

So your **only** gap is the enemy-debuff column — the sub-city mayor network. Everything else is over target.

**Build order (all max L50):** Wall → Hospital → Archer Tower → Rally Spot → Watchtower(→37 for incoming-general intel). **Research:** Construction/Typography → Hospital Scale (+50k) / Super (+150%) → Defense Advance → Defensive Mastery. **Refine:** **% on the high-tier siege anvil (T11+)**, **flat on the T1 fodder/trap layer** (flat is debuff-immune).

**Keep FULL 4-type layers.** Theory says a *mono*-siege anvil is soft to ground/mounted — but the simulator shows your **full 4-type defense wins every matchup** because you hold the counters (mounted vs their ground, ranged vs their mounted). Don't collapse to siege-only. Your priciest matchup is **mono-siege (fires first)** — that's where enemy-siege debuffs + Fire-Arrow traps matter most.

**Counter each incoming archetype:**

| They lead | Lead your defense with | Debuff mayor | Defending beast (−104%) |
|---|---|---|---|
| Siege | ground meat-shield + your siege (need +15% siege-range ring) | Cimon | Tarasque → enemy siege atk |
| Ground | Mounted | Narses (ground −50/40) | Duneyrr → enemy ground HP; Hati → enemy mounted atk |
| Ranged | Ground | Gilgamesh | Rainbow Crow → enemy ground atk |
| Mounted | Ranged | Hojo Ujiyasu | Otso → enemy mounted HP |

**When NOT to defend:** the 50% debuff cap means you **cannot out-debuff a 3,000%+ whale rally** (T15–17, 5M+ troops). Against those → **ghost or bubble** (empty keep denies the kill; ghost via a long rally/gather/march). Save the anvil for solo hits and rallies you can actually math-out — and a rally's **visible countdown** is your window to reinforce + max debuff mayors on the leader's lead type.

_Sources: scratchpad pvp_research_* .md (counters, rounds, rally_defense, flip, loadout, stacking, layering, casualties, defense_depth, generals, events, buildorder, dtp_comps) + sim_results/2/3, plus the cloned battle simulator at scratchpad/evony-battle-simulator/. All combat constants are community-reverse-engineered (Evony published no formula), directional and version-dependent; damage-line algebra and several rates are fan models — flagged in the notes._

---

## Report-derived per-tier kill data (from my own battle_details, 2026-07-27)

Only **3 of 101** parsed reports carry per-tier `battle_details` (the round-by-round troop tables — they exist only on reports with the golden **Battle Details** icon). All 3 are *attacks* I made. Numbers are OCR-noisy (some tier rows duplicate, and the value `595,139,278` bleeds across two reports — treat exact figures as ±, the **pattern** as solid):

- **Ground T11–T14 = my dominant ATTACK killers.** Validated Polaris attack: `ground:XI` and `ground:XII` each ≈ **185.9M killing**; `siege:XVI` ≈ 70.8M, `siege:XVII` ≈ 31.8M. In offense my **ground low-tier layers do the most killing**, siege high-tier is strong secondary. (Contrast: on DEFENSE the **siege anvil** is strongest because it fires first at max range — different job, different branch.)
- **Attacking a strong keep is catastrophic — measured.** One "Attacks Won" report: I sent 11.4M troops, **only 1.83M survived (84% lost)**, while the 699M-troop defender kept **684M (98% survived, 15M wounded = 2%)**. That is the "offense is the trap" thesis with real numbers: I traded ~9.6M of my troops to wound 2% of theirs. A lost PvP attack = those troops die permanently (no hospital), so this is a pure, unrecoverable loss.
- **Takeaway for the advisor:** when I *must* attack, lead **ground T11+ layers** (my proven top killers), keep siege T14–17 behind them, and never attack a keep whose defending troop count approaches or exceeds my march — the per-tier data shows my kill output collapses against a full high-tier defender wall.

**Enrichment gap:** the 5 loss reports (1 Attacks Lost, 4 Defenses Lost) and the 33 defense-wave wins have **no** battle_details — so "what troop tier beat me, in how many rounds" on my *losses* is still unmeasured. Filling it needs a targeted re-film of those specific reports with the Battle-Details drill (must pause `video_report_loop.sh` first — concurrent `adb screenrecord` collides, err=-10005). Highest-value next scan when the account is reliably free.

---

## Loss analysis — all 9 loss reports (from existing stats, 2026-07-27)

Mined the DB directly (no re-film). Two clean patterns, both confirming the defensive-fortress thesis with real numbers:

**5 ATTACK losses (2026-07-25, 22:23–22:26 — a 3-minute burst):** every one is the same misplay —
| my march | survived | my loss | defender troops | their loss |
|---|---|---|---|---|
| 11.43M | 1.83M | **84%** | 2,122M | 0.2% |
| 10.98M | 1.76M | **84%** | 1,327M | 0.5% |
| 11.07M | 1.77M | **84%** | 660M | 13% |
| 11.42M | 1.83M | **84%** | 684M | 3.6% |
| 11.43M | 1.83M | **84%** | 699M | 2.1% |

I threw ~11M troops at keeps holding **660M–2,120M** (60–190× my march) and got **84% wiped every time** for near-zero enemy damage — ~48M of my troops burned across the burst. Offense-is-a-trap, five data points. **Rule for the advisor: never attack a target whose defending troop count exceeds ~2× my march (~11M) — and these were 60–190×.** (The consistent 11M→1.83M figures are reliable; the 2.1B defender total may be city+reinforcement sum or partly OCR-inflated, but even the low end (660M) is a 60× overmatch.)

**4 DEFENSE losses (2026-07-23):** I lost to **mega-rallies**, not solo hits —
- attacker **7,570M** troops (60.9B power) vs my 12.98M garrison → I lost 1.42M.
- attacker **132.6M** troops (3B power) vs my 13.05M → I lost 1.26M.
- (two more "Defenses Lost" show only 2,560 / 7,106 troops lost — likely scout/partial reports, low signal.)

Confirms the sim: solo hits I win, but a coordinated rally of 130M+ (here up to 7.5B) overwhelms my ~13M garrison. **Those get bubbled or ghosted — the 50% debuff cap can't save a 60×-outnumbered wall.**

**Ground-truth check (raw_text, 2026-07-27):** all 9 losses are **open-map**, tagged "Alliance War Lost" / "City X:.. Y:.. — All your troops were annihilated!", single attacker `[NFG]NeoIsTlatoani` vs a single defender ([DTP]Polaris/Tekeshi/Karu, [ViG]Katar/Viper/SAM/Doner Daddy). **None were Battlefield events** — so the 84% loss was *permanent*, not a free-heal.

**Net doctrine (corrected 2026-07-27 per user — big targets are NOT off-limits, it's HOW you hit them):**
1. **Coordinated RALLY** is the right way to take a big target — the alliance combines into one hit that removes a real chunk, cost is shared, and repeated rallies force **hospital overflow → permanent kills → the whale shrinks** ("rally big targets to make them small later"). 
2. **Battlefield events (CoC/BoC/BoG) free-heal every loss** → rally to **zero** people at *no real cost*; aggressive big-target zeroing is the whole game there (that's what the user means by "Battlefield rallies zeroing people"). See §11.
3. **What actually loses** (these 9): a **solo/under-rallied ~11M poke into a 660M–2,120M open-map keep** → 84% gone permanently for ~2% of theirs (**42:1 against**). That's feeding, not attrition. Don't solo-poke whales on the open map. 
4. **Defense:** stand vs solo hits (sim + reports say you win those); **bubble or ghost** any 100M+ coordinated rally — the 50% debuff cap can't save a 60×-outnumbered wall.

No re-film needed — the stats + raw_text prove all of this; battle_details would only add per-round texture. (Deeper rally-attrition + Battlefield-zeroing + ghosting/debuff mechanics under active web research 2026-07-27 → folding into §§6, 8, 11.)

---

## 13. Deep research synthesis (2026-07-27, 5 sourced web deep-dives)

Full sourced detail in scratchpad/pvp_research_{rally_zeroing,ghost_bubble,casualties_deep,defense_sources,debuff_network}.md. Distilled to what changes play:

### A. How to take a big target (validates "rally big to make small later")
- **Solo = feeding.** A losing open-map attack: YOUR troops mostly DIE (no attacker hospital — OFFICIAL Top Games), the defender's mostly WOUND and heal back. Only the FRONT layers of a huge garrison engage one march (a march is disabled at ~10% of itself wounded), so an 11M solo removes ~2% → the 42:1 disaster we measured.
- **A rally can actually WIN.** War Hall (leader's building) sets total rally capacity: L20=37,000 · L30=290,000 · **L50=72,000,000 total troops** — ~6.5× a solo 11M hit. Leader = strongest attack general + biggest War Hall + correct COUNTER type + full buff/debuff (leader's general buffs apply to the WHOLE combined march); joiners just add mass.
- **One rally rarely shrinks a whale permanently** — their losses WOUND and heal. To shrink permanently you must **overflow their hospital**: chain winning rallies back-to-back FASTER than they heal, so wounded exceed hospital capacity and spill to KILLED. It's a rally TRAIN, not one hit.
- **Decision rule:** RALLY only if (a) you can WIN the engagement, AND (b) you can chain faster than they heal OR you're in a free-heal Battlefield event, AND (c) scout (Watchtower) shows their buffs/reinforcements DOWN. Else ghost/ignore. *Solo-poking a whale is never right on the open map.*

### B. ⭐ Battlefield-event zeroing (free-heal — "how Battlefield rallies zero people")
- **Clash of Civilizations free-heal CONFIRMED:** all Main-City troops "killed" go to hospital as wounded, heal at no resource cost, and ALL auto-heal at event end. EXCLUDES traps + sub-city troops (those die) → bring troops, disable sub-city auto-defense. BoC/BoG: defense generals survive → also free-heal-class.
- → In these events **rally to ZERO enemies at no real troop cost.** Scoring: kill troops 4–280 pts per 1,000,000 (by tier); **hold Empire Turret / Rally Hall / Battlefield Hospital = 500 pts/MINUTE each (30,000/hr)**. Objective-holding is the money; zeroing clears defenders off objectives + adds kill points.
- **A defensive tank scores BEST here** (taking hits is free; every broken rally feeds kill points; free-heal; repeat) — the exact opposite of open-map SvS where those losses are permanent. This is your best mode. Loop: rally-to-zero → hold objectives → free-heal → repeat.

### C. Defend a mega-rally (my #1 loss cause) — priority BUBBLE > GHOST > reinforce
- **Bubble (Truce Agreement):** you CAN activate right up to the moment the incoming march lands → best reactive save. Bank a 3-day + 24h + ≥2,500 gems. Check the TIMER not the cached shield graphic (OFFICIAL: caching can show an expired bubble). Can't Truce while holding Throne/towers in Server War.
- **Ghost:** send EVERY troop out on 60-min rallies vs a nearby enemy KEEP (player-rally = no stamina; boss = stamina) → scouts read 0 troops. Recall returns troops INSTANTLY → keep them out until the hit lands. SvS: resign the defense general first (it dies); remove duty officers; unlink sub-cities/auto-fight off. Resources still loot — stash below cap / Alliance Warehouse / chests unopened. Chain-fire can force-teleport you home → bubble instead.
- **Detection:** max Watchtower (L8 count · L21 type · L37 their defense general · L41 reinf buffs); ~5-min staging = a real hit, longer = usually ghosting. Warning = staging left + march travel.
- **Reinforcements don't scale:** reinforcer debuffs DON'T stack (strongest only) and reinforcers can't bring sub-cities → bodies pile up, debuffs don't. Concentrate debuff on the keep owner; against a 100M+ rally, ghost/bubble.

### D. Casualty cascade (how losses actually resolve)
Raw casualties → **Survived → Wounded → Deserter → Killed**, each stage skimming off the top:
- **Survived** = "Death-into-Survival" buffs → living troops, FREE (Cimon +10%, Zhu Di +15%, War Tactics if a keep general's Leadership+Politics>900, revival research +4–6%). Cheapest win — stack it.
- **Wounded** = hospital, capped at capacity, **HIGH-TIER FILLED FIRST** (your lowest tiers die once it's full). "All killed 0 wounded" = hospital was already full/overflowed. Raise hospital capacity (Hospital Scale +50,000 / Super +150% / Supreme +50,000 / Adv Medical +100% / Thebes dragon +25–35% / SvS +50%) → directly converts Killed→Wounded.
- **Deserter** = Holy Palace, recall with Horns; overflow = permanent.
- **Killed** = permanent (SvS → Troop Souls). Watch enemy "Wounded-into-Death" debuff (forces your wounds to die).

### E. Close the debuff gap (my ONE build gap) — the sub-city network
- **Cimon is THE first acquisition** — the only mayor that debuffs both Ranged AND Siege (my worst incoming) across Atk/Def/HP. Then Baldwin IV (Ranged Atk −75% / Siege Atk −65%), then Jan Žižka (Ranged −120%) or Flavius Aetius (Siege −60%). (Yi Seong-Gye is NOT a debuffer — it's a ranged-def buff; drop it.)
- **Gear:** Achaemenidae 6-piece (−15% all-enemy attack set bonus); prioritize Fearless Leg Armor (Siege Atk) + Courageous Boots (Siege Atk) + Courageous Ring (Ranged Atk).
- **Beasts (defending-Main-City −104%):** Tarasque (enemy Siege Attack −104%) #1, Jormungandr (enemy Ranged Attack −104%) #2.
- **Stacking:** up to 9 sub-cities, your own debuffs STACK additively (target ~−600%), but the **50% cap** means you only need enough to halve the enemy's buff — over-stacking a stat is wasted.
- **⚠️ Critical:** a debuff only applies while you OWN the sub-city, the mayor is assigned, and it's not wiped. If a rival zeroes/captures a debuff sub-city, its debuff DROPS off your defense. Keep every debuff sub-city garrisoned + defended.
- **Build via Military Academy (Keep 36)** for the debuff-research nodes (Tactic Scrolls + Gold), and rank toward Regent for the 6th+ sub-city slot.

_All community-derived except where marked OFFICIAL (attacker-no-hospital; CoC free-heal; bubble-caching). Version-sensitive % should be spot-checked in-game before heavy spend. Source contradictions logged in the research files: rally-debuff stacking, Gilgamesh's debuff value, Tarasque's base type, exact hospital per-level, rally join-window/slot counts._
