"""Screen Catalog (map) view — vision-DB coverage for the Murder Bot manager.

Self-contained FastAPI APIRouter built with the ``build_router(current_user,
database)`` factory (same pattern as ``generals_view.py``). It does NOT import
``app.py``. The Postgres ``database`` handle is accepted for signature
consistency but unused — this view reads the SQLite vision brain that
``game_mapper.py`` / ``vision_db.py`` write.

Source of truth
---------------
``vision_db.py`` (``VisionDB``) stores what the bot has visually cataloged in a
SQLite database, by default ``<repo>/game_brain/vision.db``, in three tables:

* ``screens``  — one row per identified screen: ``label`` (the identified_as
  name), ``description``, ``keywords`` (salient tokens), ``updated_at`` (epoch).
* ``captures`` — every observed frame: ``screen_label``, ``ts``, ``image_path``
  (sample thumbnail), ``ocr_text`` (salient tokens fallback).
* ``elements`` — grounded UI elements per screen.

This view unions ``screens`` with distinct ``captures.screen_label`` so labels
that were captured but not yet promoted to a screen row still appear. It is
tolerant of a missing DB, a legacy ``screen_catalog`` table, or missing columns
— any of those yield an empty state rather than an error.

Override the DB location with the ``VISION_DB`` environment variable.
"""

from __future__ import annotations

import html
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _db_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("VISION_DB")
    if override:
        candidates.append(Path(override))
    candidates.extend(
        [
            REPO_ROOT / "game_brain" / "vision.db",
            REPO_ROOT / "vision.db",
            BASE_DIR / "game_brain" / "vision.db",
            BASE_DIR / "vision.db",
        ]
    )
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _find_db() -> Path | None:
    for path in _db_candidates():
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _tokens_from_ocr(text) -> list[str]:
    if not text:
        return []
    parts: list[str] = []
    for chunk in str(text).replace("|", " ").split():
        cleaned = chunk.strip().strip(",.;:").lower()
        if len(cleaned) >= 3 and cleaned not in parts:
            parts.append(cleaned)
        if len(parts) >= 10:
            break
    return parts


def _resolve_image(image_path) -> Path | None:
    if not image_path:
        return None
    path = Path(image_path)
    candidates = [path] if path.is_absolute() else [REPO_ROOT / path, BASE_DIR / path, path]
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES:
                return candidate
        except OSError:
            continue
    return None


def _fmt_last_seen(value) -> str:
    if value is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(value)


def _latest_captures(connection: sqlite3.Connection) -> dict[str, dict]:
    """Latest capture per screen_label: {label: {ts, image_path, ocr_text}}."""
    if "captures" not in _tables(connection):
        return {}
    columns = _columns(connection, "captures")
    if "screen_label" not in columns:
        return {}
    has_ts = "ts" in columns
    has_image = "image_path" in columns
    has_ocr = "ocr_text" in columns
    select = ["screen_label"]
    select.append("ts" if has_ts else "NULL AS ts")
    select.append("image_path" if has_image else "NULL AS image_path")
    select.append("ocr_text" if has_ocr else "NULL AS ocr_text")
    order = "ORDER BY ts" if has_ts else ""
    latest: dict[str, dict] = {}
    try:
        rows = connection.execute(
            f"SELECT {', '.join(select)} FROM captures "
            f"WHERE screen_label IS NOT NULL {order}"
        )
    except sqlite3.Error:
        return {}
    for row in rows:  # ascending ts -> last write per label wins (the latest)
        label = row["screen_label"]
        if not label:
            continue
        latest[label] = {
            "ts": row["ts"],
            "image_path": row["image_path"],
            "ocr_text": row["ocr_text"],
        }
    return latest


def _screen_rows(connection: sqlite3.Connection) -> dict[str, dict]:
    tables = _tables(connection)
    entries: dict[str, dict] = {}
    for table in ("screens", "screen_catalog"):  # legacy name tolerated
        if table not in tables:
            continue
        columns = _columns(connection, table)
        label_col = "label" if "label" in columns else (
            "identified_as" if "identified_as" in columns else None
        )
        if label_col is None:
            continue
        desc_col = "description" if "description" in columns else None
        kw_col = next((c for c in ("keywords", "salient", "tokens") if c in columns), None)
        seen_col = next(
            (c for c in ("updated_at", "last_seen", "ts") if c in columns), None
        )
        select = [f"{label_col} AS label"]
        select.append(f"{desc_col} AS description" if desc_col else "NULL AS description")
        select.append(f"{kw_col} AS keywords" if kw_col else "NULL AS keywords")
        select.append(f"{seen_col} AS updated_at" if seen_col else "NULL AS updated_at")
        try:
            rows = connection.execute(f"SELECT {', '.join(select)} FROM {table}")
        except sqlite3.Error:
            continue
        for row in rows:
            label = row["label"]
            if not label:
                continue
            entries[label] = {
                "label": label,
                "description": row["description"],
                "keywords": row["keywords"],
                "updated_at": row["updated_at"],
                "source": "screen",
            }
    return entries


def load_catalog() -> dict:
    path = _find_db()
    if path is None:
        return {
            "db_path": None,
            "total": 0,
            "with_thumbnail": 0,
            "counts": {},
            "screens": [],
            "warning": (
                "vision.db not found. Looked in: "
                + ", ".join(str(p) for p in _db_candidates())
            ),
        }

    warning = ""
    connection = None
    try:
        connection = _connect(path)
        entries = _screen_rows(connection)
        captures = _latest_captures(connection)

        # Fold captures in: enrich existing entries, add capture-only labels.
        for label, capture in captures.items():
            entry = entries.setdefault(
                label,
                {
                    "label": label,
                    "description": None,
                    "keywords": None,
                    "updated_at": None,
                    "source": "capture",
                },
            )
            entry["capture_ts"] = capture.get("ts")
            entry["ocr_text"] = capture.get("ocr_text")
            entry["image_path"] = capture.get("image_path")

        try:
            counts = {
                table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("screens", "captures", "elements")
                if table in _tables(connection)
            }
        except sqlite3.Error:
            counts = {}
    except sqlite3.Error as error:
        return {
            "db_path": str(path),
            "total": 0,
            "with_thumbnail": 0,
            "counts": {},
            "screens": [],
            "warning": f"Could not read {path.name}: {type(error).__name__}: {error}",
        }
    finally:
        if connection is not None:
            connection.close()

    screens: list[dict] = []
    with_thumbnail = 0
    for label, entry in entries.items():
        tokens: list[str] = []
        if entry.get("keywords"):
            tokens = [
                token
                for token in str(entry["keywords"]).replace(",", " ").split()
                if token
            ][:12]
        if not tokens:
            tokens = _tokens_from_ocr(entry.get("ocr_text"))

        last_seen_raw = entry.get("updated_at")
        capture_ts = entry.get("capture_ts")
        if last_seen_raw is None:
            last_seen_raw = capture_ts
        elif isinstance(capture_ts, (int, float)) and isinstance(last_seen_raw, (int, float)):
            last_seen_raw = max(last_seen_raw, capture_ts)

        resolved = _resolve_image(entry.get("image_path"))
        has_thumbnail = resolved is not None
        if has_thumbnail:
            with_thumbnail += 1

        screens.append(
            {
                "label": label,
                "identified_as": label,
                "description": entry.get("description") or "",
                "tokens": tokens,
                "last_seen": _fmt_last_seen(last_seen_raw),
                "last_seen_raw": last_seen_raw,
                "source": entry.get("source", "screen"),
                "has_thumbnail": has_thumbnail,
                "thumbnail_url": f"/map/thumb/{label}" if has_thumbnail else None,
            }
        )

    screens.sort(
        key=lambda item: (
            item["last_seen_raw"] if isinstance(item["last_seen_raw"], (int, float)) else 0
        ),
        reverse=True,
    )

    return {
        "db_path": str(path),
        "total": len(screens),
        "with_thumbnail": with_thumbnail,
        "counts": counts,
        "screens": screens,
        "warning": warning,
    }


def _thumbnail_path(label: str) -> Path | None:
    path = _find_db()
    if path is None:
        return None
    connection = None
    try:
        connection = _connect(path)
        captures = _latest_captures(connection)
    except sqlite3.Error:
        return None
    finally:
        if connection is not None:
            connection.close()
    capture = captures.get(label)
    if not capture:
        return None
    return _resolve_image(capture.get("image_path"))


# --- HTML rendering --------------------------------------------------------


def _tokens_html(tokens: list) -> str:
    if not tokens:
        return '<span class="muted">no tokens</span>'
    return "".join(f'<span class="token">{html.escape(str(t))}</span>' for t in tokens[:12])


def _card_html(screen: dict) -> str:
    if screen.get("has_thumbnail"):
        thumb = (
            f'<img class="thumb" src="{html.escape(screen["thumbnail_url"])}" '
            f'alt="{html.escape(screen["label"])}" loading="lazy">'
        )
    else:
        thumb = '<div class="thumb noimg">no sample</div>'
    source_badge = (
        '<span class="src capture">capture-only</span>'
        if screen.get("source") == "capture"
        else '<span class="src screen">screen</span>'
    )
    description = (
        f'<p class="desc">{html.escape(screen["description"])}</p>'
        if screen.get("description")
        else ""
    )
    return f"""
<article class="scard">
  {thumb}
  <div class="body">
    <header class="shead">
      <h3>{html.escape(screen["label"])}</h3>
      {source_badge}
    </header>
    {description}
    <div class="tokens">{_tokens_html(screen.get("tokens", []))}</div>
    <div class="seen">Last seen: {html.escape(str(screen.get("last_seen", "—")))}</div>
  </div>
</article>"""


def render_page(data: dict) -> str:
    warning = (
        f'<div class="warn">{html.escape(data["warning"])}</div>' if data.get("warning") else ""
    )
    counts = data.get("counts") or {}
    count_chips = "".join(
        f'<span class="stat"><b>{value}</b> {html.escape(name)}</span>'
        for name, value in counts.items()
    )
    db_path = html.escape(str(data.get("db_path") or "not found"))
    if data.get("screens"):
        cards = "".join(_card_html(screen) for screen in data["screens"])
        grid = f'<div class="sgrid">{cards}</div>'
    else:
        grid = (
            '<div class="empty">No cataloged screens yet. Run the game mapper to '
            "populate the vision brain.</div>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Screen Catalog — Murder Bot</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }}
main {{ width: min(1200px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }}
a {{ color: #58a6ff; text-decoration: none; }}
h1, h2, h3 {{ margin: 0; }}
header.top {{ display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }}
.sub {{ color: #8b949e; font-size: .9rem; margin-top: .3rem; }}
.summary {{ display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; margin: 1.2rem 0 .3rem; }}
.coverage {{ padding: .5rem 1rem; background: #12331d; border: 1px solid #238636; border-radius: 999px; font-size: 1rem; font-weight: 700; color: #3fb950; }}
.stat {{ padding: .45rem .85rem; background: #161b22; border: 1px solid #30363d; border-radius: 999px; font-size: .85rem; color: #adbac7; }}
.stat b {{ color: #fff; }}
.dbpath {{ margin: .4rem 0 0; color: #6e7681; font-size: .76rem; font-family: ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }}
.warn {{ margin: 1rem 0; padding: .7rem 1rem; color: #d29922; background: #3d2f0b; border: 1px solid #9e6a03; border-radius: 8px; font-size: .85rem; overflow-wrap: anywhere; }}
.sgrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 1rem; margin-top: 1.4rem; }}
.scard {{ display: flex; flex-direction: column; background: #161b22; border: 1px solid #30363d; border-radius: 12px; overflow: hidden; }}
.thumb {{ display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; background: #010409; }}
.thumb.noimg {{ display: flex; align-items: center; justify-content: center; color: #484f58; font-size: .82rem; }}
.body {{ padding: .8rem .9rem 1rem; display: flex; flex-direction: column; gap: .5rem; }}
.shead {{ display: flex; align-items: center; justify-content: space-between; gap: .5rem; }}
.shead h3 {{ font-size: 1rem; line-height: 1.2; overflow-wrap: anywhere; }}
.src {{ flex: none; font-size: .66rem; font-weight: 700; letter-spacing: .03em; text-transform: uppercase; padding: .12rem .45rem; border-radius: 999px; }}
.src.screen {{ color: #58a6ff; background: #10233b; }}
.src.capture {{ color: #d29922; background: #3d2f0b; }}
.desc {{ margin: 0; color: #adbac7; font-size: .82rem; line-height: 1.4; }}
.tokens {{ display: flex; flex-wrap: wrap; gap: .3rem; }}
.token {{ font-size: .7rem; color: #8b949e; background: #21262d; border-radius: 6px; padding: .12rem .45rem; }}
.seen {{ color: #6e7681; font-size: .74rem; }}
.muted {{ color: #6e7681; font-size: .74rem; }}
.empty {{ margin-top: 2rem; padding: 3rem 1rem; text-align: center; color: #8b949e; border: 1px dashed #30363d; border-radius: 12px; }}
@media (max-width: 520px) {{
  main {{ padding: 1.25rem 0 3rem; }}
  .sgrid {{ grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: .7rem; }}
}}
</style>
</head>
<body>
<main>
<header class="top">
  <div>
    <h1>Screen Catalog</h1>
    <div class="sub">Murder Bot — vision-DB coverage (what the bot has cataloged)</div>
  </div>
  <a href="/">&larr; Dashboard</a>
</header>
<div class="summary">
  <span class="coverage">{data.get('total', 0)} screens cataloged</span>
  <span class="stat"><b>{data.get('with_thumbnail', 0)}</b> with sample</span>
  {count_chips}
</div>
<p class="dbpath">Source: {db_path}</p>
{warning}
{grid}
</main>
</body>
</html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the screen-catalog router wired to the host app's auth.

    ``database`` is accepted for factory-signature consistency but unused; this
    view reads the SQLite vision brain.
    """
    router = APIRouter(tags=["map"])

    @router.get("/map", response_class=HTMLResponse)
    def map_page(_user_id: int = Depends(current_user)):
        return HTMLResponse(render_page(load_catalog()))

    @router.get("/api/map")
    def map_api(_user_id: int = Depends(current_user)):
        return JSONResponse(load_catalog())

    @router.get("/map/thumb/{label}")
    def map_thumbnail(label: str, _user_id: int = Depends(current_user)):
        resolved = _thumbnail_path(label)
        if resolved is None:
            raise HTTPException(status_code=404, detail="No sample image for this screen")
        return FileResponse(resolved)

    return router
