# Evony Gathering / Farming — Bot Reference

For a Python+ADB+OpenCV+OCR bot. Numbers cited; unconfirmed %s marked **[VERIFY IN-GAME]** —
config should read those from the live UI, not hardcode.

## Tiles (levels & capacity)
Resource tiles: Farm(food)/Sawmill(lumber)/Quarry(stone)/Iron Mine(ore)/Gem Mine. Levels ~L1–L16;
**higher level = more resources + faster gather, and clusters toward map center (600,600)** on the
(0,0)–(1200,1200) grid. Capacity **during a Gathering event** (halve when no event):

| Tile Lv | Food/Lumber/Stone/Ore | Gem |
|---|---|---|
| 1 | 40,000 | 48 |
| 8 | 1,300,000 | 636 |
| 14 | 7,000,000 | 1,500 |
| 16 | 10,000,000 | 2,000 |

Buffs multiply what you *take home* above the pool (a L14 tile → up to ~18M with full buffs). Food
tiles aren't larger — farm accounts just over-index on Farms because troops eat food.

## March / capacity
- **Load = carry capacity**, ranked **Siege > Ground > Mounted = Ranged**. T12 load: Siege 63,
  Ground 45, Mounted/Ranged 36 (→ T16: 88/62/53). Farm marches = **siege** (most load, weak
  elsewhere). Take-home = `min(tile_remaining, Σ troop×Load × (1+load_buffs))`.
- Deploy screen **auto-fills "enough troops to empty the tile"** and shows **march time + gather
  duration** — OCR these rather than compute. Base gather rate driven by the general's **Politics**;
  exact rate **[VERIFY IN-GAME]**. Big tiles → multi-hour gathers.

## Buffs (track Yield% / Speed% / Load% separately)
**Generals (primary):** Queen Jindeok +40% world-yield/+20% alliance (best; want 1 per slot);
Shimazu +30% food/+10% spd; Gaius Marius +30% ore spd/+15% lumber-stone, +40% load specialty;
Constance I +20% yield/+20% load; Princess Lucy +15% spd; Amir Timur +100% load; Attila +75% load.
Skill books stack (e.g. Gaius 4×+45% ore).
**Gear:** Champion's set +10% spd +10% RSS (cheap standard); Transcender bow+ring +8% spd/+10%
load; Monarch **Crystal** refines per resource (Light=food/Wood=lumber/Thunder=stone/Golden=ore) [VERIFY %].
**Monarch talent:** Gathering Boost unlocks ML26, 4× = **+20%** account-wide.
**City/event:** 24h or 8h **City Gathering Speedup +50% spd**; Gathering event doubles pools; SvS
**Harvest Temple ±20% spd** (48h). Subordinate **Korea** sub-city ~+15% (scales w/ tier) [VERIFY];
alliance/academy gather nodes + beast seals exist [VERIFY %].

## UI automation flow (dispatch a gather march)
| # | Screen | Action | → |
|---|--------|--------|---|
| 1 | City | tap world-map/globe toggle (bottom-left) | World Map |
| 2 | World Map | tap **Search** (magnifier) | Search panel [MC] |
| 3 | Search | Resources tab → resource icon → set **Level** (+/−) → Search/Go | camera jumps to nearest tile |
| 4 | World Map | **tap the tile** | Tile info panel (type/level/**remaining**/coords + green button) |
| 5 | Tile panel | tap **"Gather"** (label may render "Occupy" — match by position, OCR both) | Deploy/March screen |
| 6 | Deploy | general slot → **Queen Jindeok** (game may auto-pick) | — |
| 7 | Deploy | troops auto-fill / **Max** (siege); OCR march time + gather duration | — |
| 8 | Deploy | tap **March** (green) | World Map; left-side march-queue countdown |
| 9 | — | repeat per idle slot | — |

Minimal path: tile → Gather → March (skip 6–7, game auto-selects). **Template-match** fixed
icons/buttons; **OCR** only variable text (tile level, remaining, ETAs, idle-march count).

## March slots (throughput)
Start 1, **max 6** via Academy research (Formation L6 → Adv/Super Adv Dispatch → Legion Expansion
L35) + VIP5 time item. **Idle/active detection:** left-edge queue widgets (avatar + Marching→
Gathering→Returning + ETA) vs empty "+" placeholders. **Loop = poll-and-fill:** every N s count
idle "+" slots, dispatch to fill; slot frees automatically on return (no recall for gathers).

## Priority to build toward
1. Queen Jindeok ×(slots) — biggest multiplier. 2. Champion's set (cheap +10/+10). 3. Monarch
Gathering Boost +20%. 4. Max march slots (6). 5. 24h City Speedup +50% before big runs. 6.
Resource-specific (Gaius/Shimazu + Crystal). 7. Load buffs only for clearing big tiles. 8. Korea
sub-city + alliance/research/seals [VERIFY %].

## SvS
Gathering is a **home-server** activity and continues during SvS; Harvest Temple gives ±20% spd.
Enemy-map gathering **unconfirmed — do not assume**; pause/scope-limit dispatch during teleport
windows so marches aren't stranded. [PARTIALLY UNCERTAIN]

Sources: onechilledgamer gathering guide + gathering generals + Gaius Marius; evonytkrguide
gathering; evonybuilds part-2; evonyguru Jindeok; theriagames troop-base-stats / march-slots / SvS;
evonyguidewiki troop-type; evonysmartbot search-settings (grid); BlueStacks farming guide.
