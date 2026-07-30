# General portraits

The `.svg` files here are **self-hosted, generated "portrait medallions"**
(type-coloured crest + initials + star rating) produced by
`generals_view.render_portrait_svg`. They carry **no third-party artwork** and
have **zero licensing risk**.

## Why not the real in-game art?

Official Evony: The King's Return general portraits are **copyright Top Games
Inc.** Every fan source was checked and none give a safe, reliable image URL:

| Source | Result |
|---|---|
| evonyguidewiki.com | Cloudflare "verify you are human" bot wall |
| evony.fandom.com | HTTP 403 to scrapers; and it has **no** Evony:TKR general pages (dead wiki) |
| evony-hq.com | Client-side SPA; `/api/generals` returns **stats only, no image URLs**; general detail pages are 402 Payment Required |

Hot-linking their PNGs would (a) break on hot-link protection and (b)
redistribute copyrighted art on someone else's bandwidth. So the app ships
generated medallions instead.

## Dropping in real art (optional)

The portrait route serves any real raster you place here, **overriding** the
generated medallion:

```
static/generals/<slug>.png      # or .jpg / .jpeg / .webp
```

`<slug>` is the general's name lower-cased with non-alphanumerics turned to
hyphens, e.g.:

- `zhou-yu.png`
- `presley-o-bannon.png`
- `jan-karol-chodkiewicz.png`

The generated SVGs are regenerated live on each page load (colour stays in sync
with the general's recorded troop type), so the `.svg` files here are just an
exported reference copy — you can delete them without affecting the app.

Data provenance: ownership comes from Postgres `murderbot.generals`; skill /
buff magnitudes are verified against the evony-hq.com generals API and
`game_brain/pvp_brain.md` §8 / §9 / §13.
