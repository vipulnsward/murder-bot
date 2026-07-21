---
title: "Evony Profile & Stats Extraction (kb/34) — reading power, troops, tech, resources by UI navigation"
tags: [evony, evony-bot, profile, stats, power, troops, academy, ocr, holo, perception, reference]
type: project
source: "Fandom ETKR wiki (Profile/Resources/Research/Generals/VIP_&_Ranks/Rally_Spot/Hospital via r.jina.ai reader proxy — direct fetch = 402) + evonyguru monarch-profile + kb/06/22/27/31 (VERIFIED coords, OCR, nav graph) + perception.py/holo_vision.py/screen_id.py/status.py source"
---

# Evony Profile & Stats Extraction (kb/34)

How an ADB/vision bot **reads player state** — power, troops, tech, buildings, resources, buffs,
generals — by navigating the same screens a human taps. This is the *read* counterpart to the
*act* KBs (base-dev kb/27, nav graph kb/31). Feeds a new `profile_stats.py` snapshot task and the
`game_brain/catalog.json` label set. **No number is invented** — every value below is tagged with
where it renders and whether OCR or Holo reads it; anything unconfirmed on the live client is a
`[VERIFY IN-GAME]` / `[CAPTURE TEMPLATE]` / `[LIVE-CAPTURE]` gap, never a hardcoded guess.

## Verification legend (READ FIRST — inherits kb/31)
Coords are **1080x1920** (this project's BlueStacks res, per `config.py`).
- **[VERIFIED]** — confirmed live on this client (from `status.py`, `kb/06`, `screen_fsm.py`).
- **[VERIFY IN-GAME]** — path/label from research or game knowledge; confirm the exact coord/string
  on a live frame before hardcoding.
- **[CAPTURE TEMPLATE]** — no anchor PNG yet; crop one from a live frame into `templates/`.
- **[LIVE-CAPTURE]** — region/row layout can only be pinned once we can screenshot the real screen
  (the whole reason this is research-only right now — client is on the disconnect screen).

**Reading is inherently gem-safe** (we only OCR, never confirm a spend). The one risk is *taps to
reach* a stat screen landing on a gem CTA — so every navigation reuses kb/31 `navigate_to` /
`ensure_home` (Cancel/X/back only, never a center CTA, "Buy", "Instant Finish", "Restart", "Quit").

---

## Part A — Stat inventory (what we can read, and where it lives)

| stat | canonical screen | nav path (from city) | where the number renders | read by |
|---|---|---|---|---|
| **Food / Lumber / Stone / Ore** | city HUD top bar (always on) | none — visible on `city` | top-bar counters L→R: food·lumber·stone·ore. Food box **`(158,10,292,62)` [VERIFIED]** (`status.py FOOD_BOX`); lumber/stone/ore step right at same y **[LIVE-CAPTURE x-offsets]** | OCR `read_number` |
| **Gems** | city HUD top bar / top-right cluster | none | rightmost of the resource cluster (or top-right) **[CAPTURE region]** | OCR `ocr_read.read_gems` (VERIFIED reads 7,794,779 @ conf 1.0, kb/22) |
| **Gold** | Keep → Levy dialog | `keep_radial` → **Levy** | levy collect amount; **gold is NOT a top-bar resource** (Fandom Resources) | OCR `read_number` |
| **VIP level** | badge under avatar (always on) | none — visible on `city` | **"just under your avatar, top-left"** (Fandom VIP&Ranks) — small `VIP xx` badge ~`(55,120)` **[CAPTURE]** | OCR `read_number` on badge crop |
| **VIP time / points** | VIP panel | tap **VIP badge** → VIP screen | remaining VIP time + points-to-next **[LIVE-CAPTURE]** | OCR + Holo `describe` |
| **Total Power (Might)** | Profile "Detail" card | **Avatar (top-left)** → **Detail (bottom-left)** | "Power Rating" line on the card (single aggregate) — evonyguru + Fandom Profile | OCR `read_number` |
| **Monarch level / Rank / Name / ID / Alliance / Culture** | Profile "Detail" card | Avatar → Detail | one field each on the card **[LIVE-CAPTURE row regions]** | OCR `read_text`/`read_number` |
| **Troops owned (T1–T15 × 4 types)** | Rally Spot troop detail (best) / any march-deploy panel | `rally_spot_radial` → **Details/Troops**; or `march_deploy` troop selection | Rally Spot "tells you the details about your troops and traps and march size" (Fandom Rally_Spot) — scrollable rows, one per type→tier, count at row-right **[LIVE-CAPTURE row grid]** | OCR per row |
| **Wounded troops** | Hospital | `hospital_radial` → **Heal** panel | wounded list by type/tier **[VERIFY]** | OCR per row |
| **Marching / away troops** | Rally Spot / March queue | `rally_spot_radial` → march list | active march cards (size per march) **[VERIFY]** | OCR per card |
| **Academy research levels** | Research tree | `academy_radial` → **Research** → tab | each node shows **level X / max**; in-progress node has a timer (kb/27) | OCR node labels + Holo `describe` state |
| **Keep level** | Keep sprite tag | none (on `city`) or `keep_radial` | **`Kxx`** tag on the Keep (kb/31 OCR anchor) | OCR `read_number` on `Kxx` |
| **Building levels** | per-building Detail | tap building → **Detail** | level line in each building's Detail dialog; small level badge on sprite **[VERIFY]** — **no single all-buildings screen** | OCR per building |
| **Active buffs** | buff icon row / City Buff | buff row on `city`; or `keep_radial` → **City buff** | active-buff icon strip (top) + City-Buff cards w/ green timer bars (kb/26/31) **[CAPTURE icons]** | Holo `describe` + OCR timers |
| **Generals** | Generals menu | **More(⋯)** → **Generals** | per-card: quality color, level, stars, 4 attrs (Leadership/Attack/Defense/Politics), power **[LIVE-CAPTURE card grid]** | OCR per card + Holo for star/quality |
| **RSS production rate** | Keep Detail | `keep_radial` → **Detail** → scroll bottom | "total RSS production" at card bottom (Fandom Resources) | OCR |

**Confirmed HUD facts** (align with kb/31 [VERIFIED] HUD notes): avatar top-left; **VIP badge stacked
under the avatar**; top-bar resource order food·lumber·stone·ore·gems; **gold not shown** (Keep Levy);
food counter opens the resources panel at `(200,33)` [VERIFIED].

---

## Part B — Per-stat extraction detail (nav → region → grounding)

### B1. Total Power / Might — *aggregate only; no native breakdown*
**Path:** `city` → tap **Avatar** (top-left, `AVATAR_TL` [VERIFY]) → **Detail** (bottom-left of the
card, [VERIFY]) → `monarch_profile`. **Number:** the "Power Rating" line (single big integer).
**The breakdown problem:** the standard ETKR client shows **one aggregate Power** — the Profile card
and rankings expose *no* decomposition into building / tech / troop / monster power. Research turned
up no "power details" screen (evonyguru's profile card lists only "Power Rating"; Fandom Profile the
same). → **A true building/tech/troop/monster split is NOT directly OCR-able.** The bot can only:
(a) read **total power** here, and (b) **reconstruct** components by reading each source screen
(sum building levels → building power, all research nodes → tech power, troop counts × per-unit power
→ troop power, generals → general power) against per-unit power tables that are **game-version
dependent** and must themselves be `[VERIFY IN-GAME]`. Treat the breakdown as *derived + estimated*,
never as a read value. (This is hardest-stat #1 — see Part E.)

### B2. Troops owned by tier & type
**Types→buildings:** ground=Barracks, mounted=Stable, ranged=Archer Camp, siege=Workshop; tiers
**T1–T15**. **Best single screen:** **Rally Spot → Details** ("tells you the details about your
troops and traps and march size", Fandom Rally_Spot) — the closest thing to a troop-inventory panel.
**Alternative:** open any **march/deploy** (gather/attack/rally) → the troop-selection panel lists
every type, each tier a row with the **count currently available at home** on the right.
**Caveat — no screen shows the TRUE total:** home-available (deploy/rally panel) **excludes** troops
**marching** (march-queue cards), **wounded** (Hospital), and **in-training** (barracks queue). A
faithful total = home + marching + wounded + training, summed per (type,tier). Subordinate-city
troops are separate again. **Read:** classify the panel, then OCR each row's count; associate the row
to its tier via the tier icon (Holo `ground`/template) since rows are icon-labeled, not text-labeled.
`[LIVE-CAPTURE]` the row-grid geometry (up to 4 types × 15 tiers = 60 cells, small fonts).

### B3. Academy research / tech levels
**Path:** `city` → tap **Academy** sprite → `academy_radial` → **Research** → tree tab. **Four trees**
(Fandom Research): **Advancement** (gather/construction/logistics — holds the Construction & Typography
nodes kb/27 prioritizes), **Defense**, **Military**, **Medical Aid**. **Number:** each node renders
**level X / max**; the single in-progress node shows a countdown timer; locked nodes show a grey
padlock + "Requires…"; maxed = "X/X" (states per kb/27). **Reading it all** = iterate 4 tabs × scroll
× OCR each node's tiny "X/Y" over ornate art, using Holo `describe` to tag available/locked/in-progress/
maxed. There is **no summary "research power" number** — completion must be aggregated node-by-node.
(Hardest-stat #3.)

### B4. Keep + building levels
**Keep level:** the **`Kxx`** tag on the Keep sprite (kb/31 OCR anchor) → `read_number`. **Other
buildings:** each shows its level; the reliable read is **tap building → Detail → level line** (per
building; **no all-buildings overview** exists — confirmed absent in Fandom City_Building). For a
bulk sweep, iterate the building sprites from kb/31's `tap_bldg` template set (keep/academy/barracks/
stable/archer/workshop/rally_spot/embassy/hospital/watchtower/tavern/market/walls/shrine), open each
Detail, OCR the level, `ensure_home` between. **Keep → Detail → scroll** also yields **total RSS
production** (Fandom Resources).

### B5. Resources, gems, VIP, buffs
- **RSS (food/lumber/stone/ore):** top-bar counters, always on `city`. Food box `[VERIFIED]`; the
  other three step right at the same y — `[LIVE-CAPTURE]` the x-offsets, then a fixed-box `read_number`
  each (mirror `status.py`'s `FOOD_BOX` + `parse_food` K/M/B suffix handling). **Protected amounts** =
  Warehouse building. **Gold** = Keep→Levy only.
- **Gems:** `ocr_read.read_gems()` already VERIFIED reliable (kb/22). `[CAPTURE]` its box.
- **VIP:** level = OCR the `VIP xx` badge under the avatar `[CAPTURE region]`; tap the badge → VIP
  panel for **VIP Time** remaining + points (Holo `describe` + OCR). VIP range 0–25 (Fandom).
- **Buffs:** active-buff **icon strip** near the top (icons, not text) → identify each via Holo
  `describe`/template `find`; durations via OCR of any timer text. The **shield/truce** specifically
  lives on the **City Buff** screen (`keep_radial` → City buff, or status circle `(80,210)` scaled-540p
  kb/31) with a green countdown bar (kb/26). `[CAPTURE]` the common buff icons.

### B6. Generals / Monarch
**Path:** `city` → **More(⋯)** → **Generals**. **Per-card:** quality by card color (Grey/Green/Blue/
Purple/Gold/Red), **Level**, **Stars** (≤5 gold, +red for Awakened), four attributes **Leadership /
Attack / Defense / Politics** (Fandom Generals). General **power** isn't on a documented HUD spot →
`[VERIFY IN-GAME]` where each card prints its power. Monarch equipment (6 gear slots
Crown/Grail/Decoration/Horn/Crystal/Staff) sits on `monarch_profile` (kb/31). Reading the roster =
iterate the scrollable general grid, OCR level/power per card, Holo for star-count + quality colour.

---

## Part C — `profile_stats.py` design (module design — NOT implemented)

Mirrors `base_dev.py`'s shape: pure dataclasses + a `make_task(perceive, navigate)` factory with
**injectable perception/navigation** and `[LIVE-CAPTURE]` guards, so the logic is testable offline and
only the screen-grounding is deferred to a clean session. Reuses the perception toolkit verbatim:
`perception.find / find_all / read_number / read_text`, `holo_vision.ground / describe`,
`screen_id.classify`, `ocr_read.read_gems`, and kb/31 `navigate_to` / `ensure_home`.

**Structured snapshot (dataclasses):**
```
TroopCell   = {type: str, tier: int, home:int, marching:int, wounded:int, training:int}
ResearchNode= {tree: str, node: str, level:int, max:int, state: str}   # avail/locked/inprog/maxed
BuildingLvl = {key: str, level:int}
General     = {name:str, quality:str, level:int, stars:int, power:int|None,
               leadership:int, attack:int, defense:int, politics:int}
Buff        = {name:str, active:bool, remaining_s:int|None}

Snapshot = {
  captured_at, keep_level,
  power_total,                     # aggregate (B1) — the ONLY trustworthy power number
  power_breakdown=None,            # derived-only; None until reconstructed (never OCR'd)
  resources={food,lumber,stone,ore,gold,gems},
  vip_level, vip_time_s,
  monarch={name,id,level,rank,alliance,culture},
  troops=[TroopCell...],           # per (type,tier); None fields where a source screen wasn't read
  research=[ResearchNode...],
  buildings=[BuildingLvl...],
  buffs=[Buff...],
  generals=[General...],
  gaps=[...],                      # every stat we could NOT ground this run (honesty ledger)
}
```

**Collector pattern.** One `perceive_<stat>(ctx) -> partial Snapshot` per stat, each: `navigate_to`
its screen → `screen_id.classify` **gate** (bail into `gaps[]` if wrong screen, never OCR blind) →
read → `ensure_home`. A top-level `read_snapshot(ctx, want=[...])` runs the requested collectors,
merges partials, and records anything ungrounded into `gaps[]`. Unwired collectors raise the same
`[LIVE-CAPTURE]` `NotImplementedError` idiom as `base_dev._not_wired`.

**Per-stat perceive steps — and OCR vs Holo split:**

| stat | perceive steps | OCR-read | Holo-grounded |
|---|---|---|---|
| **resources (RSS)** | on `city`; `read_number` each fixed box | food/lumber/stone/ore values | — (fixed boxes; no grounding) |
| **gems** | `ocr_read.read_gems` on `city` | gem count | — |
| **gold** | `navigate_to keep_radial`→Levy; OCR amount | gold | `ground` "Levy button" (no template) |
| **VIP** | OCR badge under avatar; tap badge→OCR panel | VIP level, time | `ground` VIP badge tap point |
| **power_total** | `ground` avatar→`ground` "Detail"→classify `monarch_profile`→`read_number` power line | power value, monarch level, rank | `ground` avatar + Detail; `describe` to locate the power row |
| **monarch info** | on `monarch_profile`, `read_text` each field region | name/id/rank/alliance/culture | `describe` to map fields → regions |
| **troops** | `navigate_to rally_spot`→Details (or a march-deploy); classify; scroll; OCR each row; +Hospital +march queue | per-row counts (home/wounded/marching/training) | `ground`/`find` tier icon per row → (type,tier); `describe` "which troop tier is this row" |
| **research** | `navigate_to academy_radial`→Research; for each of 4 tabs: `ground` tab → scroll → OCR each "X/Y" | node level X, max Y | `ground` each tab; `describe` node state (avail/locked/inprog/maxed) + in-progress timer |
| **keep + buildings** | OCR `Kxx`; then per building: `tap_bldg` template→Detail→OCR level | keep level, per-building level | `find` building sprite (template, kb/31); `describe` fallback if sprite missing |
| **buffs** | `find_all` known buff icons on `city`; OCR any timers; City-Buff card for shield | buff timers | `describe` "list active buff icons"; identify each icon |
| **generals** | `navigate_to generals`; per card OCR level/power/attrs; Holo stars/quality | level, power, 4 attributes | `describe` star-count + quality colour; `ground` card scroll |

**Design invariants.** (1) **classify-before-OCR** on every screen — a mis-navigated frame goes to
`gaps[]`, never yields a fabricated number. (2) **Aggregate power is a read; the breakdown is a
derivation** flagged `estimated=True` (or left `None`) — never presented as observed. (3) Numbers use
`read_number` (separator-stripping) + `status.py`'s K/M/B suffix parser for abbreviated counts.
(4) Every collector is idempotent from `city` (`ensure_home` in/out) so a partial run degrades to a
partial snapshot, not a wrong one. (5) `gaps[]` is the honesty ledger surfaced to the operator.

**[LIVE-CAPTURE] still needed (blockers for wiring):**
- *Templates:* `monarch_profile` anchor + **Detail** button; VIP badge; Rally-Spot sprite + troop-detail
  panel anchor; per **troop tier×type icon** (up to 60); Academy sprite + 4 **research-tab** anchors +
  node-state glyphs (padlock/timer/check); Generals panel anchor; the common **buff icons**; Keep sprite
  + `Kxx` crop; Hospital sprite. (Most don't exist yet — only `barracks_bldg` + training/resources/popup
  templates are VERIFIED today, kb/31 Part F.)
- *Regions:* top-bar x-offsets for lumber/stone/ore/gems (only `FOOD_BOX` is VERIFIED); VIP-badge crop;
  `monarch_profile` field boxes (power/level/rank/id); troop-panel row grid; research-node "X/Y" boxes;
  general-card sub-regions.
- *Screen labels:* add `monarch_profile`, `rally_spot_troops`, `research_tab`, `generals`, `vip_panel`,
  `city_buff` to `screen_id.SCREENS` + `screen_fsm.ANCHOR_ORDER` (kb/31 worklist).

---

## Part D — Extraction reliability (which reads the bot can trust)

| tier | stats | why |
|---|---|---|
| **Easy (single fixed box, high-conf OCR)** | RSS, gems, keep level, VIP level, total power, monarch level/rank | one number in one place; gems OCR already VERIFIED; power/level are big fonts on the profile card |
| **Medium (nav + one panel, some scroll)** | gold (Levy), buffs, RSS production, wounded troops, resources-panel detail | reachable single screen, but icon/timer reads or a Levy-dialog hop; buff icons need Holo id |
| **Hard (multi-screen aggregation / dense grids)** | troops by tier×type, academy research, all building levels, full generals roster, **power breakdown** | many rows/nodes/buildings, tab-switching + scrolling, tiny OCR, or *no source screen at all* |

---

## Part E — Top 3 hardest stats to extract reliably

1. **Power breakdown (building / tech / troop / monster power).** ETKR exposes **only an aggregate
   Power** — there is no in-client screen that decomposes it (Profile card + rankings show one number;
   no "power details" view surfaced in any source). The split can only be **reconstructed** by reading
   every contributing screen and multiplying by per-unit power tables that are **version-dependent and
   themselves unverified** — so it's an *estimate*, not a read, and error compounds across four sources.
   Total power is trivial; the breakdown is effectively not directly extractable.
2. **Full troop counts by tier (T1–T15) × type.** **No single screen holds the true total.** The
   deploy/Rally-Spot panel shows only **home-available** troops; the real total must sum **home +
   marching (march queue) + wounded (Hospital) + in-training (barracks queue)** per (type,tier) — up to
   ~60 cells across four screens, with double-counting risk, small fonts, long scrolls, and
   subordinate-city troops excluded entirely.
3. **Academy research completion.** **Four trees × dozens of nodes**, each requiring tab-switching,
   scrolling, and OCR of tiny **"X/Y"** labels on ornate node art, plus Holo state-classification
   (available/locked/in-progress/maxed) per node. High node count → slow and OCR-fragile, with **no
   summary number** to cross-check against.

*(Honorable mention — **active buffs**: purely icon-based with ticking timers, so identity needs Holo/
template matching and durations are momentary; reliable only with a captured buff-icon set.)*

---

## Worklist to make this executable (one live-capture pass)
1. Land on `monarch_profile` (Avatar→Detail); capture the card anchor + field boxes; OCR power/level/rank.
2. Capture the top-bar resource x-offsets (lumber/stone/ore/gems) relative to `FOOD_BOX`; capture VIP badge.
3. Open Rally-Spot troop details + one march-deploy panel; capture the troop row-grid + tier icons.
4. Open Academy→Research; capture the 4 tab anchors + node-state glyphs; sample OCR of "X/Y" labels.
5. Sweep building Details via kb/31 `tap_bldg` templates; capture the level-line region.
6. Open Generals; capture card grid + sub-regions. Capture the active-buff icon set + City-Buff timer.
7. Register the new screens in `screen_id.SCREENS` / `screen_fsm.ANCHOR_ORDER` and record each into
   `game_brain/catalog.json`; wire the `profile_stats.perceive_*` collectors; keep `gaps[]` as the ledger.

## Sources
**Fandom ETKR wiki** (via `r.jina.ai` reader proxy; direct fetch = HTTP 402): **Profile** (Avatar→Detail
path; card shows Name/ID/Alliance/Language/Monarch Level/Rank/**Power Rating**/Culture), **Resources**
(5 RSS + gems; gold not a resource; Keep→Detail→scroll = total RSS production; Warehouse protected),
**Research** (4 trees Advancement/Defense/Military/Medical Aid; node level X/max; gold→research-stones),
**Generals** (Tavern recruit; quality colours; level/stars; Leadership/Attack/Defense/Politics),
**VIP_&_Ranks** (VIP level 0–25 under the avatar top-left; VIP Time; ranks Knight…Regent, prestige,
weekly reset), **Rally_Spot** ("details about your troops and traps and march size"), **Hospital**
(heals wounded; Medical-Aid capacity). **evonyguru** monarch-profile (Avatar→Detail; card = Power
Rating only, no breakdown). **Internal:** `perception.py` (find/find_all/read_number/read_text/ground/
describe), `holo_vision.py` (ground/describe), `screen_id.py` (SCREENS/classify), `ocr_read` (read_gems
VERIFIED, kb/22), `status.py` (FOOD_BOX `(158,10,292,62)` VERIFIED, K/M/B parser), `base_dev.py`
(perceive/act factory + `[LIVE-CAPTURE]` idiom), kb/06 (VERIFIED coords), kb/26 (City-Buff shield),
kb/27 (Academy/research states, building levels), kb/31 (screen graph, HUD anchors, `navigate_to`/
`ensure_home`, tap_bldg templates, Part-F anchor reliability). **Biggest [VERIFY IN-GAME] gaps:** the
absence of a native power-breakdown screen, the Detail-button + avatar tap coords, top-bar resource
x-offsets, the troop row-grid/tier-icon geometry, and per-general power placement.
