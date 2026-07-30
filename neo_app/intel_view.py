"""Enemy Intel view — every player the Murder Bot has learned about.

Self-contained FastAPI APIRouter built with the ``build_router(current_user,
database)`` factory (same pattern as ``generals_view.py`` / ``map_view.py``). It
does NOT import ``app.py`` (no circular import): the host app injects its own
``current_user`` auth dependency and ``database`` context manager.

Source of truth
---------------
The Postgres ``enemies`` table, seeded from parsed battle reports. Columns::

    name        text        player name
    alliance    text        alliance tag ("DTP", "ViG", "?" when unknown)
    battles     int         times seen in a report
    my_wins     int         my wins against them
    my_losses   int         my losses against them
    max_troops  bigint      largest troop count observed
    coords      text        last observed coordinates
    buffs       jsonb       per-troop-type buff magnitudes + _level / _power
    generals    jsonb       observed generals ({"main": "..."} today)
    threat      text        "beats me" / "i beat" / blank
    last_seen   timestamp   when last observed

``threat`` is authoritative when present; when blank it is derived from the
win/loss record. Every number is rendered FULLY EXPANDED with thousands commas
— never abbreviated (1.2M / 2B).
"""

from __future__ import annotations

import html
import json
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse

TYPE_META = {
    "ground": {"label": "Ground", "glyph": "🛡️", "color": "#3fb950"},
    "ranged": {"label": "Ranged", "glyph": "🏹", "color": "#58a6ff"},
    "mounted": {"label": "Mounted", "glyph": "🐎", "color": "#ff7b72"},
    "siege": {"label": "Siege", "glyph": "🏰", "color": "#a371f7"},
}
TYPE_ORDER = ["ground", "ranged", "mounted", "siege"]

# Threat classes drive both the badge colour and the sort order (lower rank =
# shown first / more dangerous).
THREAT_META = {
    "beats_you": {"label": "BEATS YOU", "kind": "bad", "rank": 0},
    "even": {"label": "EVEN / UNKNOWN", "kind": "neutral", "rank": 1},
    "you_beat": {"label": "YOU BEAT", "kind": "good", "rank": 2},
}


def commafy(value) -> str:
    """Full, comma-separated integer — never abbreviated."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def classify_threat(threat, my_wins: int, my_losses: int) -> str:
    """Map the stored threat string (or the W/L record) to a threat class."""
    text = (threat or "").strip().lower()
    if text in ("beats me", "beats you", "loses", "i lose", "they beat me"):
        return "beats_you"
    if text in ("i beat", "beat", "i win", "i beat them"):
        return "you_beat"
    if my_losses > my_wins:
        return "beats_you"
    if my_wins > my_losses:
        return "you_beat"
    return "even"


def _relative_age(value: datetime) -> str:
    try:
        delta = datetime.now() - value
    except TypeError:
        return ""
    seconds = delta.total_seconds()
    if seconds < 0:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _buff_rows(buffs: dict) -> list[dict]:
    rows = []
    for key in TYPE_ORDER:
        stats = buffs.get(key)
        if not isinstance(stats, dict):
            continue
        meta = TYPE_META[key]
        rows.append(
            {
                "type": key,
                "label": meta["label"],
                "glyph": meta["glyph"],
                "color": meta["color"],
                "attack": stats.get("attack"),
                "defense": stats.get("defense"),
                "hp": stats.get("hp"),
            }
        )
    return rows


def build_intel_data(database) -> dict:
    """Read the enemies table and shape it for the page + JSON API."""
    enemies: list[dict] = []
    warning = ""
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT name, alliance, battles, my_wins, my_losses,
                           max_troops, coords, buffs, generals, threat, last_seen
                    FROM enemies
                    """
                )
                columns = [description[0] for description in cursor.description]
                for values in cursor.fetchall():
                    enemies.append(dict(zip(columns, values)))
    except Exception as error:  # pragma: no cover - defensive
        warning = (
            f"Could not read the enemies table ({error.__class__.__name__}); "
            "showing what is available."
        )

    records: list[dict] = []
    by_alliance: dict[str, int] = {}
    for row in enemies:
        name = row.get("name") or "Unknown"
        alliance = (row.get("alliance") or "?").strip() or "?"
        my_wins = row.get("my_wins") or 0
        my_losses = row.get("my_losses") or 0
        battles = row.get("battles") or 0
        max_troops = row.get("max_troops")
        threat_class = classify_threat(row.get("threat"), my_wins, my_losses)
        threat_meta = THREAT_META[threat_class]

        buffs = _as_dict(row.get("buffs"))
        generals = _as_dict(row.get("generals"))
        level = buffs.get("_level")
        power = buffs.get("_power")

        last_seen = row.get("last_seen")
        last_seen_iso = None
        last_seen_display = ""
        last_seen_relative = ""
        if isinstance(last_seen, datetime):
            last_seen_iso = last_seen.isoformat()
            last_seen_display = last_seen.strftime("%b %d, %Y %H:%M")
            last_seen_relative = _relative_age(last_seen)
        elif last_seen:
            last_seen_display = str(last_seen)

        by_alliance[alliance] = by_alliance.get(alliance, 0) + 1

        records.append(
            {
                "name": name,
                "alliance": alliance,
                "battles": battles,
                "my_wins": my_wins,
                "my_losses": my_losses,
                "max_troops": max_troops,
                "max_troops_display": commafy(max_troops) if max_troops else None,
                "coords": (row.get("coords") or "").strip(),
                "threat": (row.get("threat") or "").strip(),
                "threat_class": threat_class,
                "threat_label": threat_meta["label"],
                "threat_kind": threat_meta["kind"],
                "threat_note": (row.get("threat") or "").strip(),
                "level": level,
                "power": power,
                "power_display": commafy(power) if power else None,
                "buffs": buffs,
                "buff_rows": _buff_rows(buffs),
                "generals": generals,
                "last_seen": last_seen_iso,
                "last_seen_display": last_seen_display,
                "last_seen_relative": last_seen_relative,
            }
        )

    # Sort by threat (most dangerous first) then by troop size (largest first).
    records.sort(
        key=lambda record: (
            THREAT_META[record["threat_class"]]["rank"],
            -(record["max_troops"] or 0),
            record["name"].casefold(),
        )
    )

    biggest = None
    for record in records:
        if record["max_troops"] and (
            biggest is None or record["max_troops"] > biggest["max_troops"]
        ):
            biggest = record

    biggest_threat = None
    if biggest is not None:
        biggest_threat = {
            "name": biggest["name"],
            "alliance": biggest["alliance"],
            "max_troops": biggest["max_troops"],
            "max_troops_display": biggest["max_troops_display"],
        }

    return {
        "counts": {
            "total": len(records),
            "beats_you": sum(1 for r in records if r["threat_class"] == "beats_you"),
            "you_beat": sum(1 for r in records if r["threat_class"] == "you_beat"),
            "by_alliance": dict(
                sorted(by_alliance.items(), key=lambda item: (-item[1], item[0]))
            ),
        },
        "biggest_threat": biggest_threat,
        "enemies": records,
        "warning": warning,
        "source": "Postgres murderbot.enemies (seeded from parsed battle reports)",
    }


def _chip(text: str, kind: str = "") -> str:
    classes = ("chip " + kind).strip()
    return f'<span class="{classes}">{html.escape(text)}</span>'


def _buffs_html(record: dict) -> str:
    rows = record["buff_rows"]
    if not rows:
        return ""
    cells = []
    for row in rows:
        parts = []
        for label, key in (("Atk", "attack"), ("Def", "defense"), ("HP", "hp")):
            value = row.get(key)
            if value is None:
                continue
            parts.append(
                f'<span class="stat"><i>{label}</i>{commafy(value)}%</span>'
            )
        if not parts:
            continue
        cells.append(
            f'<div class="buff-row" style="--type:{row["color"]}">'
            f'<span class="buff-type">{row["glyph"]} {html.escape(row["label"])}</span>'
            f'<span class="buff-stats">{"".join(parts)}</span>'
            "</div>"
        )
    if not cells:
        return ""
    return f'<div class="buffs"><h4>Combat buffs</h4>{"".join(cells)}</div>'


def _generals_html(record: dict) -> str:
    generals = record["generals"]
    if not generals:
        return ""
    chips = []
    for key, value in generals.items():
        if value in (None, ""):
            continue
        label = str(key).replace("_", " ").title()
        chips.append(
            f'<span class="chip general"><i>{html.escape(label)}</i>'
            f"{html.escape(str(value))}</span>"
        )
    if not chips:
        return ""
    return f'<div class="generals"><h4>Generals seen</h4><div class="chips">{"".join(chips)}</div></div>'


def _card_html(record: dict) -> str:
    troops = (
        f'<p class="troops"><b>{record["max_troops_display"]}</b> troops</p>'
        if record["max_troops_display"]
        else '<p class="troops muted">Troop count not yet observed</p>'
    )

    record_bits = [f'{record["my_wins"]}W', f'{record["my_losses"]}L']
    if record["battles"]:
        record_bits.append(f'{record["battles"]} seen')
    wl = " &middot; ".join(record_bits)

    meta_bits = []
    if record["level"]:
        meta_bits.append(f'Keep L{html.escape(str(record["level"]))}')
    if record["power_display"]:
        meta_bits.append(f'Power {record["power_display"]}')
    if record["coords"]:
        meta_bits.append(f'📍 {html.escape(record["coords"])}')
    meta_line = (
        f'<p class="meta">{" &middot; ".join(meta_bits)}</p>' if meta_bits else ""
    )

    seen = ""
    if record["last_seen_display"]:
        rel = (
            f' <span class="rel">({html.escape(record["last_seen_relative"])})</span>'
            if record["last_seen_relative"]
            else ""
        )
        seen = (
            f'<p class="seen">Last seen {html.escape(record["last_seen_display"])}{rel}</p>'
        )

    note = ""
    if record["threat_note"] and record["threat_note"].lower() not in (
        "i beat",
        "beats me",
    ):
        note = f'<p class="note">“{html.escape(record["threat_note"])}”</p>'

    return f"""
<article class="ecard {record["threat_kind"]}">
  <header class="ehead">
    <div class="who">
      <span class="alliance">{html.escape(record["alliance"])}</span>
      <h3>{html.escape(record["name"])}</h3>
    </div>
    <span class="badge {record["threat_kind"]}">{html.escape(record["threat_label"])}</span>
  </header>
  {troops}
  <p class="wl">{wl}</p>
  {meta_line}
  {_buffs_html(record)}
  {_generals_html(record)}
  {note}
  {seen}
</article>"""


def render_page(data: dict) -> str:
    counts = data["counts"]
    warning = (
        f'<p class="warn">{html.escape(data["warning"])}</p>' if data["warning"] else ""
    )

    alliance_chips = "".join(
        _chip(f"{alliance} · {count}")
        for alliance, count in counts["by_alliance"].items()
    )

    biggest = data["biggest_threat"]
    biggest_html = (
        f'<span class="stat big"><span>Biggest threat</span><b>'
        f'{html.escape(biggest["alliance"])} / {html.escape(biggest["name"])}</b>'
        f'<em>{biggest["max_troops_display"]} troops</em></span>'
        if biggest
        else ""
    )

    if data["enemies"]:
        cards = "".join(_card_html(record) for record in data["enemies"])
        body = f'<div class="egrid">{cards}</div>'
    else:
        body = '<p class="empty">No enemies learned yet. The bot seeds this table from parsed battle reports.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enemy Intel — Murder Bot</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }}
main {{ width: min(1200px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }}
a {{ color: #58a6ff; text-decoration: none; }}
header.top {{ display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .75rem; }}
h1 {{ margin: 0; font-size: 1.7rem; }}
.subtitle {{ margin: .35rem 0 0; color: #8b949e; font-size: .92rem; }}
.summary {{ display: flex; flex-wrap: wrap; align-items: stretch; gap: .6rem; margin: 1.2rem 0 .3rem; }}
.stat {{ display: flex; flex-direction: column; justify-content: center; padding: .55rem .95rem; background: #161b22; border: 1px solid #30363d; border-radius: 10px; font-size: .9rem; }}
.stat b {{ color: #fff; font-size: 1.05rem; }}
.stat span {{ color: #8b949e; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; }}
.stat.big em {{ color: #ff9d94; font-style: normal; font-size: .82rem; }}
.stat.wide {{ flex: 1 1 240px; }}
.alliances {{ display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }}
.warn {{ margin: 1rem 0; padding: .7rem 1rem; color: #d29922; background: #3d2f0b; border: 1px solid #9e6a03; border-radius: 8px; }}
.egrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; margin-top: 1.4rem; }}
.ecard {{ display: flex; flex-direction: column; gap: .55rem; padding: 1rem 1.1rem 1.15rem; background: #161b22; border: 1px solid #30363d; border-left-width: 4px; border-radius: 12px; }}
.ecard.bad {{ border-left-color: #f85149; }}
.ecard.good {{ border-left-color: #3fb950; }}
.ecard.neutral {{ border-left-color: #6e7681; }}
.ehead {{ display: flex; align-items: flex-start; justify-content: space-between; gap: .6rem; }}
.who {{ display: flex; flex-direction: column; gap: .25rem; }}
.alliance {{ align-self: flex-start; padding: .1rem .5rem; font-size: .72rem; font-weight: 700; letter-spacing: .04em; color: #adbac7; background: #21262d; border: 1px solid #30363d; border-radius: 6px; }}
.ehead h3 {{ margin: 0; font-size: 1.15rem; line-height: 1.15; }}
.badge {{ flex: none; padding: .2rem .55rem; font-size: .66rem; font-weight: 800; letter-spacing: .05em; border-radius: 999px; white-space: nowrap; }}
.badge.bad {{ color: #ffb3ad; background: #3a1614; border: 1px solid #6e2b26; }}
.badge.good {{ color: #7ee787; background: #12261a; border: 1px solid #1c3d28; }}
.badge.neutral {{ color: #adbac7; background: #21262d; border: 1px solid #30363d; }}
.troops {{ margin: .1rem 0 0; font-size: 1rem; }}
.troops b {{ color: #f2cc60; font-size: 1.28rem; letter-spacing: .01em; }}
.troops.muted {{ color: #6e7681; font-size: .85rem; }}
.wl {{ margin: 0; color: #adbac7; font-size: .86rem; }}
.meta {{ margin: 0; color: #8b949e; font-size: .8rem; overflow-wrap: anywhere; }}
.buffs h4, .generals h4 {{ margin: .35rem 0 .3rem; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: #8b949e; font-weight: 700; }}
.buff-row {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: .3rem .6rem; padding: .28rem .1rem; border-top: 1px solid #21262d; }}
.buff-type {{ min-width: 92px; font-size: .8rem; font-weight: 650; color: var(--type); }}
.buff-stats {{ display: flex; flex-wrap: wrap; gap: .55rem; }}
.stat-inline, .buff-stats .stat {{ font-size: .78rem; color: #e6edf3; padding: 0; background: none; border: 0; flex-direction: row; }}
.buff-stats .stat i {{ margin-right: .28rem; font-style: normal; color: #6e7681; font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; }}
.chips {{ display: flex; flex-wrap: wrap; gap: .35rem; }}
.chip {{ padding: .18rem .5rem; font-size: .76rem; color: #adbac7; background: #21262d; border: 1px solid #30363d; border-radius: 6px; }}
.chip.general {{ color: #d2a8ff; background: #1c1633; border-color: #3a2d63; }}
.chip.general i {{ margin-right: .3rem; font-style: normal; color: #8b7fb8; font-size: .68rem; text-transform: uppercase; letter-spacing: .04em; }}
.note {{ margin: .1rem 0 0; color: #ffb3ad; font-size: .82rem; font-style: italic; }}
.seen {{ margin: .15rem 0 0; color: #6e7681; font-size: .76rem; }}
.seen .rel {{ color: #8b949e; }}
.empty {{ margin-top: 2rem; padding: 1.2rem; color: #8b949e; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }}
footer {{ margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid #21262d; color: #6e7681; font-size: .8rem; line-height: 1.6; }}
@media (max-width: 520px) {{
  main {{ padding: 1.25rem 0 3rem; }}
  .egrid {{ grid-template-columns: 1fr; }}
  h1 {{ font-size: 1.4rem; }}
}}
</style>
</head>
<body>
<main>
<header class="top">
  <div><h1>Enemy Intel</h1><a href="/">&larr; Dashboard</a></div>
</header>
<p class="subtitle">Every player the bot has learned about, seeded from parsed battle reports. Sorted by threat, then by troop size.</p>
<div class="summary">
  <span class="stat"><span>Players known</span><b>{counts["total"]}</b></span>
  <span class="stat"><span>Beat you</span><b>{counts["beats_you"]}</b></span>
  <span class="stat"><span>You beat</span><b>{counts["you_beat"]}</b></span>
  <span class="stat wide"><span>By alliance</span><div class="alliances">{alliance_chips}</div></span>
  {biggest_html}
</div>
{warning}
{body}
<footer>
  <p><b>Source:</b> {html.escape(data["source"])}.</p>
  <p>Troop counts and buff magnitudes are shown fully expanded, never abbreviated.</p>
</footer>
</main>
</body>
</html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the enemy-intel router wired to the host app's auth + DB.

    Parameters
    ----------
    current_user:
        The host app's FastAPI auth dependency (``request -> user_id``).
    database:
        The host app's ``@contextmanager`` yielding a psycopg2 connection.
    """
    router = APIRouter(tags=["enemy-intel"])

    @router.get("/intel", response_class=HTMLResponse)
    def intel_page(_user_id: int = Depends(current_user)):
        return HTMLResponse(render_page(build_intel_data(database)))

    @router.get("/api/intel")
    def intel_data(_user_id: int = Depends(current_user)):
        return JSONResponse(build_intel_data(database))

    return router
