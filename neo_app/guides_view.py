"""Public, server-rendered Evony guides and general reference pages."""

from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from counter_general import recommend_counters
from game_kb import GameKB

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static" / "guides"
DB_PATH = BASE_DIR.parent / "game_brain" / "game_kb.db"
SITE = "https://murderbot.vipulnsward.com"
SITEMAP_FALLBACK_LASTMOD = "2026-07-21"
static_files = StaticFiles(directory=STATIC_DIR)

IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
TIER_SCORE = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
MARKDOWN_TOKEN = re.compile(
    r"!\[([^\]]*)\]\((https?://[^\s)]+)(?:\s+[\"'][^)]*[\"'])?\)"
    r"|\[([^\]]+)\]\(([^)\s]+)(?:\s+[\"'][^)]*[\"'])?\)"
    r"|(\*\*|__)(.+?)\5"
    r"|`([^`]+)`"
)
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^\s)]+)")

CSS = """
<style>
:root{color-scheme:dark;--bg:#090705;--panel:#171109;--panel2:#21170c;--line:#4b3618;
 --ink:#f3ead6;--mut:#bbaa88;--gold:#e6c35c;--gold2:#ffe79a;--ember:#d34a2f;
 font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;min-height:100vh;color:var(--ink);background:
 radial-gradient(900px 480px at 85% -10%,rgba(211,74,47,.2),transparent 60%),
 radial-gradient(1000px 520px at 5% 0,rgba(230,195,92,.12),transparent 62%),var(--bg)}
a{color:var(--gold2);text-decoration:none}a:hover{color:#fff2bc}
.shell{width:min(1180px,92vw);margin:auto}.topbar{position:sticky;top:0;z-index:20;
 backdrop-filter:blur(16px);background:rgba(9,7,5,.86);border-bottom:1px solid rgba(230,195,92,.2)}
.nav{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:1rem}
.brand{font:700 1.05rem Georgia,serif;letter-spacing:.12em;color:var(--gold)}
.links{display:flex;gap:.4rem}.links a{padding:.5rem .72rem;border-radius:8px;color:var(--mut)}
.links a:hover{background:rgba(230,195,92,.08);color:var(--gold2)}
main{padding:2.3rem 0 4.5rem}.eyebrow{text-transform:uppercase;letter-spacing:.18em;font-size:.74rem;
 font-weight:800;color:var(--ember)}h1,h2,h3{font-family:Georgia,"Iowan Old Style",serif;line-height:1.15}
h1{font-size:clamp(2.1rem,6vw,4.6rem);max-width:900px;margin:.3rem 0 .8rem;color:var(--gold2)}
h2{font-size:clamp(1.55rem,3vw,2.35rem);color:var(--gold);margin:2.4rem 0 1rem}
h3{color:#f3d77f}.lede{max-width:780px;font-size:1.08rem;line-height:1.75;color:var(--mut)}
.hero{padding:2.2rem 0}.hero-grid{display:grid;gap:1.5rem}.hero-image{width:100%;max-height:520px;
 object-fit:cover;object-position:top;border:1px solid var(--line);border-radius:18px;
 box-shadow:0 24px 70px -34px #000}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:1rem}
.card{display:flex;flex-direction:column;min-width:0;overflow:hidden;border:1px solid var(--line);
 border-radius:15px;background:linear-gradient(155deg,rgba(41,28,13,.94),rgba(15,11,7,.98));
 box-shadow:0 20px 50px -34px #000;transition:transform .16s ease,border-color .16s ease}
.card:hover{transform:translateY(-4px);border-color:#9f7430}.card img{width:100%;height:190px;object-fit:cover;
 object-position:top;background:#100c08}.portrait img{height:270px}.card-body{padding:1rem;display:flex;
 flex:1;flex-direction:column}.card h3{margin:.2rem 0 .55rem;font-size:1.15rem}.card p{margin:0;
 color:var(--mut);font-size:.91rem;line-height:1.55}.card .more{margin-top:auto;padding-top:.8rem;font-weight:800}
.section-head{display:flex;align-items:end;justify-content:space-between;gap:1rem;border-bottom:1px solid var(--line)}
.count{color:var(--mut);font-size:.85rem}.badge{display:inline-block;padding:.2rem .55rem;border-radius:999px;
 font-size:.7rem;font-weight:900;letter-spacing:.06em;text-transform:uppercase;background:#382713;color:#e8cf8a}
.badge.s{background:#6d4611;color:#fff0a2}.badge.a{background:#325c45;color:#bcffd9}
.badge.b{background:#304a72;color:#d5e6ff}.badge.c,.badge.d{background:#403b35;color:#ddd}
.badges{display:flex;gap:.35rem;flex-wrap:wrap}.filters{display:grid;grid-template-columns:2fr repeat(3,1fr);
 gap:.65rem;margin:1.5rem 0;padding:1rem;border:1px solid var(--line);border-radius:13px;background:rgba(27,18,9,.75)}
input,select{min-width:0;width:100%;padding:.72rem .8rem;border:1px solid #59411f;border-radius:8px;
 background:#0c0906;color:var(--ink)}.article{max-width:820px;padding:1.2rem clamp(1rem,4vw,2.2rem);
 border:1px solid var(--line);border-radius:16px;background:rgba(19,14,9,.9);line-height:1.75}
.article p,.article li{color:#d7cbb4}.article img{display:block;max-width:100%;height:auto;margin:1.2rem auto;
 border-radius:10px}.article pre{overflow:auto;padding:1rem;background:#080604;border:1px solid var(--line)}
.article code{padding:.12rem .3rem;border-radius:4px;background:#090705;color:#f1d77e}
.article blockquote{margin:1rem 0;padding:.2rem 1rem;border-left:3px solid var(--gold);color:var(--mut)}
.article hr{border:0;border-top:1px solid var(--line)}.detail-grid{display:grid;gap:1.2rem}
.panel{padding:1.1rem;border:1px solid var(--line);border-radius:14px;background:rgba(25,17,9,.84)}
.panel h2,.panel h3{margin-top:0}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.7rem}
.stat{padding:.85rem;border-radius:10px;background:#0d0906;border:1px solid #3c2c18}.stat small{display:block;
 color:var(--mut);text-transform:uppercase;letter-spacing:.1em}.stat strong{display:block;margin-top:.3rem}
.clean{padding-left:1.15rem}.source{margin-top:2rem;color:var(--mut);font-size:.85rem}
.quick-answer{margin-bottom:1rem;border-color:#9f7430;background:linear-gradient(135deg,rgba(62,42,16,.96),rgba(25,17,9,.94))}
.quick-answer h2{margin:0 0 .55rem}.quick-answer p{margin:0;color:var(--ink);font-size:1.05rem;line-height:1.7}
.empty{display:none}.no-results{display:none;color:var(--mut);padding:1rem 0}.no-results.show{display:block}
footer{padding:2rem 0;border-top:1px solid var(--line);color:var(--mut);font-size:.85rem}
@media(min-width:760px){.hero-grid{grid-template-columns:minmax(0,1.25fr) minmax(280px,.75fr);align-items:center}
 .detail-grid{grid-template-columns:minmax(0,1.35fr) minmax(270px,.65fr)}}
@media(max-width:680px){.filters{grid-template-columns:1fr 1fr}.filters input{grid-column:1/-1}
 .links a:first-child{display:none}.portrait img{height:230px}}
</style>
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def slugify(value) -> str:
    value = str(value or "").casefold().replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def guide_slug(guide) -> str:
    path_slug = urlparse(guide.get("url") or "").path.strip("/").split("/")[-1]
    return slugify(path_slug or guide.get("title"))


def safe_url(value) -> str | None:
    try:
        parsed = urlparse(str(value))
    except (TypeError, ValueError):
        return None
    return str(value) if parsed.scheme in {"http", "https"} and parsed.netloc else None


def safe_image_url(value) -> str | None:
    clean = safe_url(value)
    if not clean or "/gtranslate/" in clean:
        return None
    return clean if re.search(r"\.(?:png|jpe?g|webp)(?:[?#].*)?$", clean, re.I) else None


def local_image(source_url) -> str | None:
    slug = slugify(urlparse(source_url or "").path.strip("/").split("/")[-1])
    for extension in IMAGE_EXTENSIONS:
        if (STATIC_DIR / f"{slug}.{extension}").is_file():
            return f"/static/guides/{slug}.{extension}"
    return None


def content_images(markdown) -> list[str]:
    images = []
    for _alt, url in MARKDOWN_IMAGE.findall(str(markdown or "")):
        clean = safe_image_url(url)
        if clean and clean not in images:
            images.append(clean)
    return images


def image_for(source_url, markdown=None) -> str:
    return local_image(source_url) or next(iter(content_images(markdown)), "/static/guides/placeholder.svg")


def general_image(name, source_url) -> str:
    slug = slugify(name)
    for extension in IMAGE_EXTENSIONS:
        if (STATIC_DIR / "generals" / f"{slug}.{extension}").is_file():
            return f"/static/guides/generals/{slug}.{extension}"
    return image_for(source_url)


def inline_markdown(value) -> str:
    text = str(value or "")
    output, position = [], 0
    for match in MARKDOWN_TOKEN.finditer(text):
        output.append(esc(text[position:match.start()]))
        image_alt, image_url, link_text, link_url, strong_mark, strong_text, code = match.groups()
        if image_url:
            clean = safe_image_url(image_url)
            if clean:
                output.append(f'<img src="{esc(clean)}" alt="{esc(image_alt or "Evony guide image")}" loading="lazy">')
            else:
                output.append(esc(image_alt))
        elif link_url:
            clean = safe_url(link_url)
            output.append(
                f'<a href="{esc(clean)}" rel="nofollow noopener">{esc(link_text)}</a>'
                if clean else esc(link_text)
            )
        elif strong_mark:
            output.append(f"<strong>{esc(strong_text)}</strong>")
        else:
            output.append(f"<code>{esc(code)}</code>")
        position = match.end()
    output.append(esc(text[position:]))
    return "".join(output)


def render_markdown(markdown) -> str:
    """Render a small safe Markdown subset; unmatched/raw HTML is escaped."""
    output, paragraph, list_tag = [], [], None
    in_code, code_lines = False, []

    def flush_paragraph():
        if paragraph:
            output.append(f"<p>{inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_tag
        if list_tag:
            output.append(f"</{list_tag}>")
            list_tag = None

    for line in str(markdown or "").splitlines():
        if line.strip().startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                output.append(f"<pre><code>{esc(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        bullet = re.match(r"^[-*+]\s+(.+)$", stripped)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1)) + 1
            output.append(f"<h{level}>{inline_markdown(heading.group(2))}</h{level}>")
        elif bullet or numbered:
            flush_paragraph()
            wanted = "ul" if bullet else "ol"
            if list_tag != wanted:
                close_list()
                output.append(f"<{wanted}>")
                list_tag = wanted
            output.append(f"<li>{inline_markdown((bullet or numbered).group(1))}</li>")
        elif stripped.startswith(">"):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote>{inline_markdown(stripped.lstrip('> '))}</blockquote>")
        elif re.fullmatch(r"[-*_]{3,}", stripped):
            flush_paragraph()
            close_list()
            output.append("<hr>")
        else:
            paragraph.append(stripped)
    if in_code:
        output.append(f"<pre><code>{esc(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    close_list()
    return "".join(output)


def json_script(data) -> str:
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def meta_description(value, fallback) -> str:
    text = re.sub(r"\s+", " ", str(value or fallback)).strip()
    return text[:157].rstrip() + ("…" if len(text) > 157 else "")


def iso_date(value) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def page(title, description, canonical, body, *, image=None, schema=None) -> str:
    absolute_image = f"{SITE}{image}" if image and image.startswith("/") else image
    og_image = f'<meta property="og:image" content="{esc(absolute_image)}">' if absolute_image else ""
    schemas = schema if isinstance(schema, list) else [schema] if schema else []
    ld = "".join(f'<script type="application/ld+json">{json_script(item)}</script>' for item in schemas)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}"><meta property="og:type" content="article">
<meta property="og:site_name" content="Murder Bot Evony Guides"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(canonical)}">{og_image}
{ld}{CSS}</head><body><div class="topbar"><nav class="shell nav"><a class="brand" href="/guides">EVONY INTELLIGENCE</a>
<div class="links"><a href="/guides">Guides</a><a href="/generals">Generals</a><a href="/">Murder Bot</a></div></nav></div>
<main class="shell">{body}</main><footer><div class="shell">Independent Evony strategy reference · Data sourced from public guide research.</div></footer>
</body></html>"""


def kb_data():
    return GameKB(DB_PATH)


def ratings_by_general(kb) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for rating in kb.ratings():
        grouped[rating["general"]].append(rating)
    return grouped


def best_rating(ratings) -> dict | None:
    return max(
        ratings or [],
        key=lambda item: (TIER_SCORE.get(str(item.get("tier") or "").upper(), 0), -(item.get("rank") or 999)),
        default=None,
    )


def breadcrumb_schema(section: str, label: str, canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": section, "item": f"{SITE}/{section.casefold()}"},
            {"@type": "ListItem", "position": 3, "name": label, "item": canonical},
        ],
    }


def general_answers(general, ratings, recommendations) -> tuple[str, dict]:
    name = str(general["name"])
    gtype = str(general.get("gtype") or "other")
    quality = str(general.get("quality") or "quality not recorded")
    rating = best_rating(ratings)
    tier_text = f"Tier {rating['tier']}" if rating and rating.get("tier") else "no recorded tier rating"
    role_text = str((rating or {}).get("role") or "").replace("_", " ").title()
    rank_text = f" (rank {rating['rank']})" if rating and rating.get("rank") is not None else ""
    first = f"{name} is a {quality} {gtype} general with {tier_text}"
    first += f" for {role_text}{rank_text}." if role_text else "."
    best_use = general.get("best_use")
    second = (f"The recorded best use for {name} is {best_use}." if best_use
              else f"The knowledge base does not record a best use for {name}.")
    counter_names = [str(item["general"]) for item in recommendations]
    third = (f"The top rated counter generals are {', '.join(counter_names)}."
             if counter_names else f"No rated counter generals are recorded for {name}'s {gtype} type.")

    counter_answer = (f"The top rated counters for {name} are {', '.join(counter_names)}."
                      if counter_names else f"No rated counter generals are recorded for {name}'s {gtype} type.")
    pvp_ratings = [item for item in ratings if str(item.get("role") or "").endswith(("_attack", "_defense"))]
    pvp_rating = best_rating(pvp_ratings)
    if pvp_rating:
        pvp_role = str(pvp_rating.get("role") or "").replace("_", " ").title()
        pvp_rank = f" (rank {pvp_rating['rank']})" if pvp_rating.get("rank") is not None else ""
        pvp_answer = f"{name} is rated Tier {pvp_rating.get('tier') or 'unranked'} for {pvp_role}{pvp_rank}."
        if best_use:
            pvp_answer += f" Its recorded best use is {best_use}."
    else:
        pvp_answer = f"The current data has no PvP attack or defense tier rating recorded for {name}."
    questions = [
        {"@type": "Question", "name": f"Who counters {name} in Evony?",
         "acceptedAnswer": {"@type": "Answer", "text": counter_answer}},
        {"@type": "Question", "name": f"What troop type is {name}?",
         "acceptedAnswer": {"@type": "Answer", "text": f"{name} is classified as a {gtype} general."}},
        {"@type": "Question", "name": f"Is {name} good for PvP?",
         "acceptedAnswer": {"@type": "Answer", "text": pvp_answer}},
    ]
    return " ".join((first, second, third)), {
        "@context": "https://schema.org", "@type": "FAQPage", "mainEntity": questions,
    }


def guide_card(guide) -> str:
    slug = guide_slug(guide)
    image = image_for(guide.get("url"), guide.get("content"))
    return f"""<article class="card"><img src="{esc(image)}" alt="{esc(guide.get('title'))}" loading="lazy">
<div class="card-body"><span class="badge">{esc(guide.get('category') or 'Guide')}</span>
<h3><a href="/guides/{esc(slug)}">{esc(guide.get('title'))}</a></h3>
<p>{esc(meta_description(guide.get('summary'), 'Practical Evony strategy and reference guide.'))}</p>
<a class="more" href="/guides/{esc(slug)}">Read guide →</a></div></article>"""


def general_card(general, rating) -> str:
    slug = slugify(general.get("name"))
    tier = str((rating or {}).get("tier") or "Unrated").upper()
    image = general_image(general.get("name"), general.get("source_url"))
    quality = general.get("quality") or "Unknown"
    gtype = general.get("gtype") or "Other"
    return f"""<article class="card portrait general-card" data-name="{esc(general.get('name')).casefold()}"
 data-type="{esc(gtype).casefold()}" data-quality="{esc(quality).casefold()}" data-tier="{esc(tier).casefold()}">
<img src="{esc(image)}" alt="{esc(general.get('name'))} Evony general portrait" loading="lazy">
<div class="card-body"><div class="badges"><span class="badge">{esc(gtype)}</span>
<span class="badge">{esc(quality)}</span><span class="badge {esc(tier.casefold())}">{esc(tier)}</span></div>
<h3><a href="/generals/{esc(slug)}">{esc(general.get('name'))}</a></h3>
<p>{esc(general.get('best_use') or general.get('skill') or 'Evony general stats, skills, and tier ratings.')}</p>
<a class="more" href="/generals/{esc(slug)}">View build →</a></div></article>"""


def render_value_list(values) -> str:
    if not values:
        return '<p class="count">No data available.</p>'
    items = []
    for value in values if isinstance(values, list) else [values]:
        if isinstance(value, dict):
            label = value.get("context") or value.get("source_label") or "Ascending"
            effects = value.get("effects") or []
            detail = "; ".join(str(item) for item in effects) if isinstance(effects, list) else str(effects)
            items.append(f"<li><strong>{esc(label)}:</strong> {esc(detail)}</li>")
        else:
            items.append(f"<li>{esc(value)}</li>")
    return f'<ul class="clean">{"".join(items)}</ul>'


def sitemap_entries() -> list[tuple[str, str]]:
    kb = kb_data()
    try:
        guides = kb.guides()
        generals = kb.list_generals()
    finally:
        kb.close()
    guide_dates = [iso_date(guide.get("updated_at")) for guide in guides]
    general_dates = [iso_date(general.get("updated_at")) for general in generals]
    return [
        ("/guides", max(filter(None, guide_dates), default=SITEMAP_FALLBACK_LASTMOD)),
        ("/generals", max(filter(None, general_dates), default=SITEMAP_FALLBACK_LASTMOD)),
        *((f"/guides/{guide_slug(guide)}", iso_date(guide.get("updated_at")) or SITEMAP_FALLBACK_LASTMOD)
          for guide in guides),
        *((f"/generals/{slugify(general['name'])}", iso_date(general.get("updated_at")) or SITEMAP_FALLBACK_LASTMOD)
          for general in generals),
    ]


def sitemap_paths() -> list[str]:
    return [path for path, _lastmod in sitemap_entries()]


def build_router() -> APIRouter:
    router = APIRouter(tags=["public-guides"])

    @router.get("/guides", response_class=HTMLResponse)
    def guides_index():
        kb = kb_data()
        try:
            grouped = defaultdict(list)
            for guide in kb.guides():
                grouped[guide.get("category") or "other"].append(guide)
        finally:
            kb.close()
        sections = []
        for category in sorted(grouped):
            cards = "".join(guide_card(guide) for guide in grouped[category])
            sections.append(
                f'<section id="{esc(slugify(category))}"><div class="section-head"><h2>{esc(category.title())}</h2>'
                f'<span class="count">{len(grouped[category])} guides</span></div><div class="grid">{cards}</div></section>'
            )
        category_links = "".join(
            f'<a class="badge" href="#{esc(slugify(category))}">{esc(category.title())}</a>'
            for category in sorted(grouped)
        )
        body = f"""<header class="hero"><p class="eyebrow">192 field-tested references</p>
<h1>Evony Guides for Smarter Builds and Better Battles</h1>
<p class="lede">Research-backed guides for generals, PvP, monsters, city growth, events, and every decision that compounds.</p></header>
<nav class="badges" aria-label="Guide categories">{category_links}</nav>
{"".join(sections)}"""
        return HTMLResponse(page(
            "Best Evony Guides for PvP, Generals & City Growth",
            "Browse 192 Evony guides covering the best generals, PvP counters, monsters, events, buffs, and efficient city growth.",
            f"{SITE}/guides",
            body,
        ))

    @router.get("/guides/{slug}", response_class=HTMLResponse)
    def guide_detail(slug: str):
        kb = kb_data()
        try:
            guides = kb.guides()
            guide = next((item for item in guides if guide_slug(item) == slug), None)
            if not guide:
                raise HTTPException(status_code=404, detail="Guide not found")
            related = [
                item for item in guides
                if item["id"] != guide["id"] and item.get("category") == guide.get("category")
            ][:6]
        finally:
            kb.close()
        title = str(guide.get("title") or "Evony Guide")
        search_title = re.split(r"\s*\|\s*Evony:", title, maxsplit=1)[0].strip()
        description = meta_description(guide.get("summary"), f"Practical strategy for {title}.")
        canonical = f"{SITE}/guides/{slug}"
        image = image_for(guide.get("url"), guide.get("content"))
        related_html = "".join(guide_card(item) for item in related)
        schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": description,
            "mainEntityOfPage": canonical,
            "url": canonical,
            "author": {"@type": "Organization", "name": "Murder Bot Evony Guides"},
            "publisher": {"@type": "Organization", "name": "Murder Bot"},
            "dateModified": iso_date(guide.get("updated_at")),
        }
        if image:
            schema["image"] = f"{SITE}{image}" if image.startswith("/") else image
        body = f"""<header class="hero hero-grid"><div><p class="eyebrow">{esc(guide.get('category') or 'Evony guide')}</p>
<h1>{esc(title)}</h1><p class="lede">{esc(guide.get('summary') or description)}</p></div>
<img class="hero-image" src="{esc(image)}" alt="{esc(title)}" fetchpriority="high"></header>
<div class="detail-grid"><article class="article">{render_markdown(guide.get('content'))}
<p class="source">Original research source: <a href="{esc(safe_url(guide.get('url')) or '#')}" rel="nofollow noopener">Evony Guide Wiki</a></p>
</article><aside><div class="panel"><h3>Guide intel</h3><div class="stats">
<div class="stat"><small>Category</small><strong>{esc(guide.get('category') or 'Guide')}</strong></div>
<div class="stat"><small>Updated</small><strong>{esc(iso_date(guide.get('updated_at')) or 'Current')}</strong></div>
</div></div></aside></div><section><div class="section-head"><h2>Related Evony Guides</h2></div>
<div class="grid">{related_html}</div></section>"""
        return HTMLResponse(page(
            f"{search_title} | Evony Guide", description, canonical, body, image=image,
            schema=[schema, breadcrumb_schema("Guides", title, canonical)],
        ))

    @router.get("/generals", response_class=HTMLResponse)
    def generals_index():
        kb = kb_data()
        try:
            generals = kb.list_generals()
            rating_map = ratings_by_general(kb)
        finally:
            kb.close()
        types = sorted({str(g.get("gtype") or "Other") for g in generals})
        qualities = sorted({str(g.get("quality") or "Unknown") for g in generals})
        cards = "".join(general_card(g, best_rating(rating_map.get(g["name"]))) for g in generals)
        options_type = "".join(f'<option value="{esc(v.casefold())}">{esc(v.title())}</option>' for v in types)
        options_quality = "".join(f'<option value="{esc(v.casefold())}">{esc(v)}</option>' for v in qualities)
        body = f"""<header class="hero"><p class="eyebrow">303 general profiles</p><h1>Evony Generals: Skills, Tiers, and Best Uses</h1>
<p class="lede">Compare every tracked Evony general by troop type, quality, role, skills, ascension, and ranked tier.</p></header>
<div class="filters"><input id="general-search" type="search" placeholder="Search generals…" aria-label="Search generals">
<select id="type-filter" aria-label="Filter by troop type"><option value="">All types</option>{options_type}</select>
<select id="quality-filter" aria-label="Filter by quality"><option value="">All qualities</option>{options_quality}</select>
<select id="tier-filter" aria-label="Filter by tier"><option value="">All tiers</option>
<option value="s">Tier S</option><option value="a">Tier A</option><option value="b">Tier B</option>
<option value="c">Tier C</option><option value="d">Tier D</option><option value="unrated">Unrated</option></select></div>
<p id="no-results" class="no-results">No generals match those filters.</p><div class="grid" id="general-grid">{cards}</div>
<script>
const controls=[...document.querySelectorAll(".filters input,.filters select")],cards=[...document.querySelectorAll(".general-card")];
function filterGenerals(){{const q=document.querySelector("#general-search").value.toLowerCase(),type=document.querySelector("#type-filter").value,
quality=document.querySelector("#quality-filter").value,tier=document.querySelector("#tier-filter").value;let shown=0;
cards.forEach(card=>{{const ok=(!q||card.dataset.name.includes(q))&&(!type||card.dataset.type===type)&&
(!quality||card.dataset.quality===quality)&&(!tier||card.dataset.tier===tier);card.hidden=!ok;if(ok)shown++;}});
document.querySelector("#no-results").classList.toggle("show",!shown);}} controls.forEach(control=>control.addEventListener("input",filterGenerals));
</script>"""
        return HTMLResponse(page(
            "Best Evony Generals: Tier List, Skills & Uses",
            "Explore 303 Evony generals with type, quality, tier ratings, skills, specialties, ascension buffs, and best-use recommendations.",
            f"{SITE}/generals",
            body,
        ))

    @router.get("/generals/{slug}", response_class=HTMLResponse)
    def general_detail(slug: str):
        kb = kb_data()
        try:
            all_generals = kb.list_generals()
            general = next((item for item in all_generals if slugify(item.get("name")) == slug), None)
            if not general:
                raise HTTPException(status_code=404, detail="General not found")
            ratings = kb.ratings(general=general["name"])
            counters = recommend_counters(general.get("gtype"), kb=kb)
            related = [guide for guide in kb.guides() if guide.get("url") == general.get("source_url")][:3]
        finally:
            kb.close()
        name = str(general["name"])
        gtype = str(general.get("gtype") or "other")
        canonical = f"{SITE}/generals/{slug}"
        image = general_image(name, general.get("source_url"))
        rating_html = "".join(
            f'<li><span class="badge {esc(str(r.get("tier") or "").casefold())}">{esc(r.get("tier") or "—")}</span> '
            f'<strong>{esc(str(r.get("role") or "").replace("_", " ").title())}</strong>'
            f' · rank {esc(r.get("rank") or "—")}<br><span class="count">{esc(r.get("context") or "")}</span></li>'
            for r in ratings
        ) or '<li class="count">No tier rating available.</li>'
        valid_names = {item["name"] for item in all_generals}
        recommendations = [
            item for item in counters.get("recommendations") or [] if item.get("general") in valid_names
        ]
        counter_names = [str(item["general"]) for item in recommendations]
        rating = best_rating(ratings)
        tier = f"Tier {rating['tier']} " if rating and rating.get("tier") else ""
        if counter_names:
            description = meta_description(
                f"How to counter {name} in Evony: use {', '.join(counter_names[:3])}. "
                f"{name} is a {tier}{gtype} general best used for {general.get('best_use') or 'an unrecorded role'}.",
                f"{name} Evony counter and general guide.",
            )
        else:
            description = meta_description(
                f"{name} is a {tier}{gtype} Evony general. "
                f"Recorded best use: {general.get('best_use') or 'not available'}.",
                f"{name} Evony general guide.",
            )
        counter_html = "".join(
            f'<li><a href="/generals/{esc(slugify(pick.get("general")))}"><strong>{esc(pick.get("general"))}</strong></a> '
            f'<span class="badge {esc(str(pick.get("tier") or "").casefold())}">{esc(pick.get("tier") or "—")}</span>'
            f'<br>{esc(pick.get("why"))}</li>' for pick in recommendations
        ) or '<li class="count">No rated counter recommendations are available for this role.</li>'
        quick_answer, faq_schema = general_answers(general, ratings, recommendations)
        person_schema = {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": name,
            "description": description,
            "url": canonical,
            "image": f"{SITE}{image}" if image.startswith("/") else image,
        }
        related_html = "".join(guide_card(guide) for guide in related)
        related_section = (f'<section><div class="section-head"><h2>Related Evony Guide</h2></div>'
                           f'<div class="grid">{related_html}</div></section>') if related_html else ""
        body = f"""<section class="quick-answer panel" aria-labelledby="quick-answer"><h2 id="quick-answer">Quick answer</h2>
<p>{esc(quick_answer)}</p></section>
<header class="hero hero-grid"><div><p class="eyebrow">Evony {esc(gtype)} general guide</p><h1>{esc(name)}</h1>
<p class="lede">{esc(description)}</p><div class="badges"><span class="badge">{esc(gtype)}</span>
<span class="badge">{esc(general.get('quality') or 'Unknown quality')}</span>
{'<span class="badge">Debuff general</span>' if general.get('is_debuff') else ''}</div></div>
<img class="hero-image" src="{esc(image)}" alt="{esc(name)} Evony general portrait" fetchpriority="high"></header>
<div class="detail-grid"><div><section class="panel"><h2>Skills & Best Use</h2>
<div class="stats"><div class="stat"><small>Main skill</small><strong>{esc(general.get('skill') or 'Not recorded')}</strong></div>
<div class="stat"><small>Best use</small><strong>{esc(general.get('best_use') or 'Flexible role')}</strong></div></div>
{f'<p>{esc(general.get("notes"))}</p>' if general.get('notes') else ''}</section>
<section class="panel"><h2>Specialties</h2>{render_value_list(general.get('specialties'))}</section>
<section class="panel"><h2>Ascending Bonuses</h2>{render_value_list(general.get('ascending'))}</section></div>
<aside><section class="panel"><h2>Tier Ratings</h2><ul class="clean">{rating_html}</ul></section>
<section class="panel"><h2>Best Counters</h2><p class="count">Recommended against a {esc(gtype)} lead.</p>
<ol class="clean">{counter_html}</ol></section></aside></div>
{related_section}<p class="source">Research source: <a href="{esc(safe_url(general.get('source_url')) or '#')}" rel="nofollow noopener">Evony Guide Wiki</a></p>"""
        return HTMLResponse(page(
            f"{name} Counter: Best Counters, Tier & Build | Evony", description, canonical, body, image=image,
            schema=[person_schema, faq_schema, breadcrumb_schema("Generals", name, canonical)],
        ))

    return router


def _self_check():
    rendered = render_markdown('# Safe\n<script>alert("x")</script> **bold** [bad](javascript:alert(1))')
    assert "&lt;script&gt;" in rendered and "<script>" not in rendered
    assert "javascript:" not in rendered and "<strong>bold</strong>" in rendered
    assert slugify("Lorenzo de’ Medici") == "lorenzo-de-medici"


if __name__ == "__main__":
    _self_check()
