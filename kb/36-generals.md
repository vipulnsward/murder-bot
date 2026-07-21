# Evony Generals Database — Catalog (from evonyguidewiki.com)

Structured roster of PvP + role generals scraped from evonyguidewiki.com "Best of ___ General"
guides + the master "List of Generals by Role". Machine-readable copy: `data/generals.jsonl`
(303 objects, one per general). This doc is the human-readable catalog + tier lists.

## Verification legend
- **Everything here is sourced from evonyguidewiki.com** (page URLs listed under each section and in
  `source_url`/`source_urls` of each JSONL record). Extracted 2026-07 via headed browser (site sits
  behind a JS "please wait / verifying" wall that blocks plain fetch/curl; a real browser passes it).
- `RANK` = the site's own ordering inside a guide's "All ___ Generals" ranking table = **authoritative**.
- `TIER` (S/A/B/C/D) = **DERIVED by us** from rank buckets (S≤3, A 4-8, B 9-16, C 17-28, D 29+), a
  convenience only — the site publishes numeric ranks + score columns, not letter tiers. Treat rank as truth.
- `(deb)` / `is_debuff` = the guide's Debuff column was non-empty, or the general is a Subordinate-City
  Mayor (Debuff). Debuff detail strings are in each record's `notes`.
- `quality="Legendary"` for the 299 generals in the site's "golden historic generals" master list
  (its wording). 4 ranking-only generals have `quality=null` (not in that list). **Skin/Dragon
  variants** (e.g. "Lorenzo de' Medici (+Skin)") are normalized to the base name; variants noted.
- **Not captured from these overview pages:** per-general `skill` text, full `specialties`, and
  `ascending` attributes — those live on individual general detail pages (100+), a next-crawl job.
  Only the 5 monster-hunter generals below carry skill/specialty text (their guide tabulates it).
  `[VERIFY]` = tag anything you hardcode against the live game.

## Counts (this pass)
- **303 generals**, **504 role-ratings**, **85 debuff** generals, **8 pages read**.
- gtype split: mounted 48, ranged 54, ground 42, siege 39, wall 23, subcity 35, monster 8, other 54.
- Roles captured: ground/mounted/ranged/siege × {march-attack, reinforce-defense}, wall_defense, monster.
- **Pages READ:** best-{ground,mounted,ranged,siege}-general, best-defense-general (Wall),
  best-boss-monster-general, list-of-generals-worth-hiring ("Best Generals & Combinations"),
  general-list-by-type-and-how-to-get (master roster + how-to-get).
- **Sibling generals pages NOT yet fetched** (next crawl): the 5 Assistant-General rankings
  (best-{ground,mounted,ranged,siege}-assistant-en, best-defense-assistant-en, assistant_general-en),
  sub-city-generals-debuff-comparison-tool-en, subordinate-city-guide-en, sub-city-buff-list-en.
- **No dedicated "Monarch general" guide exists** on the site — monarch's officer slots = Duty
  Officers (captured under gtype=other) + monarch-gear pages. Flag if a monarch-general page appears later.

## How to read the JSONL
Each line: `{name, quality, gtype, is_debuff, specialties, skill, ascending, best_use, notes,
source_url, source_urls[], ratings:[{role, tier, rank, context}]}`. `gtype` ∈
ground|mounted|ranged|siege|wall|subcity|monster|other. A general carries one rating per role it's
ranked in (e.g. a ground general has ground_attack + ground_defense, and maybe wall_defense).

---

## Ground — src: best-ground-general-en
Two rankings: **A) March & Rally (attack)** and **B) Reinforce/Wall (defense)**. 42 generals.
- **March/Rally:** 1.Lafayette 2.Vercingetorix 3.Akechi Mitsuhide 4.Lorenzo de' Medici
  5.Niccolo Piccinino(deb) 6.Narcissus(deb) 9.Louis II 11.Francis I of France 12.Alexander Hamilton
  13.Charles V 14.Lucilla(deb) 15.Gao Changgong 17.Maria Carolina 19.Zhang Fei.
- **Reinforce/Wall:** 1.Akechi Mitsuhide 2.Freyja 3.Niccolo Piccinino(deb) 4.Francis I of France
  6.Lucilla(deb) 7.Gao Changgong 8.Maria Carolina 10.Zhang Fei 11.Miltiades(deb) 12.Frigg(deb)
  13.Qin Qiong 14.Sweyn Forkbeard.
- Akechi Mitsuhide + Francis I = versatile (top of both lists). Lafayette/Lorenzo/Louis II = pure attack (weak on defense).

## Mounted — src: best-mounted-general-en
49 generals per list (58/57 rows incl. variants).
- **March/Rally:** 1.Shaybani 2.Tishtrya(deb) 4.Babur 5.Henry IV 6.Stephen I of Hungary 7.Rostam(deb)
  8.Hermes(deb) 9.Louis XIV 11.Olav II 13.Artemis(deb) 14.Marco Polo(deb) 15.Mouri Motonari
  17.Haakon Haraldsson 18.Napoleon(deb).
- **Reinforce/Wall:** 1.Hermes(deb) 2.Babur 4.Rostam(deb) 6.Henry IV 7.Mouri Motonari
  8.Haakon Haraldsson 9.Cheng Yaojin 10.Washington 11.Andre Massena(deb) 12.Ii Naomasa(deb) 13.Laudon.
- Mounted is the monster/rally troop of choice (see kb/24-25); Rostam/Marco Polo/Tishtrya/Haakon reappear as boss setters.

## Ranged — src: best-ranged-general-en
53/54 generals (largest roster).
- **March/Rally:** 1.Marcian 2.Charles VI 3.Visconti 4.Rumyantsev 5.Hatshepsut(deb) 7.Ahmose I(deb)
  8.Artemisia I 10.Algernon Sidney 11.Brian Boru 12.Gonzalo 13.Ragnar(deb) 14.Sigurd(deb) 15.Franz Joseph I.
- **Reinforce/Wall:** 1.Visconti 2.Idunn 3.Ahmose I(deb) 5.Gonzalo 6.Sigurd(deb) 7.Franz Joseph I
  9.James Cook 10.Tachibana Ginchiyo 11.Godfrey of Bouillon 12.Arthur Wellesley 14.Subutai 15.Louis IX.

## Siege — src: best-siege-general-en
42 generals.
- **March/Rally:** 1.Presley O'Bannon 3.Irene d'Arneau 4.Olaf Skotkonung 5.Romulus 7.Daniel Morgan
  8.Kiso Yoshinaka 9.Hersilia 10.Francis Drake 11.Shapur I 13.Theobald I 14.Christina 15.Champlain.
- **Reinforce/Wall:** 1.Hersilia 2.Irene d'Arneau 4.Francis Drake 5.Champlain 6.Stephen II
  7.Melisande(deb) 9.Maurice de Saxe 10.Daniel Morgan 11.Shapur I 12.Sei Shonagon 16.Edward Teach.

## Wall Defender — src: best-defense-general-en (Wall)
Cross-troop-type wall ranking (any troop type can defend a wall). 46 generals. `Strengths` col =
which troop types they buff; `Main Role` = Walls vs Attacker (some attackers double as wall defenders).
- 1.Zhou Yu 2.Takenaka Shigeharu(deb) 3.Niccolo Piccinino(deb) 4.Francis I of France 6.Isaac Brock
  7.Akechi Mitsuhide 8.Hersilia 9.Visconti 10.Henry IV 12.Hermes(deb) 14.Zhang Fei 15.Stephen II
  17.Champlain 18.Franz Joseph I.

## Monster / Boss Hunter — src: best-boss-monster-general-en
Assumes mounted-only troops. This is the one guide that tabulates skill + specialty text → captured.
Ranking is split no-pay vs paid. **Focus = double item-drop rate (dev) OR attack+march-size (zero-wound).**
- **F2P (no money):** 1.**Baibars** — skill *Double Items Drop Rate +25%* (up to +41% maxed); best free
  double-drop farmer. 2.**Nathanael Greene** — skill *Reduce Stamina's Cost -25%* (ONLY stamina-cost
  general; best for rally-heavy stamina economy).
- **Paid:** 1.**Theodora** *(Mtd/Grd Atk +30% vs Monster, Double Drop +10%; up to +43% drop — best)*
  2.Baibars 3.**Caesar** *(Mtd Atk +60% vs Monster, needs a Dragon; high attack)* 4.**Aethelflaed**
  *(Mtd Atk+55%/Def+55% vs Monster; can't use Mtd-Atk-vs-Monster skillbook)* 5.Nathanael Greene.
- Cross-ref kb/25: same doctrine (mounted, one-round-kill, Baibars/Theodora double-drop, Greene stamina).

## Subordinate-City Mayor / Debuff — src: general-list-by-type (Mayor Debuff section)
35 generals (gtype=subcity, all `is_debuff=true`). Mayors sit in captured sub-cities and project a
debuff aura; used to weaken enemies in SvS/rallies. Full list:
Amr ibn al-As, Andrew Jackson, Arminius, Baldwin IV, Catherine II, Charles Martel, Charles the Great,
Cimon, Cnut the Great, Constantine the Great, Darius I, David Farragut, Empress Dowager Cixi,
Empress Wu, Flavius Aetius, Gilgamesh, Harald, Hojo Ujiyasu, Jan Karol Chodkiewicz, Jester,
King Sejong, Lincoln, Mansa Musa, Margaret I, Mark Antony, Montezuma I, Narses, Nero,
Nordic Barbarian King, Pachacuti, Pompey, Tokugawa Ieyasu, Yeon Gaesomun, Zhu Di, Zizka.
(Debuff comparison + per-general debuff values: sub-city-generals-debuff-comparison-tool-en — next crawl.)

## Debuff generals (all gtypes) — 85 total
Any general whose guide row carries a debuff. Beyond the subcity mayors above, notable PvP-troop
debuffers: Tishtrya, Rostam, Hermes, Marco Polo, Napoleon, Artemis (mounted); Hatshepsut, Ahmose I,
Sigurd, Ragnar (ranged); Niccolo Piccinino, Narcissus, Lucilla, Frigg, Miltiades, Alexander Nevsky
(ground); Melisande, Gunther, Pallas, Raimondo, Suleiman the Magnificent (siege); Takenaka Shigeharu
(wall). Debuff strings (e.g. "Ranged & Siege Atk -10%") are in each record's `notes`. Rally doctrine
(kb/24): debuff-joins cap monster-def debuff at -50%.

## F2P (no-pay) recommended MAIN picks — src: list-of-generals-worth-hiring-en
Per-role no-money combos (Main + Assistant). Recommended MAINs:
- Ranged: **Marcian** (also Charles VI, Hatshepsut) · Mounted: **Tishtrya**, **Babur** · Ground:
  **Lafayette**, **Lorenzo de' Medici**, **Akechi Mitsuhide** · Siege: **Presley O'Bannon** ·
  Mixed/other: **Amir Timur**. Guide's meta note: latest Premium generals at Red Star 0 beat
  Tavern/Relic generals at Red Star 5 — don't invest red stars in Tavern/Relic generals.
- 100+ generals also tagged as premium/paid meta picks (see `notes` field). Full paid combos per role
  in the source page (next-crawl for exact assistant pairings).

## gtype=other (54) — src: general-list-by-type
All-arounder/mixed, Resource Gathering/Looting, Duty Officers, and Production-defense generals.
Includes gatherers/looters (kb/23) and monarch Duty-Officer picks. Names in JSONL; role-specific
rankings for these were not separately tabled on the pages read.

## Next-crawl to enrich this DB
Per-general detail pages (for skill/specialty/ascending on all 303), the 5 Assistant-General
rankings, and the sub-city debuff comparison tool. See `data/evonyguidewiki-sitemap.md`.
