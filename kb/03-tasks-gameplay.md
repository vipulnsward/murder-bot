---
title: "Evony — Task System, Buildings & Daily Gameplay Loop"
tags: [evony, gaming, tasks, buildings, research, alliances, reference, evony-bot]
type: reference
source: "deep web research (Fandom wiki, evonyguidewiki, simplegameguide, empirebuildacademy, bluestacks, levelwinner, onechilledgamer, opceason, packsify) — 24 sources"
---

# Evony — Task System & Daily Gameplay Loop

*Factual reference for **Evony: The King's Return** (Top Games Inc.), a mobile/PC MMO city-builder + 4X strategy game. Figures reflect the 2025–2026 client and can shift with patches/civilization.*

## 1. City Buildings
Your city ("Keep") is a grid of upgradeable buildings. Almost every building's max level is **capped at your current Keep level** — the Keep gates everything. ~33 building types.

### Core / administrative
- **Keep (Castle):** administrative heart; dictates unlocks, march slots, base power, progression tier.
- **Academy:** main research tree (economy, military, defense, medical, etc.); can't research while it upgrades.
- **Military Academy:** researches battle **Formations and Tactics**.
- **Rally Spot:** controls **march size** and rally capacity; keep at Keep level.
- **War Hall:** launch/join **rallies** (Keep 11+).
- **Embassy:** receives **alliance reinforcements** + enables Alliance Help.
- **Tavern:** recruit **generals**; hosts the **Activity/Duty** daily chests.

### Troop-training buildings (one per class)
- **Barracks → Ground**, **Stables → Mounted**, **Archer Camp → Ranged**, **Workshop → Siege**.
- **Arsenal:** upgrades troops to higher grades (~Keep 27).
- **Army Camp:** boosts training **speed and capacity**.

### Resource production
- **Farm → Food, Sawmill → Lumber, Quarry → Stone, Mine → Ore.** Gold via Market tax/levy.

### Economy / utility
- **Warehouse:** shields a portion of resources from plunder.
- **Market:** daily tax, Black Market, Auction House.
- **Forge:** crafts/refines general **equipment**.
- **Shrine:** offerings (gems) for rewards + monarch EXP; daily/weekly login gifts.
- **Art Hall / Victory Column / Pasture (Spiritual Beasts) / Holy Palace (troop revival).**

### Defensive
- **Walls, Watchtower (incoming-attack warning), Trap Factory, Archer Tower, Hospital (heals wounded), Bunker, Prison.**

### Subordinate Cities
Capturable NPC cities that grant **buffs** to your main city; have a dedicated research category.

## 2. Academy Research Tree
Always be researching — bonuses are permanent + empire-wide. Base trees: **Advancement (economy), Military, Defense, Medical Aid**; advanced trees unlock with Academy level: **Recovery (17), Military Advance (28), Defense Advance (33), Offensive/Defensive Mastery (41)**; plus **Alliance, Subordinate City, Monster/Gathering** categories. Speed research with speedups, Intellect Crown, duty officers, treasures.

## 3. Troop Training — Classes & Tiers
| Class | Building | Role | Strong | Weak |
|---|---|---|---|---|
| Ground | Barracks | frontline tank, gathering | defense, HP, load | attack, range |
| Mounted | Stables | monster/PvE, fast attack | attack, speed | defense, HP |
| Ranged | Archer Camp | PvP damage | range, attack | speed, defense, HP |
| Siege | Workshop | wall-break, gathering | range, **load**, **no food upkeep** | attack/defense/HP, slow |

- **Counter triangle:** Mounted → Ground → Ranged → Mounted; **Siege counters Ranged**. Turn order: mounted, ground, ranged, siege.
- **Tiers T1–T14/T15** (some lines extended to **T16/T17**). Tiers unlock by raising the class building (capped by Keep); high tiers need **Arsenal**. Stats scale steeply (T1 Ground = 100/300/600 atk/def/HP; T17 Mounted ≈ 10,100/6,650/18,230).
- **T1 Ground = "Warrior"** (the tier this bot mass-trains). Names vary by civilization.
- **Layering:** field every class across all tiers so cheap low-tiers absorb losses.

## 4. Resource Gathering
- Gather Food/Lumber/Stone/Ore/**Gems** from world-map **tiles**; higher tiles nearer map center. Alliance Resource Tiles inside territory.
- Dispatch a **march + general**; carry amount = troops' **load** (Siege carries most → siege-heavy gathering marches).
- Speed scales with general **Politics** + gathering skills (e.g., **Queen Jindeok** +40%). Timed events boost yield.

## 5. Monster & Boss Hunting
- **Normal monsters:** solo march. **Bosses (lvl 1–23):** alliance **rallies**; stronger nearer center.
- Turn-based: attack with one tier; first-round kill = no loss; losing ~10% of troops = lost fight. **Optimal: mounted-only, no-loss first-round kill.**
- Costs **~15–50 stamina** (refills to 100 at daily reset; +VIP/monarch talent). Rewards: **speedups**, resources, materials, monarch/general EXP, gems.

## 6. Daily / Weekly Loop
**Daily:** Shrine reward; Warehouse collect; free Tax/Levy; 3 Wall Patrols; **10 daily + 5 alliance quests → 200 gems**; up to 8 Bounty Quests; Tavern Activity/Duty points; **VIP daily chest**; **Alliance Help** (request + give); Alliance Science donation (~every 4h); Alliance Gifts; keep all marches gathering; spend stamina on monsters; **Mysterious Puzzle** (sliding tiles → gems/hourglasses); always keep a build + research running; check Black Market.
**Weekly/recurring:** World Boss (5 free hits/weekend, ~500 gems/wk); Undead/Wave events (~20 waves); Boss Monster events; **SvS / KvK / Alliance competition** events.

## 7. Alliance Activities
- **Alliance Help:** free, stacking time reductions on construction/research/healing.
- **Rallies** (War Hall): coordinated boss/city attacks; boss rallies = 1 general + few Mounted.
- **Reinforcement** (Embassy): defend teammates / receive defenders.
- **Alliance Science:** donate resources/gems → shared passive buffs.
- **Alliance Warehouse / Gifts / Shop** (truce agreements, speedups).
- **Alliance territory:** plant Banner (free, ~1h) → upgrade to **Alliance City** (≥20 members, ≥5M power; 24h to complete) → in-border buffs.

## Caveats
- Classic ladder is T1–T14/T15 but live client extends some lines to **T16/T17**.
- There is **no separate "Mysterious Realm"** — the recurring daily is the **Mysterious Puzzle**.
- Fandom pages returned HTTP 402 to the fetcher; corroborated via search + independent guide sites.

## Sources
Fandom wiki (Buildings, Rally Spot, Research, Resources, Boss Monsters, Daily Tasks, Alliances, City Building); evonyguidewiki (Academy, Troop Type, Troop Stats, Troop Upgrade, Keep Requirements, Stamina, Resources, Construction); simplegameguide (All Buildings); empirebuildacademy (Research, Defence); onechilledgamer (Boss, Gathering, Troops); bluestacks (Resource Farming, Army Guide); levelwinner (Beginner's Guide); opceason (Daily, Weekly); packsify (VIP); evonytkrguide (Alliance Help, Layering); gamersunite (Alliance City).
