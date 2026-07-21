# Evony Warfare / SvS / PvP — Strategy Reference (for defend-mode, shield & rally decisions)

Distilled from evonyguidewiki.com (SvS/PvP + Subordinate-City guides) to drive the bot's
`strategist` defend-mode and `auto_shield`/ghost/reinforce logic. Machine-readable copy:
`data/guides/warfare.jsonl` (15 objects, one per page). Cross-ref **kb/26 (auto-shield/defense)**,
**kb/24 (rallies)**, **kb/23 (gathering)**, **kb/36 (generals)**, **kb/27 (base development)**.

## Verification legend
- **Everything here is sourced from evonyguidewiki.com** (page URLs in each section + `url` of each
  JSONL record). Fetched 2026-07 via the reader-proxy (`crawl_evony.fetch`) — the site sits behind a
  JS "verifying" wall that blocks plain fetch/curl.
- `[SITE]` = stated on the source page (authoritative for game mechanics as documented there).
- `[VERIFY IN-GAME]` = confirm exact regions/labels/values on the real client before hardcoding —
  patch cadence changes numbers (site pages carry 2020–2026 update stamps; some values are dated).
- `[DERIVED]` = our inference for the bot, not a site claim.
- Skips this pass: none of substance. `sub-city-buff-list-en` live-fetch hit **HTTP 429** (rate-limit);
  its content was recovered from a prior-crawl cache and is fully captured below + in the JSONL.

## Battlefield / SvS taxonomy `[SITE]`
- **Server War (SvS)** — you score by defeating enemy troops/monsters on enemy servers. Richest
  gem/gold source: full personal-score goals = **236,250 gems**; you **cannot bubble on an enemy
  server** → ghosting is the survival tool. Targeting: use enemy-server ranking + the **"Golden Sword"**
  marker (enemy currently on YOUR server) → Locate Coordinates (Arrest Warrant) → teleport in.
- **Kill Event (KE)** = the "Kill Enemies" final stage of Monarch Competition. 3-tier personal quota
  scaled to your level (even low players complete it). Distinct from SvS (KE has extra scoring paths).
- **Battlefields** — Battle of Gaugamela (BoG), Battle of Constantinople (BoC), Chalons, and
  **Clash of Civilizations (CoC)**. In these arenas **killed main-city troops become WOUNDED, not
  dead**, resources are not plundered, and all wounded auto-heal after (traps + subcity troops
  excluded) → far safer than open-world SvS. Defense general does NOT die in BoG/BoC (does in SvS).
- **CoC** `[SITE]`: 8 servers = 8 teams, 2h, top-25 CoC-Assault players/server. 15-min entry Truce.
  Leaving is permanent (score→0). Score by **occupying buildings** (Order-of-Dawn temples/strongholds
  give server-wide ATK/DEF/HP +150%, March-Size +150%, Rally-Capacity +50%, huge occupy scores) and
  **killing troops** (per 1M, scaling Lv1=4…Lv15=280) + monsters.
- **Arctic Barbarians Invasion** `[SITE]`: pseudo-PvP vs NPC castles, solo or rally, 10 defeats/day,
  losses = wounded (wound-adjusted low) + net resource-POSITIVE; 500M personal = 189,000 gems.
  URLs: pvp-check-list-en, how-to-find-enemies-server-war-en, coc-clash-of-civilizations-en,
  what-is-kill-event-en, arctic_barbarians_invasion-en.

## Shield vs Fight vs Ghost — the defend-mode decision `[SITE]`+`[DERIVED]`
This is the core feed for `strategist` defend-mode and `auto_shield` (see kb/26 for the shield-apply
flow + gem-safety). Priority order when an incoming attack is detected:
1. **Can you bubble?** (normal map, not an enemy SvS server, not a shield-blocked event) →
   **auto_shield** (kb/26): default shortest bubble, inventory-only unless `allow_gem_purchase`.
   - Shields auto-apply for **5 minutes** after you teleport onto a server (yours or enemy). `[SITE]`
   - **Rallying a city/temple/throne DEACTIVATES your shield**; rallying a **boss monster keeps the
     shield UP** — so you can ghost-to-boss and stay bubbled simultaneously. `[SITE]`
2. **Can't bubble** (SvS enemy server; "you cannot be bubbled" events) → **GHOST**: rally ALL troops
   out on 60-min rallies so the empty keep loses ~no troops (walls/traps still take damage).
   - **Prefer rally-to-BOSS** (keeps shield up, hides troop count/type). City rally reveals your exact
     army to the enemy; if forced (BoC has no bosses) use a **non-allied** city. `[SITE]`
   - **In SvS, resign the defense general before ghosting or he DIES** (since 2021-10-03). In BoG/BoC
     he survives → may leave on. `[SITE]`
   - Turn OFF subcity "Automatic fight for other Cities" before ghosting (else subcity troops die). `[SITE]`
   - Cancelling a rally returns troops INSTANTLY (defend/attack/teleport); **cannot teleport while a
     rally is active** (cancel all first) — matches kb/26 "recall before teleport". `[SITE]`
3. **Think you can win the defense** → **counterattack**: cancel the ghost the instant you're hit and
   win on defense; optionally switch subcity auto-fight ON to add mayor debuffs. Bait play: leave a few
   troops (or one type) to look weak, recall the rest when the enemy commits. `[SITE]`
- **Sent-flying rule** `[SITE]`: even ghosted, wall HP drops; at 0 HP (or ~10 hits open-world, 3 hits
  in BoG/BoC) you teleport to a random spot and **all rallied troops return home** → bot must
  **re-ghost or teleport immediately** (enemies Arrest-Warrant-chase returned troops).
- **Verify-or-fallback** `[DERIVED]` (mirrors kb/26): if shield activation can't be confirmed and
  impact is imminent → recall + ghost; never let a failed shield silently pass.
  URLs: ghost-en, pvp-check-list-en.

## Rally & reinforce mechanics `[SITE]`
- **Rally Spot** = your **March Size** (troops per single march). Built Keep 1; Lv35 unlocks a Duty
  Officer slot for +march-size (Toyotomi Hideyoshi / Niwa Nagahide / Zhang Liang ideal).
- **War Hall** = your **Rally Capacity** (max participants your own rally accepts). Built Keep 9; each
  level needs the matching Embassy level. Hosts the **Alliance War** screen = the incoming/outgoing
  **rally + scout monitor** (same as Alliance ▸ Alliance War) → a cheap intel source for defend-mode.
  - **Correction to kb/24**: War Hall DOES exist in Evony TKR (kb/24 assumed it was another game). It
    is the rally-capacity building, distinct from the Rally Spot (march size). `[SITE]`
- Ghost rallies must be **60 min** (vs 5-min boss-kill rallies, kb/24). An unspoken alliance rule of
  "5-min = monster hunt, long = ghost" prevents allies from joining ghost rallies (their march line
  would reveal your city). Turn off rally chat notifications. `[SITE]`
  URLs: rally-spot-en, war-hall-en, ghost-en, pvp-check-list-en.

## Subordinate cities — types, buffs, defense setup `[SITE]`
Unlock Keep 11; up to **9** (Rank buffs raise the cap, e.g. Archduke +6). Real value = **Buff /
Debuff / General-EXP**; troops/gold/materials are minor (subcity troops are low-tier and **DIE, not
wound**, unless survival research/buff). Machine copy also in kb/36 (35 mayor generals).

- **Culture buffs (stack across same-culture cities; scale with rarity C/UC/EX/LG/EP)** — exact values:
  - **Battle:** Japan = Main-City Attacking (marching) Troop Attack +2/4/6/8/10% (offense);
    Russia = In-City (defending) Troop Attack +2/4/6/8/10% + Trap Attack +3/6/9/12/15% (defense);
    Arabia = Hospital Capacity +3/6/9/12/15% + Healing Speed +2/4/6/8/10%.
  - **Development:** Korea (warehouse +6…30% / gathering +3…15%), Europe (construction / monster
    general-EXP), China (main-city RSS production / training), America (subcity gold / research).
  - Same-culture stacking: **8 Russia Epic = +80% in-city attack**; 9 Japan Epic = +90% marching
    attack; 9 Korea Epic = +135% gathering. Culture is re-rollable (dev early → battle later).
  - `pvp-check-list`: switch **Culture to Japan (offense) or Russia (defense)** before a fight.
- **Two common buffs**: Training Speed +2/5/10/15/20% (needs mayor = historic general);
  **Death-into-Survival Rate +2/4/6/8/10%** (needs mayor **Leadership & Politics ≥900**) — keeps
  subcity troops alive so their debuff keeps applying.
- **Mayor = a DEBUFF historic general** (skill/equipment/specialty). Mayor buffs do NOT reach main-city
  troops; the mayor's **debuff DOES** apply whenever the subcity joins a battle, and **all mayors'
  debuffs STACK** (top players reach −600%). Add debuff Red gear (Ares/Achaemenidae) or debuff dragon
  (Norway Ridge). At Keep 33+ one subcity's Achaemenidae debuff is significant.
- **Defense setup (feeds defend-mode):** per subcity toggle **"Automatic fight for other Cities"** and
  **"Accept Reinforcements"** — ON only if confident of winning the defense; **OFF when ghosting or
  likely to lose** (else subcity troops die for nothing). To bring a subcity INTO your own attack,
  select it on the pre-march screen (linkage toggles irrelevant there). A subcity **cannot join** when:
  no mayor, subcity troops = 0, a rally, temple/battlefield-building attack, or NPC-subcity attack.
- Rarity upgrade (in-city subcity only) costs gems: UC=Keep10+5K, EX=Keep15+50K, LG=Keep20+500K,
  EP=Keep25+2.5M. Get subcities: beat an NPC subcity once (solo), rob a player's (wall→0 + 10 attacks,
  solo), or the Historic City Search event (**no bubble for 10 min after occupying via key**).
  URLs: subordinate-city-guide-en, subordinate-city-advantages-en, sub-city-buff-list-en.

## Council of State (Senate) — buff facility, but LOCKS generals `[SITE]`
Buffs from 3 sources: Military Title grade, Position level, appointed general star ≥6. 6 titles × 4
troop types = 24 positions. Appointing needs a **golden** historic general at **Star 5+** (purple can't).
**Critical for the bot:** an appointed general is **LOCKED** — it cannot march (combat/gathering), be a
defender, duty officer, or subcity mayor while appointed → don't schedule a Senate-appointed general
for defend/rally/gather tasks. Senator titles are gated behind **warfare scores** (Leading = win SvS +
Monarch Scores; Ruling = BoG personal scores; Honorary = BoC personal scores). URL: council-of-state-en.

## Pre-battle checklist (condense into a defend/attack prep macro) `[SITE]`
Before any BoG/BoC/SvS/KE: swap dev-defender → combat defender; set subcity linkages per plan
(OFF to ghost); review march presets; **use 1-hour ATK/DEF/HP/March-size buff items** (set a timer);
switch Monarch Gear + Talent presets (esp. **Lv22 Subordinate City Attack** talent) + Civilization
Treasure (Globus Cruciger=heal speed) + Blazon (mounted PvP set) + Shrine "King's Protection" +
Alliance Science "Mighty Force" + Dragon active skill + Culture (Japan/Russia). **SvS/KE only:** spend
resources first; **remove the defender if ghosting the whole army** (else he dies). URL: pvp-check-list-en.

## Bot hooks — what should feed `auto_shield` / `strategist` defend-mode `[DERIVED]`
1. **Bubble-blocked context ⇒ ghost, not shield.** If state indicates enemy-SvS-server or a
   "cannot-be-bubbled" event, `auto_shield` must fall through to **recall + 60-min ghost rally**
   (kb/26 already models this; this KB supplies the *when*). Prefer **rally-to-boss** so any residual
   shield stays up and troop counts stay hidden.
2. **Cheap incoming intel = War Hall / Alliance War screen** (rally + scout list) in addition to the
   Watchtower (kb/26). Both should arm the reactive shield/ghost timer.
3. **Defender-death guard:** before ghosting in SvS, the strategist must **resign the defense general**
   (dies since 2021-10-03); skip this in BoG/BoC. Also toggle subcity auto-fight OFF.
4. **Post-shield can't-teleport rule:** never attempt teleport while a rally/ghost is active — cancel
   rallies first (aligns with kb/26 "recall before teleport"), and 5-min auto-shield after any teleport.
5. **Sent-flying recovery:** if the keep is teleported to a random spot (HP 0 / hit-cap), immediately
   re-ghost or teleport — returned troops are exposed and get Arrest-Warrant-chased.

## Sources (evonyguidewiki.com, `/en/…-en/`)
pvp-check-list · ghost · coc-clash-of-civilizations · what-is-kill-event · how-to-find-enemies-server-war ·
how-to-gain-relics (relic-tile gathering, not warfare scoring — informational) · rally-spot · war-hall ·
contents-of-chest-battlefield-svs · battlefield-shop-item-list · arctic_barbarians_invasion ·
subordinate-city-guide · subordinate-city-advantages · sub-city-buff-list · council-of-state.
`[VERIFY IN-GAME]` any hardcoded value (bubble timers, score tables, gem amounts, buff %) against the
live client — several source pages carry dated (2020–2024) update stamps.
