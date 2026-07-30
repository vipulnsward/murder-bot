"""Generals gallery — artwork + combat stats for the Murder Bot manager.

Self-contained FastAPI APIRouter. It does NOT import app.py (no circular
import): the host app injects its own ``current_user`` auth dependency and
``database`` context manager through ``build_router(...)``.

Data sources
------------
* Ownership / level / stars / role : Postgres ``generals`` table (per user).
* Combat skills & buff/debuff magnitudes : a curated catalog below, whose
  numbers are verified against the evony-hq.com generals API and the local
  ``game_brain/pvp_brain.md`` combat model (sections 8 / 9 / 13).

Artwork
-------
Official Evony general portrait art is copyright Top Games Inc. Every fan-wiki
source (evonyguidewiki.com, evony.fandom.com, evony-hq.com) is behind bot /
pay walls or renders images client-side, so none give a reliable hot-link URL
and redistributing the PNGs would be a licensing risk. Instead each card ships
a self-hosted, generated SVG "portrait medallion" (type-coloured crest with the
general's initials + star rating) — zero licensing risk, no broken hot-links,
works offline. To use real art later, drop ``<slug>.png`` (or .jpg/.webp) into
``static/generals/`` and the portrait route serves it automatically.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

BASE_DIR = Path(__file__).resolve().parent
PORTRAIT_DIR = BASE_DIR / "static" / "generals"

RECOMMENDED = {
    "wall": [
        "Zhou Yu",
        "Takenaka Shigeharu",
        "Stephen II",
        "Leo III",
        "Niccolo Piccinino",
    ],
    "debuff_mayor": [
        "Cimon",
        "Gilgamesh",
        "Jan Karol Chodkiewicz",
        "Zizka",
        "Baldwin IV",
        "Flavius Aetius",
    ],
}
RECOMMENDED_LOWER = {
    name.casefold(): group for group, names in RECOMMENDED.items() for name in names
}

TYPE_META = {
    "ground": {"label": "Ground", "glyph": "🛡️", "fill": "#2ea043", "ring": "#3fb950"},
    "ranged": {"label": "Ranged", "glyph": "🏹", "fill": "#1f6feb", "ring": "#58a6ff"},
    "mounted": {"label": "Mounted", "glyph": "🐎", "fill": "#c9432f", "ring": "#ff7b72"},
    "siege": {"label": "Siege", "glyph": "🏰", "fill": "#8250df", "ring": "#a371f7"},
    "mixed": {"label": "Debuff", "glyph": "🎭", "fill": "#9e6a03", "ring": "#d29922"},
    "other": {"label": "Other", "glyph": "⚔️", "fill": "#57606a", "ring": "#8b949e"},
}

CATALOG = [
    {
        "name": "Zhou Yu",
        "gen_type": "ground",
        "group": "wall",
        "tagline": "Wall general (in-city ranged/siege)",
        "buffs": [
            "In-city Ranged Atk +40%",
            "In-city Siege Atk +40%",
            "In-city Ground Def +20%",
            "In-city Mounted Def +20%",
            "In-city Ground HP +20%",
            "In-city Mounted HP +20%",
        ],
        "debuffs": [],
        "brain_note": (
            "Top wall pick — ascended to roughly +4,096% all-type in-city buff "
            "(pvp_brain §8.3). Fires ONLY in-city; pair a separate marching "
            "attacker."
        ),
        "bio": "Eastern Han strategist who laid the foundation for the rise of Eastern Wu.",
    },
    {
        "name": "Takenaka Shigeharu",
        "gen_type": "siege",
        "group": "wall",
        "tagline": "Pure siege anvil (in-city)",
        "buffs": [
            "In-city Siege Atk +50%",
            "In-city Ground Def +45%",
            "In-city Mounted Def +45%",
        ],
        "debuffs": ["Enemy Siege Atk -10%"],
        "brain_note": (
            "Pure siege anvil, ~+3,856% ascended, and he brings Enemy Siege "
            "Atk -10% baked in (pvp_brain §8.3)."
        ),
        "bio": "Sengoku-period samurai strategist, also known as Hanbei.",
    },
    {
        "name": "Stephen II",
        "gen_type": "siege",
        "group": "wall",
        "tagline": "Alternate wall (siege)",
        "buffs": ["Siege Atk +50%", "Siege Def +40%", "Siege HP +40%"],
        "debuffs": [],
        "brain_note": "Alternate dedicated wall general (pvp_brain §7.2).",
        "bio": "King of Hungary, renowned for wise governance and shrewd diplomacy.",
    },
    {
        "name": "Leo III",
        "gen_type": "siege",
        "group": "wall",
        "tagline": "Wall option (in-city siege)",
        "buffs": ["In-city All Atk +10%", "In-city Siege Atk +35%"],
        "debuffs": [],
        "brain_note": "Listed wall option for in-city siege attack (pvp_brain §7.2).",
        "bio": "Byzantine Emperor and founder of the Isaurian dynasty.",
    },
    {
        "name": "Niccolo Piccinino",
        "gen_type": "ground",
        "group": "wall",
        "tagline": "#1 ground / assistant",
        "buffs": [
            "Ground Atk +60%",
            "Ground HP +60%",
            "Ground Def +45%",
            "Mounted Def +45%",
        ],
        "debuffs": [],
        "brain_note": "#1 ground / assistant general if leaning ground defense (§8.3).",
        "bio": "Northern-Italian mercenary commander with a near-unbroken win record.",
    },
    {
        "name": "Cimon",
        "gen_type": "mixed",
        "group": "debuff_mayor",
        "tagline": "Sub-city debuff mayor (best single)",
        "buffs": [],
        "debuffs": [
            "Enemy Ranged Atk -40%",
            "Enemy Siege Atk -40%",
            "Enemy Siege Def -30%",
            "Enemy Siege HP -30%",
        ],
        "brain_note": (
            "THE first debuff acquisition — the only mayor that debuffs BOTH "
            "Ranged AND Siege across Atk/Def/HP, plus +10% death-to-survival "
            "(§8.1, §13E). Debuffs stack across all sub-cities."
        ),
        "bio": "Athenian statesman and one of the ten generals of Athens.",
    },
    {
        "name": "Gilgamesh",
        "gen_type": "mixed",
        "group": "debuff_mayor",
        "tagline": "Sub-city debuff mayor",
        "buffs": [],
        "debuffs": [
            "Enemy Ground Atk -25%",
            "Enemy Ranged Def -40%",
            "Enemy Siege Def -40%",
        ],
        "brain_note": "Debuff mayor — Siege Def -40 / Ranged Def -40 (§8.1).",
        "bio": "Hero-king of Uruk from the Epic of Gilgamesh.",
    },
    {
        "name": "Jan Karol Chodkiewicz",
        "gen_type": "mixed",
        "group": "debuff_mayor",
        "tagline": "Sub-city debuff mayor",
        "buffs": [],
        "debuffs": [
            "Enemy Mounted Atk -25%",
            "Enemy Siege Def -30%",
            "Enemy Siege HP -30%",
        ],
        "brain_note": "Debuff mayor — Siege Def -30 / Siege HP -30 (§8.1).",
        "bio": "Lithuanian commander who beat a Swedish army three times his size.",
    },
    {
        "name": "Zizka",
        "gen_type": "mixed",
        "group": "debuff_mayor",
        "tagline": "Broad ranged debuffer",
        "buffs": [],
        "debuffs": [
            "Enemy Ranged Atk -40%",
            "Enemy Ranged Def -15%",
            "Enemy Ranged HP -15%",
            "Enemy Siege Def -15%",
            "Enemy Siege HP -15%",
        ],
        "brain_note": "Broad ranged debuffer; stacks toward -120% ranged invested (§8.1, §13E).",
        "bio": "Bohemian national hero, one of history's great commanders.",
    },
    {
        "name": "Baldwin IV",
        "gen_type": "mixed",
        "group": "debuff_mayor",
        "tagline": "Sub-city debuff mayor",
        "buffs": [],
        "debuffs": ["Enemy Ranged Atk -30%", "Enemy Siege Atk -20%"],
        "brain_note": (
            "Debuff mayor — base Ranged Atk -35 / Siege Atk -25, up to "
            "Ranged -75 / Siege -65 deep-invested (§8.1, §13E). Skin 'Divine "
            "Guardian' adds ground/mounted HP + ranged/siege atk debuffs."
        ),
        "bio": "The 'Leper King' of Jerusalem, a gifted battlefield commander.",
    },
    {
        "name": "Flavius Aetius",
        "gen_type": "mixed",
        "group": "debuff_mayor",
        "tagline": "Sub-city debuff mayor",
        "buffs": [],
        "debuffs": ["Enemy Siege Atk -20%", "Enemy Ground HP -20%"],
        "brain_note": "Debuff mayor — Siege Atk -20, scales to Siege -60 invested (§8.1, §13E).",
        "bio": "Roman general of the closing Western Roman Empire.",
    },
    {
        "name": "Presley O'Bannon",
        "gen_type": "siege",
        "group": "marching",
        "tagline": "Siege attack leader (marching)",
        "buffs": [
            "Marching Siege Atk +60%",
            "Marching Siege Def +60%",
            "Marching Siege HP +45%",
            "Marching Ranged HP +45%",
        ],
        "debuffs": [],
        "brain_note": (
            "Siege attack leader — opens at MAX range on enemy siege/ranged. "
            "The incoming archetype your wall must debuff (§9)."
        ),
        "bio": "U.S. Marine officer famed for the Battle of Derna.",
    },
    {
        "name": "Romulus",
        "gen_type": "siege",
        "group": "attacker",
        "tagline": "Siege attacker (marching)",
        "buffs": [
            "Marching Siege Atk +55%",
            "Marching Siege HP +55%",
            "Marching Ranged Def +35%",
            "Marching Siege Def +35%",
        ],
        "debuffs": [],
        "brain_note": "",
        "bio": "Founder of Rome, deified as Quirinus.",
    },
    {
        "name": "Lafayette",
        "gen_type": "ground",
        "group": "attacker",
        "tagline": "Ground attacker (marching)",
        "buffs": [
            "Marching Ground Atk +60%",
            "Marching Ground Def +60%",
            "Marching Ground HP +45%",
        ],
        "debuffs": [],
        "brain_note": "Textbook enemy Ground archetype — counter with Mounted (§9).",
        "bio": "Hero of the American Revolutionary War.",
    },
    {
        "name": "Ahmose I",
        "gen_type": "ranged",
        "group": "attacker",
        "tagline": "Ranged attacker",
        "buffs": ["Ranged Atk +55%", "Ranged Def +55%", "Ranged HP +40%"],
        "debuffs": [],
        "brain_note": "",
        "bio": "Founder of Egypt's 18th Dynasty who reunified Egypt.",
    },
    {
        "name": "Artemisia I",
        "gen_type": "ranged",
        "group": "attacker",
        "tagline": "Ranged attacker (marching)",
        "buffs": [
            "Marching Ranged Atk +55%",
            "Marching Ranged Def +55%",
            "Marching Ranged HP +35%",
        ],
        "debuffs": [],
        "brain_note": "",
        "bio": "Queen of Caria, renowned strategist of the Greco-Persian Wars.",
    },
    {
        "name": "Charles VI",
        "gen_type": "ranged",
        "group": "attacker",
        "tagline": "Ranged attacker (marching)",
        "buffs": [
            "Marching Ranged Atk +55%",
            "Marching Ranged HP +55%",
            "Marching Ranged Def +40%",
        ],
        "debuffs": [],
        "brain_note": "Textbook enemy Ranged archetype — counter by leading with Ground (§9).",
        "bio": "Holy Roman Emperor who entrusted his armies to Prince Eugene.",
    },
    {
        "name": "Hatshepsut",
        "gen_type": "ranged",
        "group": "attacker",
        "tagline": "Ranged attacker (marching)",
        "buffs": [
            "Marching Ranged Atk +55%",
            "Marching Ranged HP +55%",
            "Marching Ranged Def +40%",
            "Marching Siege Def +40%",
        ],
        "debuffs": [],
        "brain_note": "",
        "bio": "Pharaoh of the 18th Dynasty who prolonged Egypt's golden age.",
    },
    {
        "name": "Tishtrya",
        "gen_type": "mounted",
        "group": "attacker",
        "tagline": "Mounted attacker (marching)",
        "buffs": [
            "Marching Mounted Atk +60%",
            "Marching Mounted HP +60%",
            "Marching Mounted Def +40%",
            "Marching Ground Def +40%",
        ],
        "debuffs": [],
        "brain_note": "",
        "bio": "Zoroastrian deity of Sirius, guardian of rain and life.",
    },
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").casefold()).strip("-") or "general"


CATALOG_BY_LOWER = {entry["name"].casefold(): entry for entry in CATALOG}

SLUG_REGISTRY: dict[str, tuple[str, str]] = {
    slugify(entry["name"]): (entry["name"], entry["gen_type"]) for entry in CATALOG
}


def initials(name: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name or "") if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def render_portrait_svg(name: str, gen_type: str, stars: int | None = None) -> str:
    meta = TYPE_META.get(gen_type, TYPE_META["other"])
    text = initials(name)
    font_size = 150 if len(text) <= 2 else 110
    star_total = 5
    filled = max(0, min(star_total, stars or 0))
    star_y = 355
    gap = 46
    start_x = 200 - gap * (star_total - 1) / 2
    stars_svg = []
    for index in range(star_total):
        cx = start_x + gap * index
        colour = "#f2cc60" if index < filled else "#30363d"
        stars_svg.append(
            f'<text x="{cx:.0f}" y="{star_y}" font-size="34" text-anchor="middle" '
            f'fill="{colour}">★</text>'
        )
    stars_row = "".join(stars_svg) if filled else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" '
        'role="img" aria-label="' + html.escape(name) + '">'
        "<defs>"
        f'<radialGradient id="bg" cx="50%" cy="38%" r="70%">'
        f'<stop offset="0%" stop-color="{meta["ring"]}"/>'
        f'<stop offset="62%" stop-color="{meta["fill"]}"/>'
        f'<stop offset="100%" stop-color="#0b0f14"/>'
        "</radialGradient>"
        "</defs>"
        '<rect width="400" height="400" rx="18" fill="#0d1117"/>'
        f'<circle cx="200" cy="180" r="150" fill="url(#bg)" stroke="{meta["ring"]}" stroke-width="6"/>'
        '<circle cx="200" cy="180" r="150" fill="none" stroke="#0008" stroke-width="2"/>'
        '<circle cx="200" cy="180" r="118" fill="none" stroke="#ffffff26" stroke-width="2"/>'
        f'<text x="200" y="180" font-size="{font_size}" font-family="Inter, system-ui, sans-serif" '
        'font-weight="800" text-anchor="middle" dominant-baseline="central" '
        f'fill="#ffffff" stroke="#0006" stroke-width="1">{html.escape(text)}</text>'
        f'<text x="200" y="315" font-size="30" font-family="Inter, system-ui, sans-serif" '
        f'font-weight="700" letter-spacing="3" text-anchor="middle" fill="{meta["ring"]}">'
        f'{meta["label"].upper()}</text>'
        f"{stars_row}"
        "</svg>"
    )


def _card(general: dict) -> dict:
    meta = TYPE_META.get(general["gen_type"], TYPE_META["other"])
    return {
        "name": general["name"],
        "slug": general["slug"],
        "gen_type": general["gen_type"],
        "type_label": meta["label"],
        "type_glyph": meta["glyph"],
        "type_color": meta["ring"],
        "level": general.get("level"),
        "stars": general.get("stars"),
        "role": general.get("role"),
        "owned": general["owned"],
        "status": general["status"],
        "group": general.get("group"),
        "tagline": general.get("tagline", ""),
        "buffs": general.get("buffs", []),
        "debuffs": general.get("debuffs", []),
        "brain_note": general.get("brain_note", ""),
        "bio": general.get("bio", ""),
        "portrait_url": f"/generals-gallery/portrait/{general['slug']}",
    }


def build_gallery_data(database) -> dict:
    """Merge the curated catalog with the user's owned-generals DB rows."""
    owned_rows: dict[str, dict] = {}
    warning = ""
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name, gen_type, level, stars, role, owned FROM generals"
                )
                for name, gen_type, level, stars, role, owned in cursor.fetchall():
                    if not name:
                        continue
                    owned_rows[name.casefold()] = {
                        "name": name,
                        "gen_type": gen_type,
                        "level": level,
                        "stars": stars,
                        "role": role,
                        "owned": bool(owned),
                    }
    except Exception as error:
        warning = (
            f"Could not read the generals table ({error.__class__.__name__}); "
            "showing catalog only."
        )

    cards: list[dict] = []
    seen_lower: set[str] = set()

    for entry in CATALOG:
        lower = entry["name"].casefold()
        seen_lower.add(lower)
        db_row = owned_rows.get(lower)
        owned = bool(db_row and db_row["owned"])
        recommended = lower in RECOMMENDED_LOWER
        status = "owned" if owned else ("needed" if recommended else "catalog")
        slug = slugify(entry["name"])
        gen_type = db_row["gen_type"] if db_row and db_row.get("gen_type") else entry["gen_type"]
        SLUG_REGISTRY[slug] = (entry["name"], gen_type)
        merged = {
            **entry,
            "slug": slug,
            "owned": owned,
            "status": status,
            "gen_type": gen_type,
            "level": db_row["level"] if db_row else None,
            "stars": db_row["stars"] if db_row else None,
            "role": (db_row["role"] if db_row and db_row.get("role") else entry.get("group")),
        }
        cards.append(_card(merged))

    for lower, row in owned_rows.items():
        if lower in seen_lower or not row["owned"]:
            continue
        slug = slugify(row["name"])
        SLUG_REGISTRY[slug] = (row["name"], row.get("gen_type") or "other")
        cards.append(
            _card(
                {
                    "name": row["name"],
                    "slug": slug,
                    "gen_type": row.get("gen_type") or "other",
                    "group": row.get("role"),
                    "tagline": "Your roster",
                    "buffs": [],
                    "debuffs": [],
                    "brain_note": "",
                    "bio": "",
                    "level": row["level"],
                    "stars": row["stars"],
                    "role": row["role"],
                    "owned": True,
                    "status": "owned",
                }
            )
        )

    owned_cards = [card for card in cards if card["status"] == "owned"]
    needed_walls = [
        card for card in cards if card["status"] == "needed" and card["group"] == "wall"
    ]
    needed_mayors = [
        card
        for card in cards
        if card["status"] == "needed" and card["group"] == "debuff_mayor"
    ]
    other_cards = [card for card in cards if card["status"] == "catalog"]

    owned_cards.sort(key=lambda card: card["name"].casefold())
    sections = [
        {
            "key": "owned",
            "title": "Your roster",
            "subtitle": "Generals recorded in your Murder Bot database.",
            "generals": owned_cards,
        },
        {
            "key": "wall",
            "title": "Recommended walls (defense) — needed",
            "subtitle": "In-city anvil generals to acquire next (pvp_brain §7-8).",
            "generals": needed_walls,
        },
        {
            "key": "debuff_mayor",
            "title": "Recommended debuff mayors — needed",
            "subtitle": "Sub-city mayors that collapse an attacker's siege/ranged buffs (§8, §13E).",
            "generals": needed_mayors,
        },
    ]
    if other_cards:
        sections.append(
            {
                "key": "other",
                "title": "Other catalog generals",
                "subtitle": "Reference cards with verified skill data.",
                "generals": other_cards,
            }
        )

    return {
        "counts": {
            "owned": len(owned_cards),
            "needed": len(needed_walls) + len(needed_mayors),
            "catalog": len(cards),
        },
        "sections": [section for section in sections if section["generals"]],
        "generals": cards,
        "warning": warning,
        "sources": {
            "ownership": "Postgres murderbot.generals (per-user roster)",
            "skills": "evony-hq.com generals API (verified) + game_brain/pvp_brain.md §8/§9/§13",
            "artwork": (
                "Self-hosted generated SVG medallions. Official portrait art is "
                "copyright Top Games Inc.; drop <slug>.png into static/generals/ to "
                "override with real art."
            ),
        },
    }


def _chip(text: str, kind: str) -> str:
    return f'<span class="chip {kind}">{html.escape(text)}</span>'


def _card_html(card: dict) -> str:
    status_class = card["status"]
    status_label = {
        "owned": "OWNED",
        "needed": "NEEDED",
        "catalog": "CATALOG",
    }.get(card["status"], card["status"].upper())

    meta_bits = []
    if card.get("level"):
        meta_bits.append(f"Lv {card['level']}")
    stars = card.get("stars")
    if stars:
        meta_bits.append("★" * int(stars) + "☆" * (5 - int(stars)))
    if card.get("role"):
        meta_bits.append(html.escape(str(card["role"]).replace("_", " ")))
    meta_line = (
        f'<p class="meta">{" &middot; ".join(meta_bits)}</p>' if meta_bits else ""
    )

    buffs = "".join(_chip(text, "buff") for text in card["buffs"])
    debuffs = "".join(_chip(text, "debuff") for text in card["debuffs"])
    chips = ""
    if buffs or debuffs:
        chips = f'<div class="chips">{buffs}{debuffs}</div>'

    tagline = (
        f'<p class="tagline">{html.escape(card["tagline"])}</p>' if card.get("tagline") else ""
    )
    brain = (
        f'<p class="brain">{html.escape(card["brain_note"])}</p>'
        if card.get("brain_note")
        else ""
    )
    bio = f'<p class="bio">{html.escape(card["bio"])}</p>' if card.get("bio") else ""

    return f"""
<article class="gcard {status_class}">
  <div class="portrait">
    <img src="{card['portrait_url']}" alt="{html.escape(card['name'])} portrait" loading="lazy" width="400" height="400">
    <span class="status-badge {status_class}">{status_label}</span>
  </div>
  <div class="body">
    <header class="ghead">
      <h3>{html.escape(card['name'])}</h3>
      <span class="type-pill" style="--pill:{card['type_color']}">{card['type_glyph']} {html.escape(card['type_label'])}</span>
    </header>
    {meta_line}
    {tagline}
    {chips}
    {brain}
    {bio}
  </div>
</article>"""


def _section_html(section: dict) -> str:
    cards = "".join(_card_html(card) for card in section["generals"])
    return f"""
<section class="gsection">
  <div class="section-head">
    <h2>{html.escape(section['title'])} <span class="count">{len(section['generals'])}</span></h2>
    <p class="section-sub">{html.escape(section['subtitle'])}</p>
  </div>
  <div class="ggrid">{cards}</div>
</section>"""


def render_page(data: dict) -> str:
    counts = data["counts"]
    warning = (
        f'<p class="warn">{html.escape(data["warning"])}</p>' if data.get("warning") else ""
    )
    sections = "".join(_section_html(section) for section in data["sections"])
    sources = data["sources"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Generals Gallery — Murder Bot</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }}
main {{ width: min(1200px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }}
a {{ color: #58a6ff; text-decoration: none; }}
header.top {{ display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .75rem; }}
h1 {{ margin: 0; font-size: 1.7rem; }}
.summary {{ display: flex; flex-wrap: wrap; gap: .6rem; margin: 1rem 0 .5rem; }}
.stat {{ padding: .5rem .9rem; background: #161b22; border: 1px solid #30363d; border-radius: 999px; font-size: .9rem; }}
.stat b {{ color: #fff; }}
.warn {{ margin: 1rem 0; padding: .7rem 1rem; color: #d29922; background: #3d2f0b; border: 1px solid #9e6a03; border-radius: 8px; }}
.gsection {{ margin-top: 2.2rem; }}
.section-head h2 {{ margin: 0; font-size: 1.2rem; }}
.section-head .count {{ margin-left: .4rem; padding: .05rem .5rem; font-size: .8rem; color: #adbac7; background: #21262d; border-radius: 999px; vertical-align: middle; }}
.section-sub {{ margin: .3rem 0 1rem; color: #8b949e; font-size: .9rem; }}
.ggrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 1rem; }}
.gcard {{ display: flex; flex-direction: column; background: #161b22; border: 1px solid #30363d; border-radius: 14px; overflow: hidden; }}
.gcard.owned {{ border-color: #238636; }}
.gcard.needed {{ border-color: #9e3b3b; }}
.portrait {{ position: relative; aspect-ratio: 1 / 1; background: #010409; }}
.portrait img {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
.status-badge {{ position: absolute; top: .55rem; left: .55rem; padding: .18rem .55rem; border-radius: 999px; font-size: .7rem; font-weight: 800; letter-spacing: .06em; color: #fff; }}
.status-badge.owned {{ background: #238636; }}
.status-badge.needed {{ background: #b62324; }}
.status-badge.catalog {{ background: #30363d; color: #adbac7; }}
.body {{ padding: .85rem .95rem 1.05rem; display: flex; flex-direction: column; gap: .5rem; }}
.ghead {{ display: flex; align-items: center; justify-content: space-between; gap: .5rem; }}
.ghead h3 {{ margin: 0; font-size: 1.05rem; line-height: 1.2; }}
.type-pill {{ flex: none; padding: .15rem .5rem; font-size: .72rem; font-weight: 700; color: var(--pill); border: 1px solid var(--pill); border-radius: 999px; white-space: nowrap; }}
.meta {{ margin: 0; color: #f2cc60; font-size: .82rem; letter-spacing: .02em; }}
.tagline {{ margin: 0; color: #adbac7; font-size: .85rem; }}
.chips {{ display: flex; flex-wrap: wrap; gap: .32rem; }}
.chip {{ padding: .16rem .5rem; font-size: .74rem; border-radius: 6px; border: 1px solid transparent; }}
.chip.buff {{ color: #3fb950; background: #12261a; border-color: #1c3d28; }}
.chip.debuff {{ color: #ff7b72; background: #2a1615; border-color: #4a2321; }}
.brain {{ margin: .1rem 0 0; padding: .5rem .6rem; font-size: .8rem; line-height: 1.4; color: #d2a8ff; background: #1c1633; border: 1px solid #3a2d63; border-radius: 8px; }}
.bio {{ margin: 0; color: #6e7681; font-size: .78rem; font-style: italic; }}
footer {{ margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid #21262d; color: #6e7681; font-size: .8rem; line-height: 1.6; }}
@media (max-width: 520px) {{
  main {{ padding: 1.25rem 0 3rem; }}
  .ggrid {{ grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: .7rem; }}
  .ghead h3 {{ font-size: .95rem; }}
}}
</style>
</head>
<body>
<main>
<header class="top">
  <div><h1>Generals Gallery</h1><a href="/">&larr; Dashboard</a></div>
</header>
<div class="summary">
  <span class="stat"><b>{counts['owned']}</b> owned</span>
  <span class="stat"><b>{counts['needed']}</b> recommended &amp; needed</span>
  <span class="stat"><b>{counts['catalog']}</b> cards</span>
</div>
{warning}
{sections}
<footer>
  <p><b>Ownership:</b> {html.escape(sources['ownership'])}.</p>
  <p><b>Skills &amp; buff magnitudes:</b> {html.escape(sources['skills'])}.</p>
  <p><b>Artwork:</b> {html.escape(sources['artwork'])}</p>
</footer>
</main>
</body>
</html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the generals-gallery router wired to the host app's auth + DB.

    Parameters
    ----------
    current_user:
        The host app's FastAPI auth dependency (``request -> user_id``).
    database:
        The host app's ``@contextmanager`` yielding a psycopg2 connection.
    """
    router = APIRouter(tags=["generals-gallery"])

    @router.get("/generals-gallery", response_class=HTMLResponse)
    def generals_gallery_page(_user_id: int = Depends(current_user)):
        return HTMLResponse(render_page(build_gallery_data(database)))

    @router.get("/api/generals-gallery")
    def generals_gallery_data(_user_id: int = Depends(current_user)):
        return JSONResponse(build_gallery_data(database))

    @router.get("/generals-gallery/portrait/{slug}")
    def generals_gallery_portrait(slug: str):
        safe = slugify(slug)
        for extension in ("png", "jpg", "jpeg", "webp"):
            candidate = PORTRAIT_DIR / f"{safe}.{extension}"
            if candidate.is_file():
                return FileResponse(candidate)
        name, gen_type = SLUG_REGISTRY.get(safe, (safe.replace("-", " ").title(), "other"))
        svg = render_portrait_svg(name, gen_type)
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return router
