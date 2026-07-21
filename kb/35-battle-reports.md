# Evony Battle / War Reports — Analyze + Log for Decisions (Bot Reference)

Turn the game's own after-action reports into a structured feed the bot reasons over:
PvP win/loss + losses, scout intel, monster/boss/rally results. Feeds `monster` tier
back-off (kb/25) and `auto_shield` PvP pressure (kb/26). Tags: VERIFIED (sourced) /
GAME-KNOWLEDGE (confirm on a clean session) / UNCERTAIN. `[LIVE-CAPTURE]` = needs a
screenshot pass before hardcoding regions/templates. Reports are **read-only → zero gem
risk**; this whole module never taps a spend path.

## Why (the payoff)
Reports are the only ground-truth signal of whether the bot is *winning*. A real product,
**Tactica** (tactica-ai.com), exists solely to import Evony battle reports and compute
"kill zones and casualty analysis," per-unit survival rates, and rally-contributor success
— proof that structured field extraction from these reports is both feasible and valuable.
We build the same ingest locally and wire it to our decision loops.

## 1. Where reports live + navigation
- **Entry = Mail** (envelope, top-right HUD). Classic Evony Wiki (VERIFIED): "When you click
  the **Reports** button you should see **6 tabs**. These correspond to what type of report
  has arrived," with **unread counts on the button**. TKR keeps this shape.
- **TKR mail categories** (GAME-KNOWLEDGE — `[VERIFY IN-GAME]` exact labels/order): the mail
  screen tabs across the top are roughly **Reports · Alliance · System · Personal/Chat**, and
  the military **Reports** tab itself groups by sub-type:
  - **War/Battle Reports** — PvP attack & defense, reinforcement results.
  - **Monster Reports** — solo monster/boss kills.
  - **Rally Reports** — rally (join/lead) boss & PvP results, one per rally.
  - **Scout Reports** — recon results.
  (6-tab set also carries Trade/Others/Defense in classic Evony; TKR subset `[VERIFY]`.)
- **Open list → open one:** Mail → Reports tab → tap a **row** (unread = bold + red dot) →
  full report. **Collect All / one-tap claim** exists for reward-bearing reports; **star**
  (favorite) and **delete/read-all** controls live on the list. Tap path anchors: envelope
  icon → Reports sub-tab header → report row → outcome banner → back (top-left) or delete.

## 2. Report structure / fields (how to read each)

### PvP War/Battle report (attack & defense) — server806 (VERIFIED structure)
Three layers, reached by buttons inside the report:
- **Summary page** — **outcome banner (Victory / Defeat)**, both sides' **name / alliance /
  keep coords (x,y)**, generals, and the **power exchange** (power lost by each side).
  "You want to **win the power exchange** → positive score." **Higher-tier troops = more
  points.** Reinforcements count toward the exchange.
- **Troop Buff** button — per-side attack/defense/HP **buffs & debuffs**. Caveat (VERIFIED):
  "buff values shown **do not include debuffs**," and a debuff caps at **−50% of the
  defender's buffs."
- **Battle Detail** button — **per-tier, turn-based** breakdown (one layer hits one layer per
  turn); shows each tier's engaged counts and casualties. This is where the loss numbers live.
- **Troop-outcome split per side** (GAME-KNOWLEDGE — `[VERIFY]` exact labels): troops
  **sent/dispatched** → **Surviving/Remaining · Wounded · Dead**, plus **Killed** (enemy losses
  you caused). **Attacker dead are gone; wounded route to Hospital** (heal up to capacity;
  overflow dies). Buffs shift the split: enemy **wounded→dead** and your **dead→survived**
  (theriagames, topgames). **Plunder** (resources looted: food/wood/stone/ore/gold, sometimes
  gems) appears on a successful attack.
- **Read outcome robustly:** template-match the colored **Victory/Defeat banner** AND
  cross-check `own.power_lost` vs `enemy.power_lost` — never trust one signal.

### Scout report — evonyguru + Evony Wiki (VERIFIED)
Recon of a target keep. Fields: **enemy troop types + quantities**, **wall level + trap
count**, **Resource Overview** (lootable food/wood/stone/ore/gold), and **possible alliance
reinforcements**. Detail quality scales with **scout success + your informatics/Watchtower
level + scouting hero intelligence** (Wiki) — a weak scout returns partial data, so parsing
must tolerate missing fields. Buffs usually **not** shown unless high info.

### Monster / Boss & Rally reports — onechilledgamer, packsify (VERIFIED)
- **Solo monster/boss:** turn-based, **one-round-kill** goal; losing **10% of troops = you
  lose** the round. Fields: outcome, **damage dealt**, own **wounded/dead**, and **rewards**
  — speedups, resources, **prestige**, **Monarch/General EXP**, **alliance honor**, a
  level-tagged **boss chest + drops** (**general fragments = the prize**).
- **Rally (join or lead):** report lists **participants** and distributes **rewards by damage
  contribution** — so the report/ranking carries **per-member name + damage (and its % share)**.
  One rally = one report (Hydra-style: points once per rally, kb/24).
- **World/Alliance boss:** **individual + alliance damage rankings**; **treasure chests at HP
  80/60/40/20/0%** to whoever dealt damage at each threshold (≤2×/day). Rank = single/total
  damage.

## 3. Extraction approach (template + OCR + Holo mix)
Reports are **fixed-layout grids of icon+number** → structured-region OCR is the workhorse;
Holo is the fallback for variable/unknown bits.
1. **Route:** `screen_id.classify(img)` confirms a report screen (the `mail` label already
   keys on "battle report"; add report sub-labels). Then **template-match the header/type
   icon** (crossed-swords = battle, eye/magnifier = scout, monster portrait = monster, rally
   flag = rally) to pick a parser.
2. **Numbers:** `perception.read_number(img, box)` on **fixed boxes** for the big fields —
   troops sent / survived / wounded / dead / power-lost, per side, per tier row. Grids are
   stable, so region OCR is reliable and cheap.
3. **Text:** `perception.read_text(img, box)` for names, alliance, **coords (x,y)**, keep
   level, and the outcome word.
4. **Outcome:** `perception.find(img, "victory_banner"|"defeat_banner")` (colored template)
   **plus** the power-lost comparison — belt and suspenders.
5. **Icon+number pairing:** `perception.find_all(img, troop_tier_icon)` to locate each tier
   row, then `read_number` on the count to its right; same for resource icons in plunder/loot.
6. **Variable lists (rally participants):** row-template + per-row OCR, **swipe to page**;
   when rows are irregular, `perception.describe(img, "list each participant and their
   damage")` / `ground` as the Holo fallback (kb/29).
7. **Unknown layout / low confidence:** `holo_vision.describe(img, "who won, and how many
   troops died on each side?")` to salvage a record rather than dropping it.
8. Keep the **raw OCR dump** on every record for offline re-parse when regions change.

## 4. Design — `battle_reports.py` (schema + task + decision hooks; NO code yet)
Mirrors the house pattern (kb/25/26): pure-logic parsing/policy ships + unit-tests now;
`perceive`/`act` are injected `[LIVE-CAPTURE]` stubs that raise loudly until wired.

**Store** = append-only **`battle_reports.jsonl`** (one JSON record per line — same pattern as
orchestrator's `llm_decisions.jsonl`); `store.append(record)` + `store.since(ts)` /
`store.by_kind(kind)` readers. Dedupe on `report_id` so re-reads don't double-log.

**Record schema** (`@dataclass`, `to_dict()` → the jsonl line):
```
SideLosses:   troops_sent:int  survived:int  wounded:int  dead:int
              power_lost:int    kills:int                       # kills = enemy killed
Target:       name:str  alliance:str  coords:(x,y)|None  keep_level:int|None
BattleReport:
  report_id : str        # in-game mail id if OCR-able else hash(ts,kind,target,power)
  ts        : float      # report's own time if parsed, else time.time()
  kind      : str        # pvp_attack|pvp_defense|reinforce|scout|monster|boss_rally|unknown
  outcome   : str        # win|loss|draw|scouted|n/a
  target    : Target
  own       : SideLosses
  enemy     : SideLosses|None
  plunder   : dict       # {food,wood,stone,ore,gold,gems?}         PvP loot
  rewards   : dict       # {items:[{name,qty}], exp, honor, fragments:[...], resources:{...}}
  monster   : dict|None  # {type, level, damage_dealt}
  participants: list     # rally: [{name, damage, contribution_pct, troops}]
  scout     : dict|None  # {troops:{type:count}, wall_level, traps:{type:count},
                         #  resources:{...}, reinforcements:bool}
  confidence: float      # parse confidence (region-hit ratio); low → keep raw for re-parse
  raw_text  : str        # full OCR dump (audit / offline re-parse)
```

**Task** — `make_task(perceive, parse, mark_read, policy, store, notify)` → `run(ctx)`:
`open Mail → Reports tab → find unread rows (red-dot/bold, capped N/tick for humanization) →
for each: open → img=ctx.screencap() → rec=parse(img) → store.append(rec) → policy.observe(rec)
→ mark_read → back`. Idempotent via `report_id`; on parse `confidence < τ` still log raw +
`notify(...,"info")` for later review. Never deletes reward-bearing reports before **Collect
All**.

**Summary + decision hooks** (`ReportPolicy` — pure logic, testable):
- `observe(rec)` — fold a record into rolling counters.
- `summarize()` → `{kd_ratio, plunder_total, own_losses_total, wins, losses,
  attacks_incoming_1h, per_monster_loss_rate}`.
- **Monster back-off** (feeds kb/25 `MonsterPolicy.max_level`): per `(monster.type, level)`
  track mean `dead+wounded / troops_sent` over last K reports; if `> loss_threshold`
  (e.g. 5%) → `monster_backoff(type)` returns a **lowered max_level** → bot drops a tier.
  Zero-wound doctrine means any sustained wounding is the alarm.
- **PvP pressure** (feeds kb/26 `auto_shield`): count `pvp_defense`/incoming in a sliding
  window; **≥ threshold from any attacker (or repeat from one) → `pvp_pressure()` returns
  `recommend_shield=True`** → orchestrator raises `auto_shield` to proactive + `notify(...,
  "alert")`. Repeated hits on the same coords also hint "relocate" (Advanced Teleport, kb/26).
- **Scout-feed** (feeds attack targeting): expose `last_scout(coords)` so an offense task
  reads enemy troop/wall/trap/resource before committing (evonyguru "assess viability").

## 5. `[LIVE-CAPTURE]` needs (clean-session capture list)
- **Templates:** envelope/Mail icon; the Reports sub-tab headers (War/Monster/Rally/Scout);
  unread **red-dot / bold-row** marker; report-type header icons (swords / eye / monster
  portrait / rally flag); **Victory** + **Defeat** banners; troop-**tier icons** (T1–T15);
  **resource icons** (food/wood/stone/ore/gold/gems); **Collect All / claim**, star, delete,
  back.
- **Regions** (recalibrate at device res, 1080×1920 or 540×960): outcome-banner box; per-side
  **power-lost** boxes; the **troop-outcome grid** (rows=tiers × cols=sent/survived/wounded/
  dead) for own + enemy; **plunder** box; **rewards list** box; target **name/alliance/coords/
  keep-level** box; **monster type+level+damage** box; **rally participant rows** region +
  **damage** column; scroll bounds for long lists.
- **Samples:** one screenshot of each report type (pvp win, pvp loss, incoming-defense, scout,
  solo-monster, rally, world-boss) to freeze regions and validate the parser end-to-end, plus
  the exact TKR mail-tab labels/order (the one `[VERIFY]` this research couldn't pin remotely).

## Sources
Evony Wiki / fandom **Reports** ("6 tabs", unread counts) + **Scout report** (info scales
with scout success/informatics/hero intel); **server806.com/post/how-to-read-battle-reports**
(Summary power-exchange + Troop-Buff + Battle-Detail structure, higher-tier=more points,
−50% debuff cap); **evonyguru.com** scout (troops/wall/traps/resource-overview/reinforcements)
+ rallies; **theriagames.com** buffs-debuffs (wounded→dead, dead→survived); **topgamesinc**
support (casualty mechanics); **onechilledgamer.com** boss guide (one-round-kill, 10%-loss,
reward set); **packsify.com** world-boss (individual+alliance damage ranking, HP-threshold
treasure); **blog.evonytools.com** alliance-boss (rewards by damage contribution);
**Tactica — tactica-ai.com** (real battle-report ingest/analytics: kill zones, casualty
analysis, per-unit survival, rally-contributor success, sortable by participant/troop/level,
date archive — validates the extraction design). Cross-refs kb/24 (rallies), kb/25 (monster),
kb/26 (auto-shield), kb/29 (Holo), kb/31 (screen map). `[VERIFY IN-GAME]`: exact TKR mail-tab
names/order, the troop-state labels (Surviving/Wounded/Dead), and all pixel regions —
web guides describe strategy, not UI coordinates. (Fandom/Reddit/web.archive blocked this
session; structure cross-confirmed via server806 + DuckDuckGo snippets of the Wiki.)
