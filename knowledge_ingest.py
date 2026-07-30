"""knowledge_ingest.py — feed the Murder Bot brain from EXTERNAL learning sources.

Pillar: "watch YouTube / Discord on learning + self-explore". This module ingests Evony
strategy content into a Postgres `knowledge` table (db murderbot) that the brain/advisors
can query. Sources so far: YouTube (search + transcript). Discord + web are stubs to extend.

CLI:
  python knowledge_ingest.py --youtube "evony pvp attack guide" -n 8 [--topic pvp]
  python knowledge_ingest.py --stats

Read-only w.r.t. the game (no ADB). Network-only. Gem/resource-safe (touches nothing in-game).
"""
import argparse
import datetime as _dt
import subprocess
import sys

import psycopg2

DB = "murderbot"


def _conn():
    return psycopg2.connect(dbname=DB)


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS knowledge(
            source      text NOT NULL,          -- youtube | discord | web
            source_id   text NOT NULL,          -- video id / message id / url
            title       text,
            url         text,
            topic       text,
            author      text,
            text        text,                   -- transcript / message body
            n_chars     int,
            ingested_at timestamp DEFAULT now(),
            PRIMARY KEY (source, source_id))""")


def yt_search(query, n):
    """Return [(video_id, title)] via yt-dlp flat search (no download)."""
    out = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--flat-playlist", "--print", "%(id)s\t%(title)s",
         f"ytsearch{n}:{query}"],
        capture_output=True, text=True, timeout=90)
    rows = []
    for line in out.stdout.splitlines():
        if "\t" in line:
            vid, title = line.split("\t", 1)
            rows.append((vid.strip(), title.strip()))
    return rows


def yt_transcript(video_id):
    """Return the plain-text transcript for a video, or None if unavailable.
    Uses the current youtube-transcript-api instance API (.fetch), with a fallback to
    the legacy static .get_transcript for older lib versions."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
            data = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
            return " ".join(s["text"].replace("\n", " ") for s in data if s.get("text"))
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        return " ".join(s["text"].replace("\n", " ") for s in segs if s.get("text"))
    except Exception:
        return None


# Authoritative Evony strategy guide pages — grows the brain beyond video transcripts.
WEB_GUIDES = [
    "https://evonyguidewiki.com/en/buff_debuff_basic_guide-en/",
    "https://evonyguidewiki.com/en/monster-battle-mechanics-en/",
    "https://evonyguidewiki.com/en/troop-type-en/",
    "https://evonyguidewiki.com/en/best-defense-general-en/",
    "https://evonyguidewiki.com/en/subordinate-city-guide-en/",
    "https://evonyguidewiki.com/en/sub-city-generals-debuff-comparison-tool-en/",
    "https://evonyguidewiki.com/en/war-hall-en/",
    "https://evonyguidewiki.com/en/hospital-en/",
    "https://evonyguidewiki.com/en/watch-tower-en/",
    "https://evonyguidewiki.com/en/pvp-check-list-en/",
    "https://evonyguidewiki.com/en/ghost-en/",
    "https://evonyguidewiki.com/en/coc-clash-of-civilizations-en/",
    "https://evonyguidewiki.com/en/spiritual-beast-en/",
    "https://evonyguidewiki.com/en/rally-spot-en/",
    "https://evonyguidewiki.com/en/holy-palace-en/",
]

_TAG = __import__("re").compile(r"<[^>]+>")
_WS = __import__("re").compile(r"\s+")


def _html_to_text(html):
    import re
    html = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
    text = _TAG.sub(" ", html)
    import html as _h
    text = _h.unescape(text)
    return _WS.sub(" ", text).strip()


def ingest_web(urls=None, topic="guide"):
    """Fetch Evony guide pages, strip to text, upsert into `knowledge` (source='web')."""
    import urllib.request
    urls = urls or WEB_GUIDES
    conn = _conn(); cur = conn.cursor(); _ensure_table(cur); conn.commit()
    stored, skipped = 0, 0
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MurderBot brain)"})
            raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
            text = _html_to_text(raw)
            if len(text) < 400:
                skipped += 1; continue
            title = url.rstrip("/").split("/")[-1].replace("-en", "").replace("-", " ").title()
            cur.execute("""
                INSERT INTO knowledge(source, source_id, title, url, topic, text, n_chars, ingested_at)
                VALUES ('web', %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, source_id) DO UPDATE
                SET text=EXCLUDED.text, title=EXCLUDED.title, n_chars=EXCLUDED.n_chars, ingested_at=EXCLUDED.ingested_at""",
                (url, title, url, topic, text, len(text), _dt.datetime.now()))
            stored += 1
        except Exception:
            skipped += 1
    conn.commit()
    return {"found": len(urls), "stored": stored, "skipped": skipped}


def ingest_youtube(query, n=8, topic=None):
    """Search Evony YouTube, fetch transcripts, upsert into `knowledge`. Returns a summary."""
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    found = yt_search(query, n)
    stored, skipped = 0, 0
    for vid, title in found:
        text = yt_transcript(vid)
        if not text:
            skipped += 1
            continue
        cur.execute("""
            INSERT INTO knowledge(source, source_id, title, url, topic, text, n_chars, ingested_at)
            VALUES ('youtube', %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, source_id) DO UPDATE
            SET title=EXCLUDED.title, text=EXCLUDED.text, topic=EXCLUDED.topic,
                n_chars=EXCLUDED.n_chars, ingested_at=EXCLUDED.ingested_at""",
            (vid, title, f"https://youtu.be/{vid}", topic or query,
             text, len(text), _dt.datetime.now()))
        stored += 1
    conn.commit()
    return {"query": query, "found": len(found), "stored": stored,
            "skipped_no_transcript": skipped}


def stats():
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT source, count(*), COALESCE(sum(n_chars),0) FROM knowledge GROUP BY source ORDER BY 2 DESC")
    rows = cur.fetchall()
    cur.execute("SELECT count(*), COALESCE(sum(n_chars),0) FROM knowledge")
    total, chars = cur.fetchone()
    return {"by_source": [{"source": s, "docs": d, "chars": int(c)} for s, d, c in rows],
            "total_docs": total, "total_chars": int(chars)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--youtube", metavar="QUERY", help="search + ingest Evony YouTube transcripts")
    ap.add_argument("--web", action="store_true", help="ingest authoritative Evony guide web pages")
    ap.add_argument("-n", type=int, default=8, help="how many videos")
    ap.add_argument("--topic", help="topic tag")
    ap.add_argument("--stats", action="store_true", help="show knowledge-base coverage")
    a = ap.parse_args()
    if a.youtube:
        r = ingest_youtube(a.youtube, a.n, a.topic)
        print(f"YouTube '{r['query']}': found {r['found']}, stored {r['stored']}, "
              f"skipped {r['skipped_no_transcript']} (no transcript)")
    if a.web:
        r = ingest_web(topic=a.topic or "guide")
        print(f"Web guides: found {r['found']}, stored {r['stored']}, skipped {r['skipped']}")
    if a.stats or not (a.youtube or a.web):
        s = stats()
        print(f"knowledge base: {s['total_docs']} docs, {s['total_chars']:,} chars")
        for row in s["by_source"]:
            print(f"  {row['source']}: {row['docs']} docs, {row['chars']:,} chars")


if __name__ == "__main__":
    sys.exit(main())
