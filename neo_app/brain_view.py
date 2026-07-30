"""Brain / Learning manager — what the self-evolving brain has learned.

Self-contained FastAPI APIRouter. It does NOT import app.py (no circular
import): the host app injects its own ``current_user`` auth dependency and
``database`` context manager through ``build_router(...)``.

Data sources
------------
* Ingested content : Postgres ``knowledge`` table (source, source_id, title,
  url, topic, author, text, n_chars, ingested_at). Currently ~18 YouTube Evony
  videos scraped for transcripts.
* Distilled tactics : ``game_brain/knowledge_distilled.md`` — heuristic/LLM
  insights synthesised from the ingested transcripts (append-only, tagged
  ``confidence: external-video``).
* Learning daemon : ``knowledge_loop.sh`` re-ingests + re-distills every ~4h.
  Liveness is read from the pidfile at ``/tmp/knowledge_loop.pid`` and recent
  activity from ``/tmp/knowledge_loop.log``.

Every filesystem / DB read degrades gracefully: a missing table, missing file,
or dead daemon yields empty data plus a human-readable note, never a 500.
"""

from __future__ import annotations

import html
import os
import re
from collections import deque
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse

REPO_DIR = Path(__file__).resolve().parent.parent
DISTILLED_PATH = Path(
    os.environ.get(
        "KNOWLEDGE_DISTILLED_PATH",
        REPO_DIR / "game_brain" / "knowledge_distilled.md",
    )
)
LOOP_PIDFILE = Path(os.environ.get("KNOWLEDGE_LOOP_PIDFILE", "/tmp/knowledge_loop.pid"))
LOOP_LOGFILE = Path(os.environ.get("KNOWLEDGE_LOOP_LOG", "/tmp/knowledge_loop.log"))

RUN_RE = re.compile(r"^##\s+(.*)$")
SECTION_RE = re.compile(r"^###\s+(.*)$")
SOURCE_RE = re.compile(r"^_source:\s*(.*?)\s*_?$")
BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
TAGS_RE = re.compile(r"`\[(.*?)\]`\s*$")


def _pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def gather_daemon(pidfile: Path, logfile: Path, tail: int = 12) -> dict:
    try:
        pid = int(pidfile.read_text().strip())
    except (FileNotFoundError, OSError, ValueError):
        pid = None
    lines: deque[str] = deque(maxlen=max(1, tail))
    try:
        with logfile.open(errors="replace") as log:
            lines.extend(line.rstrip("\n") for line in log if line.strip())
    except OSError:
        pass
    return {
        "running": _pid_alive(pid),
        "pid": pid,
        "log_tail": list(lines),
        "pidfile": str(pidfile),
        "logfile": str(logfile),
        "interval_hint": "re-ingests + re-distills every ~4h",
    }


def gather_knowledge(database) -> dict:
    by_source: list[dict] = []
    total_docs = 0
    total_chars = 0
    warning = ""
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT source, count(*), coalesce(sum(n_chars), 0)
                    FROM knowledge
                    GROUP BY source
                    ORDER BY count(*) DESC
                    """
                )
                for source, docs, chars in cursor.fetchall():
                    docs = int(docs)
                    chars = int(chars)
                    by_source.append(
                        {"source": source or "unknown", "docs": docs, "chars": chars}
                    )
                    total_docs += docs
                    total_chars += chars
    except Exception as error:  # noqa: BLE001 - any DB failure degrades to empty
        warning = (
            f"Could not read the knowledge table ({error.__class__.__name__}); "
            "the brain has no ingested content to show yet."
        )
    return {
        "total_docs": total_docs,
        "total_chars": total_chars,
        "by_source": by_source,
        "warning": warning,
    }


def gather_sources(database, limit: int = 200) -> list[dict]:
    rows: list[dict] = []
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT source, source_id, title, url, topic, author,
                           n_chars, ingested_at
                    FROM knowledge
                    ORDER BY ingested_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    (limit,),
                )
                for (
                    source,
                    source_id,
                    title,
                    url,
                    topic,
                    author,
                    n_chars,
                    ingested_at,
                ) in cursor.fetchall():
                    link = url
                    if not link and source == "youtube" and source_id:
                        link = f"https://youtu.be/{source_id}"
                    rows.append(
                        {
                            "source": source,
                            "source_id": source_id,
                            "title": (title or source_id or "Untitled").strip(),
                            "url": link,
                            "topic": (topic or "").strip(),
                            "author": (author or "").strip(),
                            "n_chars": int(n_chars) if n_chars is not None else None,
                            "ingested_at": (
                                ingested_at.isoformat(sep=" ", timespec="minutes")
                                if ingested_at is not None
                                else None
                            ),
                        }
                    )
    except Exception:  # noqa: BLE001 - table missing / DB down -> no sources
        return []
    return rows


def parse_distilled(path: Path) -> dict:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {
            "file": str(path),
            "exists": False,
            "total_insights": 0,
            "runs": [],
            "last_run": "",
            "sections": [],
            "note": (
                "The distilled tactics file has not been generated yet — the "
                "learning daemon writes it after its first synth pass."
            ),
        }

    runs: list[str] = []
    sections: list[dict] = []
    current: dict | None = None
    total_insights = 0

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("<!--"):
            continue

        run_match = RUN_RE.match(line)
        section_match = SECTION_RE.match(line)
        bullet_match = BULLET_RE.match(line)

        if section_match:
            current = {"title": section_match.group(1).strip(), "url": "", "insights": []}
            sections.append(current)
            continue
        if run_match:
            label = run_match.group(1).strip()
            if label.lower().startswith("synth run"):
                runs.append(label)
            current = None
            continue
        if current is not None and line.startswith("_source:"):
            source_match = SOURCE_RE.match(line)
            if source_match:
                for token in source_match.group(1).split("·"):
                    token = token.strip()
                    if token.startswith(("http://", "https://")):
                        current["url"] = token
                        break
            continue
        if current is not None and bullet_match:
            body = bullet_match.group(1).strip()
            tags_match = TAGS_RE.search(body)
            tags: list[str] = []
            if tags_match:
                body = body[: tags_match.start()].strip()
                tags = [
                    tag.strip()
                    for tag in tags_match.group(1).split(",")
                    if tag.strip()
                ]
            body = body.lstrip("…").strip()
            if not body:
                continue
            current["insights"].append({"text": body, "tags": tags})
            total_insights += 1

    sections = [section for section in sections if section["insights"]]
    return {
        "file": str(path),
        "exists": True,
        "total_insights": total_insights,
        "runs": runs,
        "last_run": runs[-1] if runs else "",
        "sections": sections,
        "note": "",
    }


def build_brain_data(database) -> dict:
    return {
        "knowledge": gather_knowledge(database),
        "sources": gather_sources(database),
        "daemon": gather_daemon(LOOP_PIDFILE, LOOP_LOGFILE),
        "distilled": parse_distilled(DISTILLED_PATH),
    }


PAGE_CSS = """
:root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; line-height: 1.5; }
main { width: min(1100px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
header.top { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .75rem; }
h1 { margin: 0; font-size: 1.7rem; }
h2 { margin: 0 0 .2rem; font-size: 1.2rem; }
.lede { margin: .4rem 0 0; color: #8b949e; font-size: .92rem; max-width: 62ch; }
.section { margin-top: 2.4rem; }
.section-sub { margin: .3rem 0 1rem; color: #8b949e; font-size: .9rem; }
.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .8rem; margin: 1.4rem 0; }
.metric { padding: 1rem; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }
.metric span { display: block; color: #8b949e; font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; }
.metric strong { display: block; margin-top: .4rem; font-size: 1.35rem; overflow-wrap: anywhere; }
.metric strong.good { color: #3fb950; }
.metric strong.bad { color: #ff7b72; }
.metric small { display: block; margin-top: .2rem; color: #6e7681; font-size: .74rem; }
.pill { display: inline-block; padding: .1rem .5rem; border-radius: 999px; font-size: .78rem; font-weight: 700; }
.pill.on { color: #3fb950; background: #12261a; border: 1px solid #1c3d28; }
.pill.off { color: #ff7b72; background: #2a1615; border: 1px solid #4a2321; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1.1rem 1.2rem; }
.source-line { display: flex; flex-wrap: wrap; gap: .5rem .9rem; margin: 0 0 1rem; }
.source-line .stat { padding: .35rem .75rem; background: #161b22; border: 1px solid #30363d; border-radius: 999px; font-size: .85rem; color: #adbac7; }
.source-line .stat b { color: #fff; }
pre.log { max-height: 15rem; overflow: auto; margin: 0; padding: .85rem 1rem; white-space: pre-wrap; word-break: break-word; background: #010409; border: 1px solid #30363d; border-radius: 10px; font-size: .82rem; line-height: 1.55; color: #adbac7; }
.warn { margin: 1rem 0; padding: .7rem 1rem; color: #d29922; background: #3d2f0b; border: 1px solid #9e6a03; border-radius: 8px; font-size: .9rem; }
.src-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: .9rem; }
.src-card { display: flex; flex-direction: column; gap: .5rem; padding: .9rem 1rem; background: #161b22; border: 1px solid #30363d; border-radius: 12px; }
.src-card h3 { margin: 0; font-size: .98rem; line-height: 1.3; }
.src-meta { display: flex; flex-wrap: wrap; gap: .4rem; }
.chip { padding: .12rem .55rem; font-size: .72rem; border-radius: 999px; border: 1px solid #30363d; color: #adbac7; background: #0d1117; }
.chip.topic { color: #d2a8ff; border-color: #3a2d63; background: #1c1633; }
.src-foot { margin-top: auto; color: #6e7681; font-size: .78rem; }
.tactic { padding: 1rem 1.2rem; background: #161b22; border: 1px solid #30363d; border-radius: 12px; }
.tactic + .tactic { margin-top: 1rem; }
.tactic-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .5rem; }
.tactic-head h3 { margin: 0; font-size: 1rem; }
.tactic-head .count { color: #6e7681; font-size: .8rem; }
.insights { margin: .8rem 0 0; padding: 0; list-style: none; display: grid; gap: .55rem; }
.insights li { padding: .55rem .7rem .55rem .95rem; background: #0d1117; border: 1px solid #21262d; border-left: 3px solid #8957e5; border-radius: 8px; font-size: .88rem; }
.insight-tags { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .4rem; }
.tag { padding: .05rem .4rem; font-size: .68rem; color: #6e7681; background: #161b22; border: 1px solid #21262d; border-radius: 5px; }
footer { margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid #21262d; color: #6e7681; font-size: .8rem; line-height: 1.6; }
@media (max-width: 520px) {
  main { padding: 1.25rem 0 3rem; }
  h1 { font-size: 1.4rem; }
  .src-grid { grid-template-columns: 1fr; }
}
"""


def _sources_html(sources: list[dict]) -> str:
    if not sources:
        return '<p class="section-sub">No ingested sources recorded yet.</p>'
    cards = []
    for row in sources:
        title = html.escape(row["title"])
        if row.get("url"):
            title_html = f'<a href="{html.escape(row["url"])}" target="_blank" rel="noopener">{title}</a>'
        else:
            title_html = title
        meta = [f'<span class="chip">{html.escape(row["source"] or "?")}</span>']
        if row.get("topic"):
            meta.append(f'<span class="chip topic">{html.escape(row["topic"])}</span>')
        if row.get("author"):
            meta.append(f'<span class="chip">{html.escape(row["author"])}</span>')
        chars = (
            f'{row["n_chars"]:,} chars' if row.get("n_chars") is not None else "— chars"
        )
        ingested = html.escape(row["ingested_at"] or "date unknown")
        cards.append(
            f"""
    <article class="src-card">
      <h3>{title_html}</h3>
      <div class="src-meta">{"".join(meta)}</div>
      <div class="src-foot">{chars} &middot; ingested {ingested}</div>
    </article>"""
        )
    return f'<div class="src-grid">{"".join(cards)}</div>'


def _tactics_html(distilled: dict) -> str:
    if not distilled["exists"]:
        return f'<p class="warn">{html.escape(distilled["note"])}</p>'
    if not distilled["sections"]:
        return '<p class="section-sub">No distilled tactics parsed from the file yet.</p>'
    blocks = []
    for section in distilled["sections"]:
        title = html.escape(section["title"])
        if section.get("url"):
            title_html = f'<a href="{html.escape(section["url"])}" target="_blank" rel="noopener">{title}</a>'
        else:
            title_html = title
        items = []
        for insight in section["insights"]:
            tags_html = ""
            if insight["tags"]:
                tags = "".join(
                    f'<span class="tag">{html.escape(tag)}</span>'
                    for tag in insight["tags"]
                )
                tags_html = f'<div class="insight-tags">{tags}</div>'
            items.append(
                f'<li>{html.escape(insight["text"])}{tags_html}</li>'
            )
        blocks.append(
            f"""
  <div class="tactic">
    <div class="tactic-head">
      <h3>{title_html}</h3>
      <span class="count">{len(section["insights"])} insights</span>
    </div>
    <ul class="insights">{"".join(items)}</ul>
  </div>"""
        )
    return "".join(blocks)


def render_page(data: dict) -> str:
    knowledge = data["knowledge"]
    daemon = data["daemon"]
    distilled = data["distilled"]
    sources = data["sources"]

    running = daemon["running"]
    daemon_state = (
        '<span class="pill on">RUNNING</span>'
        if running
        else '<span class="pill off">STOPPED</span>'
    )
    daemon_pid = f'PID {daemon["pid"]}' if daemon.get("pid") else "no pidfile"

    warning = (
        f'<p class="warn">{html.escape(knowledge["warning"])}</p>'
        if knowledge.get("warning")
        else ""
    )

    by_source_html = "".join(
        f'<span class="stat"><b>{item["docs"]:,}</b> {html.escape(item["source"])} '
        f'&middot; {item["chars"]:,} chars</span>'
        for item in knowledge["by_source"]
    ) or '<span class="stat">No sources ingested</span>'

    log_lines = daemon["log_tail"]
    log_html = html.escape("\n".join(log_lines)) if log_lines else "No log output yet."

    last_run = (
        html.escape(distilled["last_run"]) if distilled.get("last_run") else "—"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brain / Learning — Murder Bot</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<main>
<header class="top">
  <div>
    <h1>Brain / Learning</h1>
    <p class="lede">What the self-evolving brain has ingested and distilled from
      community Evony content. External heuristic learning — directional, not the
      hand-verified doctrine.</p>
  </div>
  <a href="/">&larr; Dashboard</a>
</header>

<section class="section" aria-label="Learning status">
  <h2>Learning status</h2>
  <div class="status-grid">
    <div class="metric"><span>Knowledge base</span><strong>{knowledge['total_docs']:,}</strong><small>documents ingested</small></div>
    <div class="metric"><span>Total content</span><strong>{knowledge['total_chars']:,}</strong><small>characters stored</small></div>
    <div class="metric"><span>Distilled tactics</span><strong>{distilled['total_insights']:,}</strong><small>insights extracted</small></div>
    <div class="metric"><span>Learning daemon</span><strong class="{'good' if running else 'bad'}">{'Live' if running else 'Offline'}</strong><small>{daemon_state} &middot; {daemon_pid}</small></div>
  </div>
  <div class="source-line">{by_source_html}</div>
  {warning}
  <h2 style="margin-top:1.4rem">Daemon activity</h2>
  <p class="section-sub">{html.escape(daemon['interval_hint'])} &middot; {html.escape(daemon['logfile'])}</p>
  <pre class="log">{log_html}</pre>
</section>

<section class="section" aria-label="Ingested sources">
  <h2>Ingested sources <span style="color:#6e7681;font-size:.9rem;font-weight:400">{len(sources)}</span></h2>
  <p class="section-sub">Community videos scraped for transcripts and fed to the distiller.</p>
  {_sources_html(sources)}
</section>

<section class="section" aria-label="Distilled tactics">
  <h2>Distilled tactics</h2>
  <p class="section-sub">Heuristic insights extracted per source. Last synth: {last_run}.</p>
  {_tactics_html(distilled)}
</section>

<footer>
  <p><b>Ingested content:</b> Postgres <code>murderbot.knowledge</code> (source, title, url, topic, n_chars, ingested_at).</p>
  <p><b>Distilled tactics:</b> {html.escape(distilled['file'])} — append-only, tagged <code>confidence: external-video</code>.</p>
  <p><b>Learning daemon:</b> knowledge_loop.sh (pidfile {html.escape(daemon['pidfile'])}) re-ingests + re-distills every ~4h.</p>
</footer>
</main>
</body>
</html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the brain/learning router wired to the host app's auth + DB.

    Parameters
    ----------
    current_user:
        The host app's FastAPI auth dependency (``request -> user_id``).
    database:
        The host app's ``@contextmanager`` yielding a psycopg2 connection.
    """
    router = APIRouter(tags=["brain"])

    @router.get("/brain", response_class=HTMLResponse)
    def brain_page(_user_id: int = Depends(current_user)):
        return HTMLResponse(render_page(build_brain_data(database)))

    @router.get("/api/brain")
    def brain_data(_user_id: int = Depends(current_user)):
        return JSONResponse(build_brain_data(database))

    return router
