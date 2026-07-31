"""Discovery endpoints and IndexNow payload data for the public guide pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

from game_kb import GameKB
from guides_view import DB_PATH, SITE, best_rating, guide_slug, slugify

INDEXNOW_KEY = "7f3c9a1e2b4d6f8091a3c5e7b9d2f406"
CURATED_GENERALS = ("Akechi Mitsuhide", "Lafayette", "Marcian", "Shaybani", "Visconti")
CURATED_GUIDES = (
    "https://evonyguidewiki.com/en/best-ground-general-en/",
    "https://evonyguidewiki.com/en/best-mounted-general-en/",
    "https://evonyguidewiki.com/en/best-ranged-general-en/",
    "https://evonyguidewiki.com/en/best-siege-general-en/",
    "https://evonyguidewiki.com/en/assistant_general-en/",
)


def _one_line(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def llms_txt() -> str:
    kb = GameKB(DB_PATH)
    try:
        general_lines = []
        for name in CURATED_GENERALS:
            general = kb.get_general(name)
            if not general:
                continue
            rating = best_rating(kb.ratings(general=name))
            rating_text = ""
            if rating:
                role = str(rating.get("role") or "").replace("_", " ")
                rank = f", rank {rating['rank']}" if rating.get("rank") is not None else ""
                rating_text = f" Highest recorded rating: Tier {rating.get('tier') or 'unranked'} {role}{rank}."
            summary = (f"{general.get('quality') or 'Quality not recorded'} {general.get('gtype')} general. "
                       f"Recorded best use: {general.get('best_use') or 'not available'}.{rating_text}")
            general_lines.append(f"- {SITE}/generals/{slugify(name)}: {_one_line(summary)}")

        guides = {guide.get("url"): guide for guide in kb.guides()}
        guide_lines = []
        for source_url in CURATED_GUIDES:
            guide = guides.get(source_url)
            if guide:
                guide_lines.append(
                    f"- {SITE}/guides/{guide_slug(guide)}: "
                    f"{_one_line(guide.get('summary') or guide.get('title'))}"
                )
    finally:
        kb.close()

    return "\n".join((
        "# Murder Bot Evony Guides",
        "Server-rendered Evony reference for general types, recorded tier ratings, counters, and strategy guides.",
        "",
        "## Top general profiles",
        *general_lines,
        "",
        "## Top strategy guides",
        *guide_lines,
        "",
    ))


def build_indexnow_payload(urls) -> dict:
    site_host = urlparse(SITE).netloc
    url_list = []
    for url in urls:
        parsed = urlparse(urljoin(f"{SITE}/", str(url)))
        if parsed.scheme != "https" or parsed.netloc != site_host:
            raise ValueError(f"IndexNow URL must belong to {site_host}")
        clean = urlunparse(parsed._replace(fragment=""))
        if clean not in url_list:
            url_list.append(clean)
    return {
        "host": site_host,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE}/{INDEXNOW_KEY}.txt",
        "urlList": url_list,
    }
