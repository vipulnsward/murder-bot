# Evony Rallies — Join + Auto-Set on Bosses (Bot Reference)

For an ADB+OpenCV/OCR bot to auto-join and auto-set boss rallies. **Best find: a real OSS
reference bot** — `TungNC-echoes/auto-evony-v1` (Python+ADB+template-matching on MEmu, identical
interface to BlueStacks). Tap sequences below (`code` = its actual template names) were read from
its source and are the closest thing to a reference implementation. Tags: VERIFIED / GAME-KNOWLEDGE
/ UNCERTAIN.

## Boss taxonomy + stamina
Numbered bosses b1..b23 (weakest→strongest). **Stamina tiers:** b1–4=15, b5–10=20, b11–12=30–35,
b13–14=40, b15+=50 (global range 6–50). Anchors: Zombie b1=15/36.5K pwr; Kamaitachi b12≈89M;
Behemoth b14=40/187.7M; Typhon b17=50/551.8M; Garmr b23=4.7B.
**Event monsters = the high-value targets** (reward/stamina far higher): **Ymir** best resources
(L3 = 266,667 RSS/stamina, top in game); **Cerberus/Pan** best speedups (Cerberus L3 = 227
min/stamina); **Hydra** (Mon–Tue 08:00 server, 24h; points **once per rally**, so run many small
rallies). Pan is +408% weak to Ground; others want mounted.
**Priority = a config array by reward/stamina:** active event monsters (Ymir/Cerberus/Pan/Hydra) →
highest numbered boss you can one-round → low bosses to drain stamina.

## Rally fundamentals
- **Boss rally muster timer = 5 minutes** (VERIFIED — bot always taps `attack/5minutes`).
- **Join is loot-agnostic** — you get the chest + general XP no matter how few troops. **Join with
  1 general + 1 mounted troop** (a preset) to farm drops while preserving your army; full march only
  when the rally needs power to one-round.
- **One-round-kill rule:** turn-based; not killing in round 1 loses 10% of the march. Rallies pool
  troops to one-round high bosses. Joiners' **debuff generals** cut the boss's stats (monster-def
  debuff caps **−50%**), lowering troops the setter needs.
- **Rally Spot** (not "War Hall" — that's another game) enables rallies; its level + the leader's
  rally-size stat set max rally size. Per-level size table UNCERTAIN.

## UI flow — JOIN a rally (from the reference bot, VERIFIED order)
Boss-filtered join (`join_advanced_war_sequence`):
1. `war_button` → Alliance War/Rally list.
2. Template-match each wanted boss portrait in the list (per-boss image, thr 0.7) — only bosses in
   your `selected_bosses` array = **boss-only filter**. Swipe up/down (4s settle) to scan.
3. Find `join_button` in the region **below the matched boss row** (thr 0.75); absent = already
   joined → skip (dedupe).
4. Tap it → `doi_quan_san_co` ("preset formation") → (`chon_tuong`→`chon` = select+confirm general)
   → `hanh_quan` (March). One join per loop cycle, then re-scan. `check_and_handle_insufficient_stamina`.
- **1-troop loot-join = a saved preset**, not per-join typing → set your join preset to 1 mounted +
  a looter general (Theodora 43% double-drop / Baibars 41% / Aethelflaed 33%).
- **NOT in the reference bot (build these):** march-time/"<5min remaining" feasibility filter — OCR
  the rally countdown + boss coords, compute ETA=dist/march-speed, join only if `ETA+safety < remaining`.

## UI flow — SET/START a rally on a boss (VERIFIED order)
**Find boss:** (i) external scout feed (bot scrapes iscout.club → boss X/Y json — most reliable);
(ii) in-game Search (magnifier) by monster type+level, or the Viking list (OCR fallback);
(iii) blind coord list from config.
**Go to boss** (`attack_boss`): `attack/location` → `attack/x` (clear ×5, input X, enter) →
`attack/y` (same) → `attack/tien_hanh` (Go) → match boss portrait (per-boss folder/image, thr
0.7–0.9) → tap boss → info popup.
**Create rally** (`execute_attack_sequence`): `attack/attack` (Attack) → `attack/war` (choose
Rally) → `attack/5minutes` → `doi_quan_san_co` (preset) → `chon_tuong`→`chon` (general) →
`attack/nhap_quan` (enter troop count via `input text`) → `hanh_quan` (March). Retry loop max 7×
30s waiting for the preset panel; on insufficient stamina detect `xac_nhan` (Confirm) →
handle_insufficient_stamina.
**Weak/middle/strong presets:** reference bot uses one fixed count per boss; to rotate presets,
select the in-game saved preset slot per boss/type before `doi_quan_san_co` (e.g. Pan → ground preset).

## Generals & troops
Troops **mounted** for ~all bosses (best one-round); match weakness for type-weak event bosses.
Setter/attacker (mounted S-tier): Rostam, Marco Polo, Tishtrya, Haakon. Loot-join: Theodora/
Baibars/Aethelflaed. Debuff-join: monster-def debuffers (−50% cap). Stamina: Nathanael Greene
(−25%), Maria Theresa (−20%); Seleucus I (march speed = more rallies/hr).

## Rally-only bosses
**Alliance Boss** (every 28d, 2wk, via Event Center; solo unlimited or join rally = Individual +
Alliance score). **World Boss** (Tue–Sun, 1 of 4 types/day; treasure at HP 80/60/40/20/0% → rotate
the rally setter every ~2 thresholds).

## Bot takeaways
Reuse the reference-bot flow (swap MEmu→BlueStacks, identical). Boss-finding: external scout feed >
OCR map scan. Loot-join = preset (1 mounted + Theodora). Build the two gaps: join feasibility
filter + rotating presets. Priority = config array by reward/stamina.

Sources: evonytkrguide bosses + boss-rewards; onechilledgamer boss/event-monster/hydra/general
guides; theriagames boss DB + how-to-kill + alliance/world boss + rally-spot; **OSS reference
`github.com/TungNC-echoes/auto-evony-v1`** (rally.py, war_actions[_advanced].py, boss_attacker.py,
get_location_boss.py, boss_locations.json). Unverified: rally-size-per-level table; full muster-time
options beyond 5-min.
