# ESB-TKR Feature Study & Our Roadmap

Learning from the commercial Evony bot **ESB-TKR / EAT** (emulatorautomation.com) to decide
what to add to our own bot. Sources: the product site + its legacy docs blog (evonysmartbot.com
2022–2024) + web/Reddit synthesis. Confidence tags: [multi]=corroborated, [single]=one source,
[uncertain]=inferred.

## Strategic read (the important part)

ESB-TKR is a **rally / farm / boss-hunt / map-scan / defense** bot. It deliberately does **NOT**
train troops, upgrade buildings, or do research. That is the *inverse* of our bot, which is
strong on base management (training, food self-heal, dashboard/stream) and does nothing on the
map/rally side. **The two feature sets are almost perfectly complementary.** Adding auto-bubble
+ alliance/daily loops + gathering would make ours the first tool that does *both* well —
especially on macOS, where ESB-TKR itself is only a shaky beta.

## Platform & pricing (can we just use ESB instead?)

- **OS:** Windows is the mature build. A **macOS Apple-Silicon build exists but is beta** ("some
  features may not be working"). On the user's macOS/BlueStacks, our ADB+OpenCV path is the more
  reliable option. [multi]
- **Emulators:** MEmu 7.6, NoxPlayer, BlueStacks 5, via ADB port. [multi]
- **Pricing:** self-run $5/mo (1 instance) → $10 (5) → $20 (15), +$1/extra; 3-day trial.
  Managed cloud service $30/mo (rally joiner or gathering) → $100/mo VIP. [single]
- Conclusion: **build our own, learn from ESB.** Not worth a Windows box + subscription for a
  black box that can't manage our base and whose Mac build is unreliable.

## ESB-TKR feature catalog (what to learn from)

**Rallies** — Join Rallies (default filters: <5 min left, boss-only, march-time feasible); two
algorithms (Accurate reads timer+boss type; Fast joins boss rallies blindly). Join from Alliance
Chat links. **Auto Setter** starts rallies on bosses with presets (Weak/Middle/Strong: pan type
Mounted/Ground/Archers, tier, troop count, rotate-preset), stamina-consume, fallback to joining
after ~5 fails; boss priority Event→Hydra→b15..b1. Requires Japanese culture + zoomed-out map. [multi]

**Monsters/Bosses** — Boss Finder (scans Viking list then map); Monster Killer (solo non-boss);
stamina management; event bosses prioritized. [multi]

**Gathering/Farming** — dispatch marches to specified tiles at a specified level; march-slot
management; multi-instance slot scaling. No gear-swap-on-gather documented. [multi]

**Defense/Survival** — **Auto-bubble / instant shield**: detects being scouted or attacked and
bubbles *before* the march lands; **saves the shield if the attacker recalls**. Priority 3d→24h→8h;
buy-with-gems fallback; push notifications. Explicitly not 100% reliable (crash = no bubble).
[multi] Their most-loved feature.

**Map/World** — full server-map scan (track players/treasures/alliances); **Grid search** over
(0,0)–(1200,1200) with X/Y bounds + search-time, Fixed vs Automatic gap-partition, Grid-ID per
instance; Random search (swipe) for few accounts; iScout API feeds bosses for 24/7 setting. [multi]

**Alliance** — Activities bundle every 4h: Science donation + Help auto-tap + Gift claim +
Treasure Fragment. Viking/boss sharing to a "collective" (alt-account pool). [single]

**Daily/Events** — Wheel of Fortune, Patrol, Black Market auto-buy, Crazy Eggs, Mail/events
collection (3h20m), in-city resource collection (3h20m), auto-close achievement pop-ups. Not
found: VIP chest, wall patrol, bounty, shrine, SvS-timing. [single/uncertain]

**Scheduling** — Google-style **calendar scheduler**; smart interval timers; **Breaks** (human
sleep windows); real-time charts with **PDF/CSV export**. [multi]

**Multi-account** — multiple instances (plan-gated); **profiles** (sync to server DB); **proxy**
support; Grid-ID partitioning. [multi]

**Anti-detection** — image recognition, no injection; breaks, random search, proxies, hourly
re-login; disclaims ban-safety, recommends farm accounts. [multi]

## Our roadmap — features to add (ranked value × automatability on our stack)

Legend: **[fixed-UI]** = no map navigation needed, can build now; **[zoom-nav]** = blocks on the
camera-zoom-robust map/building navigation.

### Tier 1 — build first (high value, high automatability, [fixed-UI])
1. **Auto-bubble / instant shield on scout-or-attack** — ESB's flagship and the biggest survival
   win. Detect incoming march/scout (OCR alert banner + red march indicators) → tap shield item
   (priority 3d→24h→8h, gem fallback). Fixed UI. Add an `UNDER_ATTACK` state to our FSM. **Start here.**
2. **Alliance daily bundle** — Help auto-tap + Science donation + Gift claim + Treasure Fragment,
   on a timer. Fixed-position taps; highest value-per-effort. Runs on the scheduler we built.
3. **Daily/event collection loop** — Mail, in-city resources, Wheel of Fortune, Crazy Eggs, patrol,
   VIP/free chests. All fixed-UI, timer-driven → **wire the ALAS-style scheduler** (built, not yet
   wired) to these. Fastest path to "runs all day unattended."

### Tier 2 — after zoom-nav lands ([zoom-nav])
4. **Resource gathering / auto-dispatch to tiles** — map search + tile-level OCR + march slots.
   Biggest "we don't do it" gap that's in OpenCV+OCR reach; also funds the 1B food goal (kb/14).
5. **Rally join (boss rallies)** — read rally list, filter <5 min / boss-only / march-feasible.
   UI-list based (easier than gathering). Add alliance-chat-join later.
6. **Monster/boss attack + Auto-Set rallies** — map scan (grid/random) + boss detect + preset/pan
   + stamina. Most complex; model ESB's preset system. Build after gathering proves the map-nav.

### Tier 3 — infra multipliers
7. **Notifications (Discord/Telegram webhook)** — on `UNDER_ATTACK`, account-disconnect (we already
   detect it!), bubble-applied, crash. A few hours' work, huge UX; **we can beat ESB here easily.**
8. **Multi-account / multi-instance** — generalize our per-account disconnect detection to N ADB
   devices + per-profile config + round-robin scheduling.
9. **Full map scan** — [zoom-nav], heavy OCR, niche intel value. Lowest priority; ESB's grid model
   (0–1200, gap-partition) is the blueprint if we do it.

### Skip / defer
Teleport, auto-heal/hospital, gear-swap-on-gather — unproven in ESB, lower value.

## Build order

Auto-bubble → alliance daily bundle → wire scheduler to daily/event tasks → Discord/Telegram
notifications → **(zoom-nav lands)** → gathering → rally-join → monster/auto-set → multi-account →
map scan (optional).

**Zoom-nav dependency:** items 4, 6, 9 block on the camera-zoom-robust map/building navigation.
Items 1, 2, 3, 7, 8 are fixed-UI and can proceed in parallel while zoom-nav is built.

## Note: our own gem-safety rule (learned the hard way)

The Training Speedup modal's **"Finish All"** (orange, bottom-left) spends **GEMS** to instant-
complete on abnormal/oversized batches (observed: ~386k gems on a stacked 3d batch, without
clearing it), whereas for a normal single batch it applies **items**. "Use" (green) applies
selected **items** but has misbehaved (consumed items without cutting the timer). **The bot must
never tap a gem-spend path automatically.** Auto-clear should prefer item-based speedup and gate
any gem action behind an explicit, bounded confirmation — same discipline as the food refill's
never-open-all / never-spend-gems rails.
