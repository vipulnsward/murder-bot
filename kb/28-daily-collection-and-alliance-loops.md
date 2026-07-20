# Daily Collection & Alliance Loops — Bot Automation Reference (kb/28)

The "runs all day unattended" free-collection layer: every repeatable daily freebie + alliance
loop a bot should sweep. Two new bot tasks fall out of this: **`daily_collect`** (poll red dots →
claim personal freebies) and **`alliance`** (help + donate + gifts). Both are **red-dot-driven**:
detect a badge → open → claim → verify → move on. **GEM-SAFE is the hard invariant — never spend a
single gem** (never buy hammers/spins/offerings/VIP/stamina; stop tech donation before the gem
tier). Tags: **[BOT]** fully automatable · **[semi]** action automates, edge cases manual ·
**[MAN]** leave to human. `[VERIFY IN-GAME]` / `[CAPTURE TEMPLATE]` = confirm on the real 540p
BlueStacks client before hardcoding coords/thresholds. Numbers cross-referenced to kb/03 §6-7 and
kb/16 (prior cited research) are marked `[kb]`; single-sourced or memory numbers are `[VERIFY]`.

---

## The detection engine (shared by every loop below)

Three primitives, all lifted from OSS bots we already surveyed (kb/17):

1. **Red-dot / badge = template-free red-pixel-area test in an ROI.** From
   `sonpiaz/4x-game-agent` `screen_analyzer.py`: `red = np.sum((r>150)&(r>g+50)&(r>b+50));
   present = red/total > 0.02`. Run this on a small ROI at each nav-icon's top-right corner. A
   red dot (often with a white number) = "something claimable here." **This is the primary poll
   signal** — cheaper and more robust than a per-reward template. `[CAPTURE TEMPLATE]` the exact
   badge to tune the 0.02 threshold + ROI boxes per icon.
2. **Available-vs-claimed = two-state toggle templates.** From `Jany-M/TaskEX` assets
   (`idle_checked.png`/`idle_unchecked.png`, `favorite_checked.png`/`favorite_unchecked.png`):
   a claimable button is bright/colored; a claimed one is greyed/checked or gone. Match both;
   pick the higher-confidence state. Claim buttons in Evony are **green**; **red buttons = spend
   gems / cancel** (screen_analyzer's `_classify_popup` keys on red-button area) → **never tap
   red**. `[CAPTURE TEMPLATE]` `claim_btn_green`, `claimed_grey`, `gem_cost_red`.
3. **Named-button click + confirm chain + verify.** From `TungNC-echoes/auto-evony-v1`:
   `find_and_click_button(name, threshold≈0.65)` → look for the follow-up confirm →
   re-screenshot + re-classify to confirm the reward toast/state change (4x's rule: "workflows
   must verify screen type at checkpoints"). For opening reward boxes, its item flow is a fixed
   sequence `open → use` (`open_items_actions.py ITEM_ACTION_SEQUENCE`).

Cadence: schedule with the ALAS-style `next_run`+`SuccessInterval` queue from kb/17 — most of these
reset at **daily server reset**; a few refresh on a cooldown (tax/levy/help). Don't busy-poll; wake
on the schedule, then poll red dots.

---

## (1) Daily Activity / Activeness points — the 145 chest  **[semi]**
- **Reward:** milestone chests along an activeness bar; the top chest (framed as **145** in the
  brief) can drop a **Key of Conscription → epic gold-general fragment** `[kb/16]`. Lower
  milestones give speedups/resources/gems. **Cadence:** daily reset.
- **Points come from doing the other loops** — gather dispatch, monster/boss kills, building,
  training, using items, completing quests `[kb/16]`. So the bot **earns points as a side effect**
  of `daily_collect` + the gather/rally tasks; it only needs to **claim the milestone chests**.
- **UI flow:** open the **Quests / Daily** panel (bar with milestone chest icons; brief calls it
  the **Tavern** activity chest `[VERIFY]` exact location — Quests panel vs Tavern) → each reached
  milestone shows a **glowing chest + red dot** → tap chest → claim toast → verify dot cleared.
- **Detect:** red dot on the Quests/Tavern nav icon; per-milestone = `claim_btn_green` present
  (reached) vs greyed lock (not yet) vs empty slot (already claimed). Loop all milestones L→R.
- **GEM-SAFE:** claiming is free; do not buy the premium/growth activeness track with gems.

## (2) Daily Quests — 10 personal + 5 alliance (~200 gems)  **[BOT]**
- **Reward:** ~**200 gems/day** across 10 personal + 5 alliance quests `[kb/03, kb/16]`, plus a
  full-completion chest. **Cadence:** daily reset.
- **UI flow:** Quests panel → **Daily** tab → each completed quest row has a green **Claim** →
  tap each; then the **completion/activeness chest** at the bar's end → Claim. Repeat on the
  **Alliance** sub-tab (5 rows).
- **Detect:** red dot on Quests icon → `find_all(claim_btn_green)` down the list, tap each top-to-
  bottom, re-screenshot until no green Claim remains. Greyed row = in-progress (skip); vanished
  row = claimed.
- **GEM-SAFE:** pure claim; no spend.

## (3) Wheel of Fortune (Tavern) — free daily spin  **[semi]**
- **Reward:** generals/gems/resources/speedups. **Cadence:** ≥1 **free spin/day**; a discounted
  bulk pull at a coin threshold — kb/16 says **save to the 900-coin pull** rather than single-
  spinning `[kb/16]`. Single spins otherwise cost **gems** `[VERIFY]` cost.
- **UI flow:** Tavern → **Wheel of Fortune** → if a **"Free" spin badge** is present, tap **Spin**
  → animation → claim. Stop.
- **Detect:** template `free_spin_badge` present vs a **gem-price label** on the spin button. Only
  tap when the free badge shows; if the button shows a gem cost → **abort** (gem-safe).
- **GEM-SAFE:** **free daily spin only; never gem-spin.** Bulk-pull only if funded by free Wheel
  coins, never gems. Treat as **[semi]** — verify the free-vs-gem button state carefully.

## (4) Wall Patrol — 3 free/day  **[BOT]**
- **Reward:** gear packages (**Crown / Staff / Decoration / Grail / Horn / Crystal**, incl. L3
  Crown) + **Material Chests**, drop rates ~**1.92%–7.04%** per attempt; **3 free patrols/day**,
  resets daily `[theriagames walls-guide]`.
- **UI flow:** tap **Walls** building → **Patrol** → **Patrol** (consumes 1 of 3) → reward pops →
  claim/close → repeat until the "0/3 remaining" state.
- **Detect:** red dot on Walls; OCR/template the **"x/3" counter**; loop the Patrol button while
  count > 0. Exhausted = greyed Patrol or "0/3".
- **GEM-SAFE:** don't buy extra patrols with gems; stop at 3.

## (5) Bounty Quests — up to 8/day  **[semi]**
- **Reward:** gold/resources/EXP; **8/day** `[kb/03, kb/16]`. Some bounties dispatch a general for
  a timed run (like a mini-gather); others insta-complete. **Cadence:** daily, slots refill.
- **UI flow:** open **Bounty Quests** (Tavern/Quests area `[VERIFY]` location) → **Accept** a
  bounty (auto-assigns a general) → it runs on a timer → **Claim** on completion → refill the slot.
- **Detect:** red dot on the Bounty icon; per-slot state = **Accept** (green, available) / running
  timer (OCR) / **Claim** (done). Loop: claim done → accept new → until 8 used or slots empty.
- **GEM-SAFE:** don't gem-refresh the bounty list or gem-instant a bounty timer. **[semi]** because
  it ties up a general slot — gate it so it doesn't steal a gather march.

## (6) Free Tax / Free Levy / Warehouse & base-resource sweep  **[BOT]**
- **Free Tax:** **Market** accrues gold; a **free collect** on a cooldown → tap Market → **Tax** →
  Collect. **Free Levy:** **Keep/Monarch** grants a **free levy** of resources/gold (extra levies
  cost gems) → **take the free one only** `[VERIFY]` cadence. **Warehouse:** collect produced +
  protected resources; plus **sweep-tap the base** for floating resource bubbles (4x's "auto-
  collect resources = sweep-tap base"). **Cadence:** tax/levy ~cooldown; base bubbles continuous.
- **UI flow:** Market → Tax → Collect · Keep → Levy → (free option only) → Collect · then a
  **grid sweep-tap** over the city to pop floating resource/gold/EXP bubbles.
- **Detect:** red dot / glowing coin on Market & Keep; floating bubbles = bright animated blobs on
  the base (template `float_resource` or the red-pixel test on base ROI). Free-levy = the option
  **without** a gem-cost label.
- **GEM-SAFE:** **only the free levy** — the paid levy tiers show gem prices; never tap them.

## (7) Mail + Event Center reward collection — "Claim All"  **[BOT]**
- **Reward:** attachments (speedups/resources/gems) in **Mail**; event-track rewards in the
  **Event Center**. **Cadence:** continuous / per-event.
- **UI flow:** **Mail** → **Rewards** tab → **Claim All** (single button) → delete-read.
  **Event Center** → each event tile with a red dot → open → tap each **Claim** / **Claim All**.
- **Detect:** red dot on Mail icon and Event Center icon → prefer a `claim_all_btn` template; if
  absent, `find_all(claim_btn_green)` loop. Verify dot cleared.
- **GEM-SAFE:** claim only; ignore any "buy pack" CTA inside events (those are gem/cash).

## (8) Shrine — daily free reward (+ skip paid offerings)  **[semi]**
- **Reward:** a **free daily reward** + login gifts; **offerings give rewards + monarch EXP but
  cost gems** `[kb/03]`. **Cadence:** daily.
- **UI flow:** tap **Shrine** → claim the **free daily/login** reward → **STOP**.
- **Detect:** red dot on Shrine → claim the free tile (green, no price). The **offering** buttons
  carry a **gem-cost label** → skip.
- **GEM-SAFE:** **free daily only; never make a paid offering.** That gem gate is exactly why this
  is **[semi]** — the free tile and the paid offering sit on the same screen; template-verify the
  free one and never the priced ones.

## (9) VIP daily chest  **[BOT]**
- **Reward:** free daily VIP chest (resources/speedups/VIP points) + VIP-level daily perks.
  **Cadence:** daily `[kb/03, kb/16]`.
- **UI flow:** tap the **VIP crown/avatar** → **Daily Chest / Claim** → close.
- **Detect:** red dot on the VIP badge; `claim_btn_green` vs greyed "claimed."
- **GEM-SAFE:** claim the free chest; **do not buy VIP points/activation with gems**.

## (10) Crazy Eggs / Lucky Wheel / event freebies  **[semi]/[MAN]**
- **Crazy Eggs = an EVENT** (runs ~10 days during the **Consuming Return** window, repeats ~every
  4 days), not a standing daily. **Hammers** come free from **killing monsters/bosses + gathering**
  — *or* **200 gems in the shop** `[theriagames crazy-eggs]`. Egg costs/cooldowns: **Lucy 3
  hammers/30m · James Bowie 6/1h · Isabella I 8/2h · Minamoto 12/4h · Caesar unlocks after all
  four**; ~**58–70 hammers** to fire all four. **Cracking is free.**
- **Hunter's Lucky Gift:** up to **10/day**, drops from high-level bosses (~1-in-3), **free** —
  resource chests, refining stones, Blood of Ares, civ-scroll frags `[theriagames lucky-gift]`.
- **Bacchus Tavern:** a **spend** event (Bacchus Gold Coins; 40%→70% odds strategy)
  `[theriagames bacchus-tavern]` — **bot SKIPS** unless coins are free.
- **UI flow (eggs):** Event Center → Crazy Eggs → if hammers ≥ egg cost → tap egg → crack → claim.
- **Detect:** event present (red dot on Event Center) + OCR hammer count ≥ threshold; only crack
  when hammers were earned free.
- **GEM-SAFE:** **never buy hammers/coins with gems.** Only crack with free-earned hammers →
  treat as **[semi]**; if it can't verify hammer source, leave **[MAN]**.

---

## ALLIANCE loops → the `alliance` task

## (11a) Alliance Help — auto-tap the Embassy hand  **[BOT]**
- **Reward:** free time reduction on every teammate's construction/research/healing/gear (and
  yours when you request). **Cadence:** continuous — the single highest-value free loop.
- **Mechanics `[evonytkrguide alliance-help]`:** the **hand icon** sits above any building with a
  running timer; the **hand on top of the Embassy = help EVERYONE in one tap**. You can help each
  person's task **once**, and request help on your task **once**. Value scales with Embassy level +
  research: **~10–15 min early game → several hours later; Embassy L32–33+ → 50+ helps/task.**
- **UI flow:** tap the **Embassy hand** (one tap helps all) every cycle; **also** request help
  right after the bot starts any build/research/heal (kb/27). 4x's `strategy.py` encodes the rule:
  **Alliance Help BEFORE any speedup, always** (each help = free timer reduction).
- **Detect:** red dot / number badge on the Embassy hand → tap → the badge clears when there's
  nothing left to help. Poll it on a short interval (help requests appear constantly).
- **GEM-SAFE:** 100% free.

## (11b) Alliance Science / Tech donation — stop before the gem tier  **[BOT, gem-guarded]**
- **Reward:** alliance-wide passive buffs + **personal alliance points/coins** per donation.
  **Cadence:** donations refresh on a **~4h cooldown** (recommend `next_run += 4h`) `[kb/16]`.
- **UI flow:** **Alliance → Science (Research/Tech)** → pick a **recommended** tech → **Donate**.
  Donation buttons come in tiers: a **free/resource-cost donate** and a **gem "one-key/instant"
  donate**.
- **Detect:** red dot on Alliance icon → the **basic Donate** button (resource icon, no gem
  price). **HARD GEM GUARD:** template `gem_cost_red` / a gem icon on the button → **do not tap**.
  Only tap the resource/free donate; when it flips to a gem-only prompt → stop for this cycle.
- **GEM-SAFE:** this is the loop the brief explicitly flags — **stop before it wants gems.**

## (11c) Alliance Gift claim  **[BOT]**
- **Reward:** gift chests + **Alliance Gift active-point** chests (whale purchases spawn gifts for
  everyone); loyalty/points. **Cadence:** continuous.
- **UI flow:** **Alliance → Gift** → **Claim All** (or loop each chest) → then claim the
  **active-point milestone chests** on the same screen.
- **Detect:** red dot on Alliance → Gift tab → `claim_all_btn` or `find_all(claim_btn_green)`.
- **GEM-SAFE:** claim only.

## (11d) Treasure Fragment / Alliance Treasure  **[semi]**
- **Reward:** treasure fragments assemble into chests (gear/speedups) `[VERIFY]` — surfaced via
  Alliance / event tracks; some come from Alliance Boss (below). **Cadence:** event/continuous.
- **UI flow:** Alliance / Event Center → Treasure tile → **Claim/Assemble** when a full set shows.
- **Detect:** red dot; `claim_btn_green` only when a set is complete (else greyed).
- **GEM-SAFE:** claim/assemble only; never gem-buy missing fragments. **[semi]** (exact UI varies).

## (11e) Alliance Boss  **[semi]**
- **Reward `[theriagames alliance-boss]`:** recurring **event every 28 days, lasts 2 weeks**; R4/R5
  summon **1 of 3 bosses** from the **Event Center**. Attack **solo (unlimited)** or **join an
  alliance rally**. Rewards: **Silver Lionheart Badges** (3,300 → a Civ-Gear chest), gems,
  **Refining/Research Stones, Runestone chests** (max personal-damage sample: 130 badges, 5,500
  gems, 320 refining, 320 research, 160 runestone chests). **Stamina-gated, not gem-gated.**
- **UI flow:** Event Center → Alliance Boss → **Rally/Join** (or solo Attack) → send **highest-
  attack tier only** (mounted/ranged so it survives) → confirm → claim on end. This overlaps the
  rally automation in kb/24 — reuse auto-join.
- **Detect:** red dot on Event Center during the window; **Join Rally** button (template, cf.
  TaskEX `join_alliance_war_btn.png`) present.
- **GEM-SAFE:** attacks cost **stamina**, not gems — don't gem-refill stamina. **[semi]**: gate so
  it doesn't burn troops you need; verify no-loss composition first.

## (12) Monarch talent point — take "Offer"  **[semi]**
- **Reward:** a free talent point per Lord level; the brief's **"Offer"** node = **+20% reputation
  & Lord EXP** `[kb/16]`. **Cadence:** whenever a point is available (level-ups from EXP the other
  loops generate).
- **UI flow:** tap the **Monarch portrait → Talents** → if **unspent points** → tap the pre-
  designated node (**"Offer"** first) → **confirm**. `[VERIFY]` exact tree layout/node coords —
  hardcode the node coordinate after one manual mapping.
- **Detect:** red dot on the Monarch portrait / Talents tab; OCR the **"unspent points"** count > 0.
- **GEM-SAFE:** allocation is free; **never gem-reset** the talent tree. **[semi]** (node coords
  are layout-specific).

## (13) The universal "collect-all / red-dot sweep"  **[BOT]**
This is the meta-pattern that ties 1–12 together and catches anything new. From 4x `strategy.py`'s
daily routine the literal step is **"Claim ALL red notification dots."** Implementation:
- Keep a **table of nav-icon ROIs** (Quests, Mail, Event Center, Alliance, Embassy hand, VIP,
  Shrine, Walls, Market, Keep, Monarch, Tavern). Each cycle, run the **red-pixel test** over each
  ROI → build a work-list of icons showing a badge.
- For each flagged icon: open it → run the icon-specific claim flow above → **re-screenshot &
  verify the dot cleared** → close. Unknown/new screens: `find_all(claim_btn_green)` + a generic
  **Claim All** template as a catch-all, then back out safely.
- **Never** tap a **red/gem-priced** button anywhere in the sweep (the global gem guard).

---

## Bot task design

### `daily_collect` (personal freebies) — priority order
Mirrors 4x's daily routine, ordered by value/effort:
1. **Mail + Event Center Claim-All** (7) — speedups/gems sitting there.
2. **Daily Quests + Activeness chests** (2, 1) — ~200 gems + general frags.
3. **VIP daily chest** (9).
4. **Wall Patrol ×3** (4) · **Bounty ×8** (5, gated vs gather marches).
5. **Free Tax / Free Levy / Warehouse + base sweep** (6).
6. **Shrine free daily** (8, skip paid offerings).
7. **Wheel of Fortune free spin** (3, free-only) · **Monarch "Offer" point** (12).
8. **Event freebies** (10) — Lucky Gift auto-drops; Crazy Eggs only if hammers free.
Runs on **daily-reset** wake + a mid-day catch-up; each item is a red-dot-gated flow with verify.

### `alliance` (alliance loops) — priority order
1. **Alliance Help / Embassy hand** (11a) — short interval, every cycle (highest free value).
2. **Alliance Gift Claim-All** (11c).
3. **Alliance Science donation** (11b) — **~4h cooldown, HARD stop before gem tier.**
4. **Treasure Fragment assemble** (11d) · **Alliance Boss join** (11e) during its window.
Embassy-hand poll is frequent; donation is cooldown-scheduled; boss is event-gated.

### GEM-SAFE invariants (hard guards, apply to BOTH tasks)
- **Never tap a button carrying a gem icon / gem-price label** (`gem_cost_red` template) — claim
  buttons are **green**, spend buttons are **red/blue with a gem number**.
- **Alliance tech donation:** only the resource/free donate; **stop the instant it flips to a
  gem-only donate.**
- **No gem:** spins, egg/lucky hammers, Bacchus coins, extra wall patrols, extra/paid levy, paid
  Shrine offerings, VIP activation/points, stamina refills, talent resets, bounty refresh/instant.
- **Verify-after-act** every claim (re-screenshot, confirm dot cleared / toast shown); a gem-cost
  confirm dialog = **abort + back out**, log, move on (never blind-confirm).

---

## Sources
theriagames.com: evony-walls-guide (Wall Patrol 3/day, gear+material chests, drop rates),
evony-crazy-eggs-event-guide (hammer sources/costs, 200-gem shop, egg cooldowns), evony-hunters-
lucky-gift-guide (10/day, boss drop), evony-world-boss (10 hits/day, rank gem rewards),
evony-alliance-boss-guide (28-day/2-week cycle, Event Center, Silver Lionheart Badges),
evony-bacchus-tavern-guide (spend event, 40%→70%); evonytkrguide.com how-to-use-alliance-help
(Embassy hand = help all, once/person/task, Embassy L32-33+ → 50+ helps). OSS: sonpiaz/4x-game-
agent `strategy.py` (daily routine + "Claim ALL red notification dots", Alliance-Help-before-
speedups, gem-safe rules), `screen_analyzer.py` (red-pixel-area badge test, red-button popup
classify), README (Auto-collect-resources sweep-tap, Auto-alliance-help+donate); Jany-M/TaskEX
(checked/unchecked toggle + rarity-frame templates, `join_alliance_war_btn`); TungNC-echoes/auto-
evony-v1 (`find_and_click_button` thr≈0.65, `open→use` item sequence, market/levy actions).
Internal: kb/03 §6-7, kb/16 (145 chest / 200-gem quests / 8 bounties / VIP chest / Wheel 900-coin /
Monarch "Offer" / Shrine offerings cost gems), kb/17 (ALAS scheduler, detection stack), kb/24
(rally auto-join), kb/27 (alliance help on build/research). **NOTE (WebSearch budget was exhausted
mid-research — no fresh search pass):** evonyguidewiki.com was unreachable and theriagames Tavern/
Shrine pages are "coming soon" stubs, so the **Tavern 145 breakdown, Wheel free-spin/coin cost,
Shrine daily contents, exact bounty/levy cadence, and Monarch talent tree coords are `[VERIFY
IN-GAME]`** before hardcoding. **World Boss free-hit count conflicts: theriagames says 10/day vs
kb/16's 5/week — `[VERIFY IN-GAME]`.**
