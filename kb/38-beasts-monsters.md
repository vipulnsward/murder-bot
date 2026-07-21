# Beasts, Dragons & Monster/Boss Knowledge — Bot Reference (kb/38)

Strategy synthesis for the bot's monster-hunt + rally tasks, distilled from evonyguidewiki.com.
Machine-readable copy: `data/guides/pve.jsonl` (29 page records, `category:"pve"`). Extends kb/25
(solo monster/boss) and kb/24 (rallies) with sourced ladders, troop-count tables, beast/dragon
buffs, and reward targeting. Feeds `monster.MonsterPolicy` and `rally_join.RallyJoinPolicy`.

## Verification legend
- **All facts here are sourced from evonyguidewiki.com** (page URL under each section + in each JSONL
  record's `url`). Fetched 2026-07 via the reader-proxy (`crawl_evony.fetch`); the site sits behind a
  JS challenge that blocks plain fetch/curl.
- Numbers are the site's own published values. The guide **publishes Power only, never HP** — treat
  Power as a difficulty proxy, not an absolute.
- Troop counts are **buff-dependent** (research/general/equipment/gear). The table values assume a
  well-developed hunter; a bot must confirm the actual zero-wound / no-RSS-loss count in-game (the
  site's Boss Battle Simulator, or the on-screen "recommended troops").
- `[VERIFY]` = confirm on a live screenshot pass before hardcoding into a policy.

## Boss ladder (Power; permanent map bosses B1–B23)
Source: boss-power-list-en. B1 Zombie 36.5K · B2 Redcap 219K · B3 Centaur 328.5K · B4 Skeleton
Dragon 787.2K · B5 Werewolf 1.3M · B6 Manticore 2.2M · B7 Yasha 3.4M · B8 Peryton 6.5M · B9 Minotaur
9.9M · **B10 Griffin 17.9M** · B11 Ifrit 59.6M · B12 Kamaitachi 89.4M · B13 Fafnir 134.1M · B14
Behemoth 187.7M · **B15 Phoenix 262.7M** · B16 Jormungandr 394.1M · B17 Typhon 551.8M · B18 Ammit
800.1M · B19 Stymphalian Bird 1.1B · B20 Kraken 1.6B · B21 Azazel 2.6B · B22 Leviathan 3.3B · B23
Garmr 4.7B. **Botted solo sweet-spot = B10–B15** (one-round-killable, good drops, still drops beast
EXP up to B13). B16+ always take wounds.

**Event bosses** (appear only during events, higher reward/stamina) — per-level Power ladders in the
JSONL (`boss-power-list-en`). Ranges: Ymir L1–7 23.4M→1.8B · Cerberus L1–5 68.2M→1.5B · Pan L1–7
22.3M→1.8B · Hydra L1–6 84.9M→1.5B · Sphinx L1–8 12.4M→2B · Witch/Warlord L1–7 13M→1.5B ·
Golem/Lava Turtle L1–7 12.4M→1.5B · Bayard L1–5 65.5M→1.5B · Nian L1–6 · Royal Thief 13.6M · Garuda ·
Taotie · Desert Bandit 1–10. **Viking** difficulty tiers Easy/Normal/Hard/Hell (Lv1–50) + Alliance
Challenge (Icebreaker/Berserker/Chief/King 89.4M/134.1M/262.7M/1B).

**Normal monsters** (map-tile mobs, NOT bosses) Lv1–50: Robber → Kheshig (L41–45 6M–34.5M) → Takeda
Fire Cavalry (L46–50 53.4M–308.2M). These are gather/tile-clear targets, not the hunt loop.

## Combat mechanics (monster-battle-mechanics-en) — the rules the policy must respect
- **Turn-based; player strikes first and always deals damage turn 1.** Not killing in turn 1 → the
  monster hits back and wounds troops. A troop tier/type is **disabled at 10% wounded**; all disabled
  = loss.
- **Zero wounds = a one-round (turn-1) kill.** Priority order: raise **attack first**, then **troop
  count**, use **cavalry only**, use a **single tier**. Mixing tiers/types does NOT reach 0 (turn-1
  troops are always the ones wounded).
- Wound cap is 10%, but **ground-only** fights and **Monarch Talent Lv6 "Mortality"** drop it to 5%
  (Mortality roughly **halves** wounds).
- Boss: the *number* of wounds steps down as you add troops (plateaus exist). Normal monster: the
  *rate* steps down.
- Turn order: Ground before Cavalry; **Ranged only fight after ground+cav+siege are disabled** (so
  ranged rarely help and can't cut cav wounds); **Siege take damage from turn 1** (never use vs
  monsters). → Single-tier mounted is optimal for all but Pan.
- **Two-turn economy:** allowing one turn of wounds ~halves troops needed (Peryton 85k for 1-turn vs
  50k for 2-turn) but incurs wounds → hospital cost. The simulator's **"No-RSS-Loss Troops"** = the
  practical minimum that avoids a net resource loss even with wounds (use when a full zero-wound army
  isn't available).

## Troop sizing — the numbers for MonsterPolicy / rally-set (how-many-troops-defeat-boss-en)
Near-zero-wound sizing by boss power (keep → tier → cavalry count):
| Power | Keep / Tier / Count | Example bosses |
| --- | --- | --- |
| ~1.5M | k21 t8 30k | Werewolf B5 |
| ~4M | k23 t9 30k | Yasha B7, Manticore B6 |
| ~18M | k25 t10 150k | Griffin B10, Minotaur, Royal Thief, event-L1s |
| ~65M | k27 t11 500k | Ifrit B11, Ymir1, Cerberus1, event-L2s |
| ~90M | k30 t12 1.0M | Kamaitachi B12, Hydra1, Ymir2, event-L3s |
| ~160M | k32 t13 1.6M | Fafnir B13, Ymir3, Cerberus2, event-L4s |
| ~200M | k35 t13 2.2M / t14 1.6M | Behemoth B14, Hydra3 |
| ~270M | k38 t14 2.2M | Phoenix B15, Ymir4, event-L5s |
| ~400M | k39 t14 2.8M | Jormungandr B16, Ymir5, Hydra4 |
| ~550M | k40 t14 3.5M | Typhon B17 |

Per-boss zero-wound anchors: Griffin t11 150k · Ifrit t12 200k · Kamaitachi t12 990k · Fafnir t13/t14
1.6M · Behemoth t14 1.595M · Phoenix t14 2.27M @+1526%. **Higher attack buff and an against-monster
Def debuff sharply cut the count** (Ymir L3 t13 1.064M: ~12k wounded at 0 debuff → **0 wounded with
monster Def −25%**). Rally-join = 1 general + 1 mounted troop (loot-agnostic; kb/24).

## Generals, buffs & the doctrine (per how-to-kill-* pages)
**Doctrine (every normal + most event bosses): send only your single highest tier of MOUNTED cavalry,
one wave, to one-round-kill.** Buff mounted attack first, count second. This is the same rule kb/25
records; the how-to-kill pages confirm it for all 16 bosses.
- Skill books on the hunter: **Mounted Attack Against-Monster Lv4**, **Mounted Attack Lv4**, **March
  Size Lv4**.
- **Against-monster debuff** (NOT a normal debuff) reduces troops needed — Dragon Equipment Set (4);
  **monster Def debuff caps at −50%** (5× set). **In a rally, only ONE joiner needs the
  against-monster debuff — it does not stack across joiners** (matches kb/24's −50% cap note).
- Damage generals / loot-join / stamina-saver generals: see kb/25 + kb/24 (Rostam/Marco Polo/
  Tishtrya/Haakon damage; Theodora/Baibars/Aethelflaed double-drop loot-join; Nathanael Greene −25%
  stamina).

**Type-weak exceptions (do NOT use mounted):**
- **Pan** has 3 variants, each weak to a different type (`how-to-kill-pan-en` damage matrix):
  **Pan(Ranged) → attack with GROUND (408%)** · **Pan(Ground) → MOUNTED (140%)** · **Pan(Mounted) →
  RANGED (367%)** · **Siege = 50% vs all, never use.** The setter must pick the matching in-game
  troop preset per Pan variant.
- **Warlord**: in-game text says "more damage to mounted / less to ground," but testing shows
  **cavalry-only is still least-wounded** — keep mounted.
- **World Boss** (world-boss-en): vs **Bird of Hurricane → GROUND**, vs **Thunder Scorpion → RANGED**
  (they out-damage mounted); other world bosses mounted.

## Reward targeting — which monster is worth hitting for what (boss-drop-item-list-en)
Pick targets by the operator's current need:
- **Speed-ups:** Cerberus, Pan, Ymir, Griffin, Witch, Warlord, Hydra.
- **Resources:** **Ymir (best in game)**, Witch, Warlord, Royal Thief.
- **Refining stone:** Ymir, Pan, Witch, Warlord, Golem, Lava Turtle, Viking.
- **Research stone:** Viking (Hard+), Witch, Warlord, Hydra L3–4, Golem, Lava Turtle.
- **Gold / Material / Medal:** Viking (Hard+), Bayard.
- **Spiritual Beast EXP:** normal bosses Werewolf B5+ (best value Minotaur B9); event L1s.
- **General/Monarch EXP + stamina:** **Hydra** (drops chips in bulk → spin Wheel of Fortune for
  stamina).
- **Runestone / Tactic scroll:** Pan L4+. **Blazon:** Sphinx. **Source of Life:** Sphinx L4+.
- **Blood of Ares** (general ascending): event boss L3+ or normal boss L11+ — **cap 3/day from
  bosses**, ~14/day across all sources (relics 6, resource tiles L13+ 4). After the 3/day boss cap,
  switch to reward-optimal bosses.
- **Blood Crystal:** B14 Behemoth+ or event bosses ≥200M power. **Crimson Crystal / Awakening Stone**
  (beast smelt) come from Garuda + World Boss damage, not normal drops.

## Stamina (how-to-get-stamina-en) — gem-safe refill model
- **Resets to 100 at daily server reset**; VIP level + Monarch Talent Lv18 raise the recovery speed
  (passive regen confirmed — resolves the kb/25 `[VERIFY]`).
- **Free:** Tavern 25×1 three times/day at server **03:30 / 09:30 / 12:30**; events (Consuming
  Return, Crazy Egg 100×4, Lucky Apple, King's Path, Garuda Trial).
- **Gem (operator's stamina bot only):** Store 50 = 200→1,600 gems escalating · Black Market 50 = 300
  gems · Shopping Spree 50×5 = 800 gems. **Alliance Shop** (on discount) 10/50/100 = 30k/50k/100k
  Alliance points.
- **Bot rule (kb/25): stay gem-safe — hunt off the free daily reset + Tavern 25×3; pause/wait when
  stamina < cost; leave gem refills to the operator's stamina bot.**
- Per-kill stamina cost: see kb/25 (B1 15 · B10 20 · B11 30 · B12 35 · B13–15 40 · B23 50; scaling
  15–50). `[VERIFY]` B2–B9 / B16–B22.

## Spiritual Beast & Dragon — the monster-hunt buffs (spiritual-beast-en, dragon-guide-en)
- **Bird of Hurricane** (1st-gen beast, Pasture Lv11): Mounted Atk/Def/HP +52% **+ Double Items Drop
  from Monsters +26%** → **put it on the mounted hunting general** (few other double-drop sources).
  This is the single most PvE-relevant beast for the farm loop.
- **Fasolt** (Pasture dragon): the dedicated **Boss-Hunt (Mounted)** dragon — Talent II = "Mounted
  Troop Attack **on Monsters**" (an against-monster buff). The goal dragon for a mounted hunter; use
  Bird of Hurricane until you get it. Fafnir = mounted/siege alt.
- Beasts vs dragons: dragons stronger at full development but far costlier — **early game develop
  beasts first**, hold dragons until general equipment is sufficient.
- Debuff beasts/dragons (2nd/3rd gen) belong on **sub-city mayors** (their debuff reaches the battle
  when the sub-city joins; buffs don't reach the main army). Beast on assistant/duty officer = no
  buff (only power).
- Beast EXP (300k to activate a beast) farms alongside the hunt: mid normal bosses **Minotaur B9 →
  Fafnir B13 = 5,000 EXP each** (B14+ give none); Relics Chamber 100k; World Boss ranking (how-to-get-
  spiritual-beast-exp-en). Beast Scale from bosses caps **42/day**.

## World Boss (world-boss-en) — extends kb/24's world-boss note
Weekly, 48h, random map spot, type rotates (4 types). **Can never lose, zero wounded.** Ranked by
individual + alliance damage; recovers HP on relocation (deal 100% before it moves). **5 free
attacks/day** then gem chances (200/400/600/800/1000). **Treasure at HP 80/60/40/20/0%.** Damage
tuning differs: **add lower cav tiers too** (no wound penalty) and raise **Def+HP** (fight runs until
0.8% wounding, 0.4% w/ Mortality → durability = more hits = more damage). **Against-monster debuffs do
NOT work on World Boss** (only normal buffs/debuffs); max debuff reduction 250%. Rally (keep 36 +
rally-buff research) can beat solo, but sub-cities can't join a rally.

## What this changes for the bot
- **`monster.MonsterPolicy`**: seed `preferred_types` as a reward/stamina-priority array (active event
  monster → highest one-round normal boss → low bosses to drain stamina; kb/24). Add per-target
  `troop_type` (default mounted; **Pan variant + World-Boss type override**) and a `stamina_cost` +
  `min_troops`/`no_rss_loss_troops` field from the sizing table. Respect the **Blood-of-Ares 3/day**
  and **Beast-Scale 42/day** caps.
- **`rally_join.RallyJoinPolicy`**: loot-join = 1 general + 1 mounted troop; join is loot-agnostic
  (kb/24). **Hydra scores points once per rally → prefer many small rallies.** Feasibility filter
  still to build (ETA vs countdown; kb/24).

## Sources (evonyguidewiki.com /en/)
spiritual-beast-en · dragon-guide-en · dragon-cliff-en · how-to-get-spiritual-beast-exp-en ·
boss-power-list-en · boss-drop-item-list-en · how-to-get-stamina-en · how-to-get-blood-of-ares-en ·
calculator-number-of-troops-to-kill-boss-en · how-many-troops-defeat-boss-en ·
monster-battle-mechanics-en · world-boss-en · how-to-defeat-royal-thief-en · how-to-kill-{griffin,
ifrit, kamaitachi, fafnir, behemoth, phoenix, ymir, cerberus, pan, hydra, sphinx, witch, warlord,
golem, lava-turtle, bayard}-en. Cross-ref: **kb/25** (solo hunt loop, stamina costs, UI flow),
**kb/24** (rally join/set, event-monster priority, world/alliance boss). All 29 pages distilled in
`data/guides/pve.jsonl`.
