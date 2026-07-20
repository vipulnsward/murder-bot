---
title: "Evony Screen Map & Navigation Graph (kb/31) — nodes, edges, popups, ensure_home"
tags: [evony, evony-bot, navigation, screen-fsm, game-brain, adb, opencv, ocr, reference]
type: project
source: "OSS-bot code teardown (sonpiaz/4x-game-agent, Jany-M/TaskEX, TungNC-echoes/auto-evony-v1) + guide sites (evonytkrguide/onechilledgamer/theriagames/fandom/evonyguidewiki/YouTube) + in-project VERIFIED coords (kb/06, screen_fsm.py, auto_refill.py, recovery_handler.py)"
---

# Evony Screen Map & Navigation Graph (kb/31)

The unifying map that ties the feature KBs (gather kb/23, rally kb/24, monster kb/25, shield
kb/26, base-dev kb/27, daily/alliance kb/28) into one **screen graph** a bot can traverse: reach
every screen from the home city and get back. Feeds `screen_fsm.py` (extend `ANCHOR_ORDER` +
add `navigate_to`/`ensure_home`) and the `game_brain/catalog.json` label set.

## Verification legend (READ FIRST — no faked coords)
Coordinates are **1080x1920** (this project's BlueStacks resolution, per `config.py`). Honesty
markers, because most new-screen coords **cannot be confirmed without a live pass**:

- **[VERIFIED]** — confirmed live on this 1080x1920 client (from `kb/06`, `screen_fsm.py`,
  `auto_refill.py`, `recovery_handler.py`). Safe to hardcode.
- **[VERIFY IN-GAME]** — reach-path/label is from research or gameplay knowledge; the exact
  coordinate/string must be confirmed on a live frame before hardcoding.
- **[CAPTURE TEMPLATE]** — no anchor PNG exists yet; crop one from a live frame (tight, camera-
  robust) and add to `templates/`.
- **[scaled 540p]** — derived from `Jany-M/TaskEX` (540x960) by x2; verify, don't trust blindly.

**Do not blind-tap any coordinate marked [VERIFY]/[scaled]** in a gem-risky context. The gem-safe
invariant from every feature KB holds: recovery/navigation is **dismiss / back / X only**, never a
center CTA, gem-glyph button, "Instant Finish", "Buy", "Restart", or exit "Quit".

---

## Part A — How the OSS bots classify screens (FSM) + our design

Three repos read at source level (file paths cited in Sources). Bottom line: **combine
4x-game-agent's explicit FSM/state-stack + `ensure_home` skeleton with TaskEX's real
template-anchor matcher, retry-until-anchor navigation, zone-guarded popup closer, and OCR
exit-guard.** auto-evony-v1 is a linear script with no FSM — skip it except for its
language-prefixed template dirs (en/vi) and JSON map-target coords.

**sonpiaz/4x-game-agent** (`games/kingshot/state_machine.py`, `screen_analyzer.py`,
`workflow_engine.py`, `coordinate_map.py`; MIT):
- A **string-const state enum** + a `POPUP_STATES` set (`{POPUP_QUIT, POPUP_TOPUP,
  POPUP_PURCHASE, POPUP_GENERIC}`). Classifier is **decoupled** from the FSM.
- `classify_fast()` uses **cheap pixel heuristics ordered by frequency** (bottom-nav present →
  `home_city`; dark-edge/bright-center overlay ratio > 0.5 → a popup; dialog panel w/o nav →
  building menu), and only calls OCR on an `"ambiguous"` result. `_classify_popup` keys on the
  **red-button area** in the button band (`np.sum((r>150)&(r>g+50)&(r>b+50))/total > 0.02` → quit).
- A **state stack**: push the prior screen when a popup appears, pop on dismiss → the bot knows
  where it was. `screen_changed(before,after,thr=0.92)` (downscaled `matchTemplate`) verifies a
  tap did something.
- `handle_popup()` dispatches per popup type and **taps Cancel/X, never Confirm/Buy**. Coords
  come from an externalized `POPUP` dict + `scale_coords(x,y,dw,dh)` (ref 1440x2560).
- `ensure_home()` = **retry-until-anchor, never a blind back**: 6 tries; if popup → `handle_popup`;
  else tap the **per-screen exit coordinate** (back-arrow top-left for battle/hero/alliance,
  close-X for building/training/research menus); finally `_wait_for_screen("home_city")`. Every
  task runs **ensure_home → steps → ensure_home**.
- The **portable skeleton** is `games/_template/`: a `screen_anchors` dict + `_check_anchors`
  (swap its color-anchors for `cv2.matchTemplate` template-anchors and you have our FSM).

**Jany-M/TaskEX** (real ETKR bot; `utils/navigate_utils.py`, `utils/image_recognition_utils.py`;
540x960; GPL-3.0):
- **No enum** — screens are identified by **which anchor templates are present/absent**
  (Alliance-City == `explore_world_map_btn` visible; World-Map == `explore_alliance_city_btn` +
  `alliance_btn` visible; "Ideal Land" == `explore_alliance_city_btn` present but `alliance_btn`
  absent → tap back to city). Primitive: `is_template_match(gray+blur, TM_CCOEFF_NORMED, thr 0.8)`
  and `template_match_coordinates(thr 0.85)`, plus an NMS `_all` variant.
- `ensure_shared_feature_start_screen()` = TaskEX's `ensure_home`: **retry-until-anchor, max 15**,
  closing popups + safe-back each miss, **aborting after 3 consecutive exit prompts** so it never
  quits the game.
- `find_and_close_popup_via_red_x()` — HSV red-mask → centroid of the largest red contour, but
  with a **hard SAFETY ZONE GUARD: only accept the X if it's in the top-right quadrant**
  (`cx > 0.55*w and cy < 0.30*h`), then **verify the popup actually closed** (`mean(absdiff) >=
  3.0`). This is exactly "close popups but never tap the red gem button elsewhere on screen."
- `press_back_with_exit_guard()` + `_is_exit_game_prompt()` — press back, OCR the center band for
  `"exit the game"` / `"are you sure … exit"`, and if matched **tap Cancel, never Confirm**. The
  single most valuable safety idiom across all three repos.

**Our FSM = extend `screen_fsm.identify()`.** Current `ANCHOR_ORDER` (see `screen_fsm.py`) already
does the right thing: an **ordered list of `(screen, template, threshold)`**, most-specific first,
loosest (city) last. We extend it with the new anchors below. The classifier stays
template-first + OCR-title fallback (as `game_brain.record()` already does:
`screen_fsm.identify()` → `ocr_read.screen_hint()`), and we add a `POPUP_STATES` set, a per-popup
`dismiss` table, `ensure_home()`, and a route-table `navigate_to()` (Parts D-E).

---

## Part B — Screen catalog (node · anchor · reach · leave)

Node IDs are `snake_case` and extend the existing FSM labels (`city`, `barracks_radial`,
`training_idle/busy`, `resources`, `speedup_modal`, `cap_popup`, `exit_dialog`, `disconnect`).
"Anchor" = how the bot IDs the screen (existing template / [CAPTURE TEMPLATE] / OCR title text).

### Tier 0 — the hub
| node | anchor | reach from city | leave |
|---|---|---|---|
| **`city`** | template `barracks_bldg` (thr 0.60, camera-zoom sensitive) **[VERIFIED]**; OCR the **`Kxx`** Keep level tag as a second anchor **[CAPTURE]** | — (default screen) | tap a building / globe / HUD icon |

**City HUD anchors** (fixed, for building `navigate_to` waypoints):
- **Top-left:** Monarch **avatar** (→ `monarch_profile`) with **VIP badge stacked under it**. `[VERIFY ~(60,60)]`
- **Top bar:** resource counters **food · lumber · stone · ore · gems** (gold is via Keep Levy, not shown). Food amount `(200, 33)` opens the food-scoped `resources` panel **[VERIFIED]**.
- **Top-right:** **gems** cluster (→ daily-item `shop`) and the **Event Center** icon (→ `event_center`). `[VERIFY]`
- **Bottom row:** **globe/world toggle** (→ `world_map`), **Items/backpack**, **Alliance**, **Mail**, **Chat**, **More(⋯)** (holds Generals). Exact left-to-right order **[VERIFY IN-GAME]** — the guides assume players know it; the dedicated UI walkthrough video is dead.
- **Red-dot** badges flag any building/menu with a pending action → primary poll signal (kb/28 red-pixel test).

### Tier 1 — world map cluster
| node | anchor | reach | leave |
|---|---|---|---|
| **`world_map`** | `explore_alliance_city_btn` + `alliance_btn` both present (TaskEX pattern) **[CAPTURE]**; "World Map" label bottom-left | `city` → tap **globe** (bottom, right side reported) **[VERIFY]** | tap **home/castle toggle** (where globe was) → `city` **[VERIFY glyph]** |
| **`search_panel`** | magnifier panel with **Monster / Resource** (and Keep/Relic) tabs + level stepper **[CAPTURE]** | `world_map` → tap **magnifier** (left edge) **[VERIFY]** | back/X → `world_map` |
| **`coord_jump`** | X/Y input field over the map **[CAPTURE]** | `world_map` → tap the **coordinate readout at bottom-center** → type X, Y → Go **[VERIFY]** | Go recenters camera; back → `world_map` |
| **`tile_info`** | tile/monster info popup: type · level · **remaining** · coords + green action button **[CAPTURE]** | `world_map`/`search_panel` → tap a **tile/monster sprite** | X/back → `world_map` |
| **`march_deploy`** | deploy screen: general slot + troop tiers + **march time / stamina** (OCR) + green **March** **[CAPTURE]** | `tile_info` → **Gather/Occupy** (resource) or **Attack** (monster) | back → `world_map`; **March** dispatches then → `world_map` |

Feature flows already documented: gather kb/23 §"UI automation flow"; solo monster kb/25 §"UI
flow"; rally set/join kb/24 (the reference `auto-evony-v1` sequence `attack/location → x → y →
tien_hanh → boss → Attack → war → 5minutes → preset → general → March`).

### Tier 2 — building radial menus (tap a building → ring menu)
Tap opens a **ring of options**; common set: **Upgrade · Detail(s) · Help · Duty · + a
building-specific primary action**. Each building sprite is a distinct **[CAPTURE TEMPLATE]** (only
`barracks_bldg` exists today). Match the building sprite to know which radial you're in; match the
radial option icons to act.

| node | primary action | radial options (per research) | anchor |
|---|---|---|---|
| **`barracks_radial`** | **Train** (ground) | Train/View · Speed Up · Duty · Upgrade · Details | `radial_train`, `radial_speedup` **[VERIFIED]** |
| `stables_radial` / `archer_radial` / `workshop_radial` | Train (mounted / ranged / siege) | same shape as barracks | **[CAPTURE]** per building |
| **`keep_radial`** | **Upgrade · Detail · Levy · City buff · Cultures · Decorate** | `Kxx` level tag identifies the Keep | **[CAPTURE]** |
| **`academy_radial`** | **Research** | Research · Skill Books Shop · Duty(L20) · Upgrade · Details | **[CAPTURE]** |
| **`rally_spot_radial`** | **Rally / March control** (march slots/size) | Rally · Details · Upgrade · Duty(L35) | **[CAPTURE]** |
| `embassy_radial` | **Alliance Help** (Embassy hand = help all) · reinforcements | Help · Details · Upgrade | **[CAPTURE]**; the **hand icon + number badge** above it (kb/28) |
| `hospital_radial` | **Heal** wounded | Heal · Details · Upgrade | **[CAPTURE]** |
| **`watchtower_bldg`** | **Military Info** (incoming list) | opens `watchtower_list` | **[CAPTURE]**; unlocks Keep L7 |
| **`tavern_bldg`** | **Recruit** generals | Recruit · **Wheel of Fortune** · Activity · Great General Chest · Upgrade | **[CAPTURE]** |
| `market_bldg` | **Tax collect** | Tax · **Black Market** · Auction · Upgrade | **[CAPTURE]** |
| `walls_bldg` | **Patrol** (Wall Patrol 3/day, kb/28) | Patrol · Defense · Upgrade | **[CAPTURE]** |
| `shrine_bldg` | **free daily** reward / offerings | free tile (green) vs paid **offering (gems — skip)** | **[CAPTURE]** |

**Leave any radial:** tap outside the ring / back → `city`.

### Tier 3 — building sub-screens (from a radial)
| node | anchor | reach | leave | notes |
|---|---|---|---|---|
| **`training_idle`** | `train_btn_idle` + `warriors_title` (T1) **[VERIFIED]** | `barracks_radial` → Train `(179,679)` → tier icon `(135,1237)` **[VERIFIED]** | back ×2 → `city` | kb/06 |
| **`training_busy`** | `speedup_btn` **[VERIFIED]** | mid-batch | — | Speed Up → `speedup_modal` |
| **`speedup_modal`** | `modal_speedup_title` **[VERIFIED]** | tap active timer → Speed Up | X `(1010,594)` **[VERIFIED]** | **GEM-SAFE: recovery closes it; only the training loop taps Finish All `(280,1840)`** |
| `research` | research tree tabs + node states (available/locked/in-progress/maxed) **[CAPTURE]** | `academy_radial` → Research | back → `city` | kb/27; disabled while Academy upgrading |
| `duty` | general-pick panel **[CAPTURE]** | `<building>_radial` → Duty (Appoint) | back | hot-swap general; kb/27 |
| `upgrade_dialog` | level/cost/time detail + confirm **[CAPTURE]** | `<building>_radial` → Upgrade | back/Cancel | **cancel gem-fill/rent prompt**; kb/27 |
| **`resources`** | `food_1m_label` **[VERIFIED]** | `city` → tap food amount `(200,33)` **[VERIFIED]** | X `(1010,594)` **[VERIFIED]** | food-scoped; kb/06 |
| **`city_buff`** | OCR title **"City Buff"**; first card **"Truce Agreement"** w/ green timer bar | (A) `keep_radial` → **City buff**; (B) top-left status circle `(80,210)` **[scaled 540p]** | back → `city` | shows active shield countdown; kb/26 |
| `levy` | Levy collect dialog **[CAPTURE]** | `keep_radial` → **Levy** | back | **free levy only**; paid tiers = gems (kb/28) |

### Tier 4 — HUD panels (from the city HUD, not a building)
| node | anchor | reach from city | leave |
|---|---|---|---|
| **`items_inventory`** | tabbed backpack; **War tab** holds Truce Agreements, **Special tab** avatar frames **[CAPTURE]** | tap **backpack** (bottom bar) **[VERIFY]** | X/back |
| **`monarch_profile`** | Monarch gear 6 slots (**Crown/Grail/Decoration/Horn/Crystal/Staff**), VIP, Level, Talents **[CAPTURE]** | tap **avatar top-left** **[VERIFY]** | X → `city` |
| **`generals`** | "General Menu Interface": stars/beasts/gear slots; **"Enhance" button bottom-left** **[CAPTURE]** | **More(⋯)** → Generals (or side icon) **[VERIFY]** | X/back |
| **`event_center`** | tiles w/ Claim; hosts Monarch Competition, Crazy Eggs, Alliance/World Boss **[CAPTURE]** | tap **top-right event icon** **[VERIFY]** | X → `city` |
| **`mail`** | Reports/Mail; **bird icon flashes RED on incoming attack**; 6 activity tabs **[CAPTURE]** | tap **Mail/bird** (bottom bar) **[VERIFY]** | X/back; **Claim All** for rewards (kb/28) |
| **`shop`** | daily item shop / packages **[CAPTURE]** | tap **gems, top-right** **[VERIFY]** | X → `city` |
| **`black_market`** | rotating item list; **timer refresh**; gem-tagged items = skip **[CAPTURE]** | `market_bldg` → **Black Market** **[VERIFY]** | X/back |
| **`wheel_of_fortune`** | spin wheel; **100 chips/spin, 100/day free (cap 900)** **[CAPTURE]** | `tavern_bldg` → **Wheel of Fortune** | X/back; **free spin only, never gem** (kb/28) |
| **`watchtower_list`** | OCR title **"Military Info"**; incoming-march list w/ **ETA countdowns** (col layout **[VERIFY]**) | `watchtower_bldg` (Keep L7+) | X/back | kb/26 auto-shield intel |

### Tier 4b — alliance sub-screens (from `alliance`)
| node | anchor | reach | leave |
|---|---|---|---|
| **`alliance`** | "Alliance" header + roster + sub-buttons **[CAPTURE]** | tap **Alliance** (bottom bar) **[VERIFY]** | X → `city` |
| `alliance_help` | help list; or the **Embassy hand** shortcut | `alliance` → Help (or tap Embassy hand in city) | back |
| `alliance_science` | tech tree + **Donate** (resource/free vs gem tier) **[CAPTURE]** | `alliance` → Science/Research | back; **HARD stop before gem donate** (kb/28) |
| `alliance_gift` | gift chests + **Claim All** / active-point chests **[CAPTURE]** | `alliance` → Gift | back |
| `alliance_war` | ongoing **rally list** w/ Join buttons; `boss_monster_flag`/`join_button` (auto-evony-v1) **[CAPTURE]** | `alliance` → War (or `ongoing_rally_btn`) | back; kb/24 auto-join |
| `alliance_store` | spend Alliance Points (Teleports/Stamina/Speedups/**Truce**) **[CAPTURE]** | `alliance` → Store | back |

### Tier 5 — popups (interrupts) → see Part C for the dismissal table
`login_gift`, `event_popup`, `visitor_gate`, `cap_popup` (**[VERIFIED]**), `storage_full`,
`level_up`, `exit_dialog` (**[VERIFIED]**), `disconnect` (**[VERIFIED]**), stray `speedup_modal`
(**[VERIFIED]**).

---

## Part C — Popup-dismissal table (GEM-SAFE)

**Universal rule** (from 4x `handle_popup` + TaskEX `find_and_close_popup_via_red_x`): dismiss via
a **corner X (top-right quadrant only: `cx>0.55w & cy<0.30h`)** or **tap the dimmed backdrop
outside the modal**; then **verify the screen changed** (`mean(absdiff)>=3` / re-`identify`). A
button bearing a **gem/diamond glyph** or a **red center CTA** is forbidden. Never tap **Buy,
Purchase, Recharge, Go, Instant Finish, Confirm(on a spend), Restart, or exit Quit**.

| popup | anchor to detect | SAFE dismiss | NEVER tap | status |
|---|---|---|---|---|
| **`disconnect`** ("logged in elsewhere") | `disconnect_popup` template (thr 0.85) | **do NOT tap — raise `DisconnectError`**; operator/relaunch decides | Restart, Reconnect (auto) | **[VERIFIED]** — `screen_fsm.is_disconnect()` |
| **`exit_dialog`** ("exit the game?") | `exit_dialog` template; OCR "exit the game"/"are you sure…exit" | **Cancel `(360,1134)`** | **Quit/Confirm** | **[VERIFIED]** |
| **`cap_popup`** (training capacity exceeded) | `cap_popup` template | **training flow only: Confirm `(714,1134)`** (accepts adjusted qty); any *other* capacity/storage popup → **X** | typing qty (fragile); gem speedup | **[VERIFIED]** (kb/06) |
| stray **`speedup_modal`** | `modal_speedup_title` | **X `(1010,594)`** | **Finish All** from recovery (gems on stacked batches) | **[VERIFIED]** |
| **`login_gift`** / daily gift | full-screen gift w/ Claim **[CAPTURE]** | tap **Claim** (green) → **X** | premium/growth track (gems) | [VERIFY] |
| **`event_popup`** / sale offer | promo splash on launch **[CAPTURE]** | **corner X** only | center Buy/Go/gem tiles | [VERIFY] |
| **`visitor_gate`** / traveling merchant | gate/merchant modal **[CAPTURE]** | **Collect** if free, else **X** | gem-priced wares | [VERIFY] (popup itself unconfirmed) |
| **`storage_full`** / resource full | warehouse-cap modal **[CAPTURE]** | **X** | gem storage expansion | [VERIFY] |
| **`level_up`** (Keep/Monarch) | celebratory modal + reward **[CAPTURE]** | **Claim** then **X** | "next level pack" gem upsell | [VERIFY] |

**Bubble caution (bot-critical, kb/26 + Agent-3):** buying a Truce via **Keep → City Buff
activates immediately and OVERWRITES the running shield**. For deliberate shielding prefer
**`items_inventory` → War tab → Truce Agreements** so you pick duration without wasting an active
bubble.

---

## Part D — `ensure_home()` design (universal "get back to city")

Formalizes the embryo already in `auto_refill.open_resources()` (back-spam + exit-guard until
`barracks_bldg` visible), hardened with 4x's retry-until-anchor and TaskEX's abort-after-3-exit.
**Never blind-back from an unknown popup; never tap through the exit dialog.**

```python
POPUP_STATES = {"disconnect","exit_dialog","cap_popup","speedup_modal",
                "login_gift","event_popup","visitor_gate","storage_full","level_up"}
PANEL_STATES = {"resources","items_inventory","monarch_profile","event_center","mail",
                "shop","black_market","alliance","city_buff","watchtower_list","generals",
                "search_panel"}   # overlays that close with the corner X
CLOSE_X   = (1010, 594)   # [VERIFIED]
CANCEL    = (360, 1134)   # [VERIFIED] exit-dialog Cancel
CAP_OK    = (714, 1134)   # [VERIFIED] capacity Confirm (training flow only)

def press_back_with_exit_guard(screencap, tap, back):
    back()                              # adb keyevent 4
    img = screencap()
    if identify(img) == "exit_dialog":
        tap(*CANCEL, d=0.8)             # Cancel, NEVER Quit
        return "exit_prompt"
    return "back"

def ensure_home(screencap, tap, back, max_tries=15):
    """Drive the game to `city`. Raise DisconnectError (never tap it). Returns bool."""
    exit_prompts = 0
    for _ in range(max_tries):
        img = screencap()
        s = identify(img)
        if s == "city":
            return True
        if s == "disconnect":
            raise DisconnectError()                 # hard stop, operator relaunches
        if s in POPUP_STATES:
            dismiss_popup(s, img, tap)              # Part C table; Cancel/X only
            exit_prompts = 0
            continue
        if s in PANEL_STATES:
            tap(*CLOSE_X, d=0.6)                    # corner-X close
            exit_prompts = 0
            continue
        # unknown / building radial / subscreen -> guarded back
        if press_back_with_exit_guard(screencap, tap, back) == "exit_prompt":
            exit_prompts += 1
            if exit_prompts >= 3:                   # TaskEX: stop before quitting
                return False
        else:
            exit_prompts = 0
    return identify(screencap()) == "city"
```

`dismiss_popup(s, ...)` looks up the Part-C action: `exit_dialog`→Cancel, stray
`speedup_modal`/panels→CLOSE_X, `login_gift`/`level_up`→Claim-then-X, everything else→
**red-X-in-top-right-quadrant** (TaskEX `find_and_close_popup_via_red_x` + change-verify).
`disconnect` is filtered out earlier (raised). **Only the training loop** ever taps `CAP_OK` /
Finish All — `ensure_home` and recovery never do.

---

## Part E — `navigate_to(screen)` design (route table, city-rooted)

TaskEX-style: navigation is a **hand-coded route with anchor verification at each hop**, not a BFS
(the UI is small and fixed; routes are more reliable and debuggable). Every route starts by
guaranteeing the hub, then follows tap→verify steps; a failed hop retries, then falls back to
`ensure_home` and restarts the route.

```python
G  = "GLOBE"; MAG = "MAGNIFIER"; BACKPACK="BACKPACK"; ALLIANCE="ALLIANCE_BTN"
MAIL="MAIL_BTN"; AVATAR="AVATAR_TL"; GEMS="GEMS_TR"; EVENT="EVENT_TR"; MORE="MORE_BR"
# ^ all [VERIFY IN-GAME] city-HUD coords; capture once, then hardcode.

ROUTES = {
  # world cluster
  "world_map":     [("tap", G),                       ("anchor","world_map")],
  "search_panel":  [("goto","world_map"), ("tap",MAG),("anchor","search_panel")],
  "coord_jump":    [("goto","world_map"), ("tap","COORD_READOUT"), ("anchor","coord_jump")],
  # HUD panels
  "items_inventory":[("tap",BACKPACK),                ("anchor","items_inventory")],
  "monarch_profile":[("tap",AVATAR),                  ("anchor","monarch_profile")],
  "event_center":  [("tap",EVENT),                    ("anchor","event_center")],
  "mail":          [("tap",MAIL),                     ("anchor","mail")],
  "shop":          [("tap",GEMS),                     ("anchor","shop")],
  "generals":      [("tap",MORE), ("tap","GENERALS_ROW"), ("anchor","generals")],
  "resources":     [("tap",(200,33)),                 ("anchor","resources")],   # [VERIFIED]
  # alliance
  "alliance":      [("tap",ALLIANCE),                 ("anchor","alliance")],
  "alliance_help": [("goto","alliance"), ("tap","HELP_TAB"),    ("anchor","alliance_help")],
  "alliance_science":[("goto","alliance"),("tap","SCIENCE_TAB"),("anchor","alliance_science")],
  "alliance_gift": [("goto","alliance"), ("tap","GIFT_TAB"),    ("anchor","alliance_gift")],
  "alliance_war":  [("goto","alliance"), ("tap","WAR_TAB"),     ("anchor","alliance_war")],
  # buildings + subscreens (building sprite matched by template, not fixed coord)
  "keep_radial":   [("tap_bldg","keep_bldg"),         ("anchor","keep_radial")],
  "city_buff":     [("goto","keep_radial"), ("tap_opt","city_buff_opt"), ("anchor","city_buff")],
  "academy_radial":[("tap_bldg","academy_bldg"),      ("anchor","academy_radial")],
  "research":      [("goto","academy_radial"), ("tap_opt","research_opt"), ("anchor","research")],
  "barracks_radial":[("tap_bldg","barracks_bldg"),    ("anchor","barracks_radial")],  # [VERIFIED bldg]
  "training_idle": [("goto","barracks_radial"), ("tap",(179,679)), ("tap",(135,1237)),
                    ("anchor","training_idle")],       # [VERIFIED]
  "watchtower_list":[("tap_bldg","watchtower_bldg"),  ("anchor","watchtower_list")],
  "tavern":        [("tap_bldg","tavern_bldg"),       ("anchor","tavern_bldg")],
  "wheel_of_fortune":[("goto","tavern"),("tap_opt","wheel_opt"),("anchor","wheel_of_fortune")],
  "black_market":  [("tap_bldg","market_bldg"), ("tap_opt","black_market_opt"),
                    ("anchor","black_market")],
}

def navigate_to(dest, screencap, tap, back, hop_retries=3):
    ensure_home(screencap, tap, back)
    for step in _expand(ROUTES[dest]):              # ("goto",x) recurses into ROUTES[x]
        kind, arg = step
        for _ in range(hop_retries):
            img = screencap()
            if kind == "anchor":
                if identify(img) == arg: break
            elif kind == "tap":
                tap(*arg, d=1.0)
            elif kind == "tap_bldg":                 # match building sprite template, tap center
                sc, c = _match(img, arg)
                if sc >= 0.80: tap(*c, d=1.4)
            elif kind == "tap_opt":                  # match radial option / panel button template
                sc, c = _match(img, arg)
                if sc >= 0.80: tap(*c, d=1.0)
            if _dismiss_if_popup(img, tap): continue # popups can appear mid-route
        else:
            ensure_home(screencap, tap, back)        # hop failed -> reset and let caller retry
            return False
    return identify(screencap()) == dest
```

Design notes: (1) **building sprites are matched by template** (`tap_bldg`), not fixed coords, so
they survive camera pan/zoom — the one already-robust pattern (`barracks_bldg` matches ~0.95
across positions). (2) Radial options / panel buttons are matched by template (`tap_opt`) for the
same reason. (3) Popups are handled *inside* the hop loop (they interrupt any transition). (4)
Every route is **idempotent from `city`** because it starts with `ensure_home`.

---

## Part F — Anchor reliability (which screens the bot can trust today)

| tier | screens | anchor quality |
|---|---|---|
| **Solid (verified template)** | `city`, `barracks_radial`, `training_idle`, `training_busy`, `resources`, `speedup_modal`, `cap_popup`, `exit_dialog`, `disconnect` | ship-ready; already in `ANCHOR_ORDER` |
| **Good OCR-title anchor (capture/confirm)** | `city_buff` ("City Buff"), `watchtower_list` ("Military Info"), `keep_radial` (`Kxx` tag), `monarch_profile` (avatar+VIP), `event_center` (top-right icon), `mail` (red-flash bird) | template OR OCR title — high confidence, needs one capture pass |
| **Needs capture + coord verify** | `world_map`, `search_panel`, `coord_jump`, `tile_info`, `march_deploy`, `items_inventory`, `generals`, `shop`, `black_market`, `wheel_of_fortune`, `alliance` (+`help/science/gift/war/store`), `academy_radial`, `rally_spot_radial`, `stables/archer/workshop/embassy/hospital/tavern/market/walls/shrine` radials, `research/duty/upgrade_dialog/levy` | [CAPTURE TEMPLATE] + [VERIFY IN-GAME] coord before use |
| **Popups needing capture** | `login_gift`, `event_popup`, `visitor_gate`, `storage_full`, `level_up` | [CAPTURE]; fall back to top-right-quadrant red-X closer until captured |

**Screens with a genuinely unique, reliable identifier** (bot won't confuse them): `city`
(barracks sprite), the training triad (train/speedup/warriors templates), `resources`
(food_1m_label), `watchtower_list` ("Military Info" is unique text), `city_buff` ("City Buff" +
"Truce Agreement"), `disconnect`/`exit_dialog`/`cap_popup`/`speedup_modal` (existing popup
templates), `keep_radial` (`Kxx` OCR). Screens that will need **anchor combinations** (like
TaskEX's Alliance-City-vs-World-Map disambiguation) because no single template is unique: the
many building radials (all share the ring shape → must match the building sprite too), and the
alliance sub-tabs (share the alliance chrome → match the active tab highlight).

---

## Worklist to make this executable (capture pass on the live client)
1. **Capture building sprites** (one tight PNG each, default zoom): keep, academy, stables, archer,
   workshop, rally_spot, embassy, hospital, watchtower, tavern, market, walls, shrine. Add to
   `templates/`, register as `tap_bldg` targets.
2. **Capture HUD-icon coords** (city): globe, backpack, alliance, mail, avatar, gems, event,
   more(⋯) — fill the `ROUTES` `[VERIFY]` placeholders.
3. **Capture panel/popup anchors** for every [CAPTURE] node above + OCR-verify the title strings
   ("City Buff", "Military Info", "Alliance").
4. **Extend `screen_fsm.ANCHOR_ORDER`** with the new `(screen, template, thr)` rows, most-specific
   first (popups → panels → radials → city last, preserving the existing order).
5. **Add** `POPUP_STATES`, `PANEL_STATES`, `dismiss_popup`, `ensure_home`, `navigate_to` to
   `screen_fsm.py`; wire `press_back_with_exit_guard` to the existing `back()`.
6. **Record each new screen into `game_brain/catalog.json`** as you land on it (the
   `game_brain.record()` path already labels via `screen_fsm.identify()` → OCR fallback).

---

## Sources
**OSS code (read at source level):**
- sonpiaz/4x-game-agent (MIT) — `games/kingshot/state_machine.py` (GameState enum, POPUP_STATES,
  handle_popup, state-stack), `screen_analyzer.py` (classify_fast pixel heuristics + red-button
  popup test + screen_changed), `workflow_engine.py` (`ensure_home` retry-until-anchor,
  `_wait_for_screen`), `coordinate_map.py` (POPUP dict + scale_coords), `games/_template/*`
  (portable anchor skeleton). https://github.com/sonpiaz/4x-game-agent
- Jany-M/TaskEX (GPL-3.0; real ETKR, 540x960) — `utils/navigate_utils.py`
  (`ensure_shared_feature_start_screen`, `find_and_close_popup_via_red_x` w/ top-right-quadrant
  guard + change-verify, `press_back_with_exit_guard` + `_is_exit_game_prompt`),
  `utils/image_recognition_utils.py` (`is_template_match`/`template_match_coordinates[_all]`),
  `assets/540p/{dialogs,other,join_rally,bubbles}/*.png` (anchor templates),
  `features/logic/{join_rally,auto_bubble,auto_gather}.py`. https://github.com/Jany-M/TaskEX
- TungNC-echoes/auto-evony-v1 (linear, no FSM; MEmu) — `action.py`
  (`find_button_on_screen` thr 0.8, `handle_insufficient_stamina` blind sequence — anti-pattern,
  no gem guard), `boss_locations.json` (S/X/Y map targets), `images/{en,vi}/` localized templates,
  `actions/{rally,war_actions,boss_attacker,open_items_actions}.py`.
  https://github.com/TungNC-echoes/auto-evony-v1
  (Note: `evsahal/TaskEnforcerX` — the possible calibration-spreadsheet variant — could not be
  verified this session; TaskEX itself has no spreadsheet, coords are template PNGs.)

**Guide sites / UI (see kb/23-28 for feature-specific flows):** onechilledgamer beginners/
gathering/general/monarch-gear guides; theriagames keep/academy/barracks/rally-spot/dictionary/
daily-checklist/vip guides + watchtower/tavern/market stubs; evonytkrguide alliance-help + items;
evony-the-kings-return.fandom.com Keep/Truce_Agreements/Items/Profile/VIP/Resources/Regular_Events/
City_Building + evony.fandom.com Reports/Coordinates/User_Interface (via reader proxy/snippets —
Fandom & evonyguidewiki returned 402/refused, so their finer UI details are **[VERIFY IN-GAME]**);
evonyguru menu-layout-generals/monarch-interface/bubble-truce; talkandroid walkthrough
(top-left avatar, globe bottom, More menu); levelwinner beginners guide (bubble, offensive action
breaks shield); reddit r/Evony_TKR (bubble via Items→War tab; coordinate readout at map bottom);
info.topgamesinc v4.84.2 ("Military Info" alert settings); YouTube RRkH_4OCrrc (auto-search),
jzSBtQLjJ48 (Watchtower). Bottom-bar order, search-panel tab labels, and per-popup X placement are
the biggest **[VERIFY IN-GAME]** gaps (no accessible source spells them out; the dedicated UI-tour
video is dead).

**Internal:** `screen_fsm.py` (ANCHOR_ORDER, identify, DisconnectError), `auto_refill.py`
(open_resources back-spam+exit-guard, to_warriors), `recovery_handler.py` (PLAYBOOK, VLM fallback),
`game_brain.py` (record→catalog), `config.py` (1080x1920), kb/06 (verified nav coords), kb/23-28
(feature flows), kb/17 (OSS survey).
