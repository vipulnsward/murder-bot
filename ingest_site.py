"""Bulk-ingest Evony Guide Wiki pages into the local game knowledge base."""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

from crawl_evony import fetch
from game_kb import GameKB


URL_RE = re.compile(r"https?://[^\s)>]+")
HEADER_RE = re.compile(r"^##\s+(.+?)\s*$")


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def _url_slug(url: str) -> str:
    return _slug(unquote(urlsplit(url).path).strip("/"))


def parse_sitemap(path) -> list[tuple[str, str]]:
    guides = []
    seen = set()
    category = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if match := HEADER_RE.match(line):
            name = re.sub(r"\s*\(\d+\)\s*$", "", match.group(1))
            category = _slug(name)
            continue
        if category:
            for url in URL_RE.findall(line):
                if url not in seen:
                    seen.add(url)
                    guides.append((url, category))
    return guides


def _record(markdown: str, url: str, category: str) -> dict:
    marker = re.search(r"^Markdown Content:\s*$", markdown, re.MULTILINE | re.IGNORECASE)
    body = markdown[marker.end():].strip() if marker else markdown.strip()
    title_match = re.search(r"^Title:\s*(.+?)\s*$", markdown, re.MULTILINE | re.IGNORECASE)
    heading_match = re.search(r"^#{1,6}\s+(.+?)\s*#*\s*$", body, re.MULTILINE)
    title = (title_match or heading_match).group(1).strip() if title_match or heading_match else ""
    summary = ""
    for paragraph in re.split(r"\n\s*\n+", body):
        paragraph = " ".join(line.strip() for line in paragraph.splitlines()).strip()
        if len(paragraph) >= 30 and re.search(r"[A-Za-z]{3}", paragraph) and not re.match(
            r"^(?:#{1,6}\s|[-*+]\s|\d+\.\s|!\[|\[.+\]\(.+\)$|[>|`])", paragraph
        ):
            summary = paragraph
            break
    return {
        "id": _url_slug(url),
        "title": title,
        "url": url,
        "category": category,
        "summary": summary,
        "content": body[:1500],
    }


def ingest(
    sitemap="data/evonyguidewiki-sitemap.md",
    pages_dir="data/pages",
    out="data/site_guides.jsonl",
    db_path="game_brain/game_kb.db",
    limit=None,
    delay=1.0,
):
    pages = Path(pages_dir)
    output = Path(out)
    pages.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if output.exists():
        with output.open(encoding="utf-8") as source:
            for line in source:
                try:
                    if url := json.loads(line).get("url"):
                        existing.add(url)
                except (json.JSONDecodeError, AttributeError):
                    pass

    entries = parse_sitemap(sitemap)
    if limit is not None:
        entries = entries[:limit]
    fetched = skipped = failed = 0
    failures = []
    with output.open("a", encoding="utf-8") as sink:
        for processed, (url, category) in enumerate(entries, 1):
            page = pages / f"{_url_slug(url)}.md"
            if page.exists():
                skipped += 1
                markdown = page.read_text(encoding="utf-8")
            else:
                try:
                    markdown = fetch(url)
                    page.write_text(markdown, encoding="utf-8")
                    fetched += 1
                except Exception as error:
                    failed += 1
                    failures.append((url, str(error)))
                    print(f"FAILED {url}: {error}", flush=True)
                    time.sleep(delay)
                    continue
                time.sleep(delay)
            if url not in existing:
                sink.write(json.dumps(_record(markdown, url, category), ensure_ascii=False) + "\n")
                sink.flush()
                existing.add(url)
            if processed % 10 == 0 or processed == len(entries):
                print(
                    f"Progress {processed}/{len(entries)}: fetched={fetched} skipped={skipped} failed={failed}",
                    flush=True,
                )

    kb = GameKB(db_path)
    loaded = set()
    with output.open(encoding="utf-8") as source:
        for line in source:
            try:
                record = json.loads(line)
                if record["url"] in loaded:
                    continue
                loaded.add(record["url"])
                kb.add_guide(
                    record["title"],
                    record["url"],
                    record.get("category"),
                    record.get("summary"),
                    record.get("content"),
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                print(f"FAILED JSONL record: {error}", flush=True)
    stats = kb.stats()
    kb.close()
    print(f"FINAL fetched={fetched} skipped={skipped} failed={failed} stats={stats}", flush=True)
    return {"fetched": fetched, "skipped": skipped, "failed": failed, "failures": failures, "stats": stats}


if __name__ == "__main__":
    ingest(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
