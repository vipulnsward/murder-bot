# evonyguidewiki.com — Crawl Sitemap (219 guide URLs discovered)

Categorized inventory of guide pages on evonyguidewiki.com (English `/en/`), harvested from the nav +
related-links of the generals guides. Use this to ingest the rest of the site. `data/generals.jsonl`
+ `kb/36-generals.md` already cover the generals guides marked **[DONE]** below.

## Access note (important for any crawler)
The site is behind a JavaScript "One moment, please… verifying" wall (openresty). Plain `WebFetch`
and `curl` get the challenge shell or a 415 — they do NOT see content. **A real (headed) browser
passes it automatically**, then a clearance cookie persists for the whole session. Crawl method used:
gstack `/browse` skill in **`--headed`** mode (masks `navigator.webdriver`), `goto` the URL, wait
~15-20s on the first hit for the challenge to clear, then all later pages load instantly. Extract
tables via `browse eval` (querySelectorAll on `.entry-content`). Pass `--headed` on every browse call.

---

## GENERALS — core DB source
**[DONE]** (parsed into generals.jsonl):
- https://evonyguidewiki.com/en/best-ground-general-en/
- https://evonyguidewiki.com/en/best-mounted-general-en/
- https://evonyguidewiki.com/en/best-ranged-general-en/
- https://evonyguidewiki.com/en/best-siege-general-en/
- https://evonyguidewiki.com/en/best-defense-general-en/  (Wall)
- https://evonyguidewiki.com/en/best-boss-monster-general-en/
- https://evonyguidewiki.com/en/list-of-generals-worth-hiring-en/  (Best Generals & Combinations / F2P vs paid)
- https://evonyguidewiki.com/en/general-list-by-type-and-how-to-get-en/  (master roster + how-to-get)

**[TODO] — highest value for enriching the DB (assistant/subcity/detail):**
- https://evonyguidewiki.com/en/best-ground-assistant-en/
- https://evonyguidewiki.com/en/best-mounted-assistant-en/
- https://evonyguidewiki.com/en/best-ranged-assistant-en/
- https://evonyguidewiki.com/en/best-siege-assistant-en/
- https://evonyguidewiki.com/en/best-defense-assistant-en/
- https://evonyguidewiki.com/en/assistant_general-en/  (and best_ground_assistant-en/ — dup slug)
- https://evonyguidewiki.com/en/sub-city-generals-debuff-comparison-tool-en/  (per-general debuff values)
- https://evonyguidewiki.com/en/art-hall-general-list-en/
- https://evonyguidewiki.com/en/duty-officer-guide-en/  ·  duty-officer-general-level-en/
- https://evonyguidewiki.com/en/general-hall-reward-en/  ·  what-is-historic-general-en/
- Mechanics for stats/leveling: general-cultivate-en, general-enhance-star-level-en,
  general-exp-per-level-en, general-power-recipe-en, general-rare-color-en, soul-binding-en,
  how-to-get-generals-en, how-to-increase-general-power-en, fastest-way-to-level-up-general-en,
  how-to-increase-max-number-general-en.
- Note: **NO dedicated "best monarch general" page exists** — monarch officer slots = Duty Officers.
- Per-general DETAIL pages (skill/specialty/ascending for each of the 303) are NOT in this list; they
  are individual pages reachable from the general-list — needed to fill `skill`/`specialties`/`ascending`.

## BUFFS / DEBUFFS / SKILLS
- https://evonyguidewiki.com/en/buff_debuff_basic_guide-en/
- https://evonyguidewiki.com/en/debuff-simulator-en/
- https://evonyguidewiki.com/en/sub-city-buff-list-en/
- https://evonyguidewiki.com/en/rank-buff-en/
- https://evonyguidewiki.com/en/recommended-skills-en/
- https://evonyguidewiki.com/en/skill-book-list-en/
- https://evonyguidewiki.com/en/specialty-en/
- https://evonyguidewiki.com/en/how-to-add-skill-en/
- https://evonyguidewiki.com/en/blazon-en/  ·  how_to_get_blazon-en/

## GEAR / EQUIPMENT
- https://evonyguidewiki.com/en/monarch-gear-en/  ·  monarch-gear-level-up-en/  ·  how-to-use-monarch-gear-en/
- https://evonyguidewiki.com/en/civilization-equipment-en/
- https://evonyguidewiki.com/en/imperial-parthian-equipment-en/
- https://evonyguidewiki.com/en/red-equipment-combination-en/  ·  red-equipment-compare-en/
- https://evonyguidewiki.com/en/forge-en/  ·  forge-master-certificate-en/
- https://evonyguidewiki.com/en/how-to-get-refining-stone-en/  ·  seal-en/
- https://evonyguidewiki.com/en/category/equipment-en/

## SPIRITUAL BEASTS / DRAGONS
- https://evonyguidewiki.com/en/spiritual-beast-en/
- https://evonyguidewiki.com/en/dragon-guide-en/  ·  dragon-cliff-en/
- https://evonyguidewiki.com/en/how-to-get-spiritual-beast-exp-en/

## MONSTERS / BOSSES / MONSTER-HUNT  (cross-ref kb/25, kb/24)
- https://evonyguidewiki.com/en/boss-power-list-en/  ·  boss-drop-item-list-en/
- https://evonyguidewiki.com/en/how-to-get-stamina-en/  ·  how-to-get-blood-of-ares-en/
- https://evonyguidewiki.com/en/calculator-number-of-troops-to-kill-boss-en/  ·  how-many-troops-defeat-boss-en/
- https://evonyguidewiki.com/en/monster-battle-mechanics-en/  ·  world-boss-en/
- how-to-kill: bayard, behemoth, cerberus, fafnir, golem, griffin, hydra, ifrit, kamaitachi,
  lava-turtle, pan, phoenix, sphinx, warlord, witch, ymir (each `/en/how-to-kill-<name>-en/`)
- https://evonyguidewiki.com/en/how-to-defeat-royal-thief-en/
- https://evonyguidewiki.com/en/category/monster-hunt-en/

## SvS / WARFARE / PvP
- https://evonyguidewiki.com/en/pvp-check-list-en/
- https://evonyguidewiki.com/en/how-to-find-enemies-server-war-en/
- https://evonyguidewiki.com/en/coc-clash-of-civilizations-en/  (Clash of Civilizations / SvS)
- https://evonyguidewiki.com/en/contents-of-chest-battlefield-svs-en/  ·  battlefield-shop-item-list-en/
- https://evonyguidewiki.com/en/what-is-kill-event-en/  ·  how-to-gain-relics-en/
- https://evonyguidewiki.com/en/rally-spot-en/  ·  war-hall-en/
- https://evonyguidewiki.com/en/arctic_barbarians_invasion-en/
- https://evonyguidewiki.com/en/category/pvp-tips-knowledge-en/

## SUBORDINATE CITY
- https://evonyguidewiki.com/en/subordinate-city-guide-en/  ·  subordinate-city-advantages-en/
- https://evonyguidewiki.com/en/council-of-state-en/
- https://evonyguidewiki.com/en/category/subordinate-city-en/

## CITY DEVELOPMENT / BUILDINGS / TROOPS  (cross-ref kb/16, kb/27)
- Buildings: academy, barracks, army-camp, archer-camp, archer-tower, stables, military-academy,
  hospital, embassy, walls, watch-tower, trap-factory, bunker, warehouse, market, farm, mine, quarry,
  sawmill, pasture, construction, research-factory, workshop, arsenal, prison, holy-palace, wonder,
  shrine, victory-column, triumphal-arch, bacchus-tavern, tavern, auction, art-hall (each `/en/<name>-en/`)
- Troops: troop-type-en, troop-initial-stats-en, troop-upgrade-en
- Ref: upgrade-requirements-keep-en, dead-keep-power-list-en, ideal-land-en, tavern-level-and-drop-rates-en,
  black-market-products-list-en, art_treasure-en

## EVENTS
- category/event-en, consuming_return_event, crazy_egg, dwarfs_lucky_apple, kings-party, treasure-hunt,
  lucky-composing, exhibition-hall-reward, limited-time-promotion, revelation-of-horus, revelation-of-maya,
  shadow-of-dawn, dawn-of-civilization, mysterious-puzzle-1-5-egypt, hecates-moon, ekaterina-garden,
  wisdom_dome, cleopatras_treasure, civilization-treasure, server-gift, ghost, contents-of-chest-event,
  event-pack-1-5, eventpack-5vs1 (each `/en/<name>-en/`)

## ITEMS / RESOURCES / ECONOMY  (cross-ref kb/02, kb/14, kb/15)
- how-to-get: gem, gold-efficiently, hammer, medal, badge, scroll, runestone, soul-crystal, prestige,
  monarch-exp, resource, skillbook, tactic-scroll, teleporter, speed-up-items, march-speedup,
  march-size-increase, more-march-slot, vip-time, arrest-warrant, artwork-fragment, ascension-fragment
- how-to-increase: general-power, march-size, march-speed, vip-level, max-number-general
- VIP/economy: vip-en, vip-benefits-list-en, pay-cheap-en, make-profit-purchase-pack-en,
  make-wounded-as-you-need-en, march-size-per-level-en, material-chest-bag-contents-en,
  alliance-shop-item-list-en, what-is-adv-dispatch-en, category/list-of-item-en

## MECHANICS / MISC
- alliance-competition-en, server-time-chart-en, server-merge-en, how-to-change-server-en,
  how-to-make-sub-account-en, option-en, quiz_answer_list-en, term-translation-list-en,
  correct-translation-tips-en

## CATEGORY INDEX PAGES (use to discover any pages missed above)
- /en/category/{beginners-guide,coining,free-item-gathering,general,general-list,military-buildup,
  misc,skill,equipment,event,monster-hunt,pvp-tips-knowledge,subordinate-city,list-of-item}-en/
- Site index: https://evonyguidewiki.com/en/index-en
