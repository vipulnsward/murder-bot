"""Evony-style data tables for the local keep_live dashboard."""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.routing import Mount

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "game_brain" / "reports"
ALLIANCE_DB = Path(os.environ.get("ALLIANCE_DB_PATH", ROOT / "game_brain" / "alliance.db"))
PAGES = {
    "battlefield": ("Battlefield", "/tables/battlefield"),
    "pvp": ("PvP", "/tables/pvp"),
    "monster-rallies": ("Monster rallies", "/tables/monster-rallies"),
    "mail": ("Mail", "/tables/mail"),
    "announcements": ("Announcements", "/tables/announcements"),
}
_manual_rows = {"mail": [], "announcements": []}
_refresh_status = {"mail": "", "announcements": ""}

CSS = """
:root{color-scheme:dark;--bg:#0a0806;--surface:#16120b;--surface2:#211a0e;
--border:#3a2f1a;--text:#efe6d2;--muted:#b8a888;--gold:#e6c35c;
--gold2:#f7dd8f;--good:#4ade80;--warn:#fbbf24;--bad:#f87171;
font-family:Geist,Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;min-width:320px;min-height:100vh;color:var(--text);
background:radial-gradient(1000px 480px at 12% -8%,rgba(230,195,92,.12),transparent 60%),
radial-gradient(900px 420px at 100% 0,rgba(192,57,43,.12),transparent 55%),var(--bg)}
a{color:inherit;text-decoration:none}.rail{position:fixed;inset:0 auto 0 0;width:52px;
display:flex;flex-direction:column;align-items:center;padding:8px 0;border-right:1px solid var(--border);
background:var(--surface);z-index:3}.brand,.rail a{width:40px;height:40px;display:grid;place-items:center;
border-radius:8px;margin:2px 0;color:var(--muted);font-size:18px}.brand{background:var(--gold);
color:#1c1105;font-size:12px;font-weight:800;margin-bottom:8px}.rail a:hover,.rail a.active{
background:var(--surface2);color:var(--gold2)}main{margin-left:52px;padding:24px;width:calc(100% - 52px)}
.heading{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:18px}
.eyebrow{margin:0;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
h1{margin:2px 0 0;font-family:Georgia,"Iowan Old Style",serif;font-size:24px;color:var(--gold2)}
.tabs{display:flex;gap:6px;overflow-x:auto;padding:2px 0 12px;scrollbar-width:thin}
.tabs a{white-space:nowrap;border:1px solid var(--border);border-radius:8px;padding:7px 11px;
color:var(--muted);font-size:14px}.tabs a:hover,.tabs a.active{color:var(--gold2);
border-color:var(--gold);background:rgba(230,195,92,.1)}.card{border:1px solid var(--border);
border-radius:12px;background:linear-gradient(180deg,rgba(42,33,18,.62),rgba(16,12,7,.94));
overflow:hidden}.table-wrap{max-height:calc(100vh - 190px);overflow:auto}
table{width:100%;border-collapse:collapse;min-width:760px}th,td{padding:11px 13px;
border-bottom:1px solid var(--border);text-align:left;vertical-align:top}thead th{position:sticky;
top:0;background:#19130a;z-index:1}th button{border:0;background:none;padding:0;color:var(--gold);
font:inherit;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;cursor:pointer}
th button:after{content:" ↕";color:var(--muted)}tbody tr:hover{background:rgba(230,195,92,.05)}
tbody tr:last-child td{border-bottom:0}.muted{color:var(--muted)}.num{font-variant-numeric:tabular-nums}
.badge{display:inline-block;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700;
color:var(--gold2);background:rgba(230,195,92,.14)}.win{color:var(--good)}.loss{color:var(--bad)}
.empty{text-align:center;color:var(--muted);padding:40px 16px}.actions{display:flex;gap:8px;align-items:center}
.refresh{border:0;border-radius:8px;background:var(--gold);color:#1c1105;padding:8px 12px;
font-weight:700;cursor:pointer}.notice{margin:0 0 12px;color:var(--muted);font-size:13px}
@media(max-width:640px){main{padding:16px 12px}.heading{align-items:start;flex-direction:column}
.table-wrap{max-height:calc(100vh - 220px)}th,td{padding:9px 10px;font-size:13px}}
"""

SCRIPT = """
document.querySelectorAll("th button").forEach(button=>button.addEventListener("click",()=>{
 const table=button.closest("table"),body=table.tBodies[0],index=button.parentElement.cellIndex;
 const asc=button.dataset.order!=="asc";button.dataset.order=asc?"asc":"desc";
 [...body.rows].sort((a,b)=>a.cells[index].innerText.localeCompare(
 b.cells[index].innerText,undefined,{numeric:true,sensitivity:"base"})*(asc?1:-1))
 .forEach(row=>body.appendChild(row));
}));
"""


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _reports() -> list[dict]:
    rows = []
    for path in REPORTS_DIR.glob("*/extracted.json"):
        data = _read_json(path)
        if isinstance(data, dict):
            rows.append(data)
    return sorted(rows, key=lambda row: row.get("timestamp") or "", reverse=True)


def _number(value) -> str:
    if value is None:
        return "—"
    try:
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(value) >= divisor:
            return f"{value / divisor:.1f}{suffix}"
    return f"{value:,}"


def _metric(stats: dict, name: str) -> str:
    value = stats.get(name)
    if isinstance(value, dict):
        return f"A {_number(value.get('attacker'))} / D {_number(value.get('defender'))}"
    return _number(value)


def battlefield_rows() -> list[list[str]]:
    rows = []
    for report in _reports():
        title = str(report.get("title") or "")
        if "pvp" not in str(report.get("kind") or "").lower() and not re.search(
            r"attack|defend|defenses|scout", title, re.I
        ):
            continue
        participants = report.get("participants") or []
        attacker = report.get("attacker")
        defender = report.get("defender")
        for participant in participants:
            if participant.get("role") == "attacker":
                attacker = attacker or participant.get("name")
            elif participant.get("role") == "defender":
                defender = defender or participant.get("name")
        if not attacker and participants and "defend" in title.lower():
            attacker = participants[0].get("name")
        stats = report.get("stats") or {}
        rows.append([
            str(attacker or "—"),
            str(defender or ("Our city" if attacker else "—")),
            _metric(stats, "wounded"),
            _metric(stats, "killed"),
            str(report.get("outcome") or "—").title(),
            str(report.get("timestamp") or "—"),
        ])
    return rows


def _lead_type(buffs) -> str | None:
    if not isinstance(buffs, dict):
        return None
    ranked = []
    for troop in ("ground", "ranged", "mounted", "siege"):
        values = buffs.get(troop)
        if isinstance(values, dict):
            try:
                ranked.append((float(values.get("attack") or 0), troop))
            except (TypeError, ValueError):
                pass
    return max(ranked)[1] if ranked else None


def _threat(row: dict) -> str:
    if row.get("threat"):
        return str(row["threat"])
    wins, losses = int(row.get("my_wins") or 0), int(row.get("my_losses") or 0)
    troops = int(row.get("max_troops") or 0)
    if losses > wins or troops >= 1_000_000_000:
        return "critical"
    if troops >= 500_000_000:
        return "high"
    if troops >= 100_000_000:
        return "medium"
    return "low"


def _counter_names(lead_type: str | None) -> str:
    if not lead_type:
        return "—"
    try:
        from counter_general import recommend_counters

        picks = recommend_counters(lead_type, top=3).get("recommendations", [])
        return ", ".join(pick["general"] for pick in picks) or "—"
    except Exception:
        return "—"


def _postgres_enemies() -> list[dict]:
    try:
        import psycopg2
        import psycopg2.extras

        with psycopg2.connect(dbname=os.environ.get("MURDERBOT_DB", "murderbot")) as connection:
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                """SELECT name, alliance, battles, my_wins, my_losses, max_troops,
                          coords, buffs, generals, threat, last_seen
                   FROM enemies ORDER BY last_seen DESC NULLS LAST, name"""
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def _sqlite_enemies() -> list[dict]:
    if not ALLIANCE_DB.is_file():
        return []
    try:
        with sqlite3.connect(ALLIANCE_DB) as connection:
            connection.row_factory = sqlite3.Row
            return [
                {
                    **dict(row), "battles": 0, "my_wins": 0, "my_losses": 0,
                    "max_troops": int(float(row["power_millions"]) * 1_000_000),
                    "buffs": {row["lead_type"]: {"attack": 1}},
                    "threat": None,
                }
                for row in connection.execute(
                    """SELECT name, alliance, power_millions, lead_type, coords, updated_at
                       FROM alliance_threats ORDER BY power_millions DESC"""
                )
            ]
    except (OSError, sqlite3.Error):
        return []


def pvp_rows() -> list[list[str]]:
    enemies = {str(row["name"]).casefold(): row for row in _postgres_enemies()}
    for row in _sqlite_enemies():
        enemies.setdefault(str(row["name"]).casefold(), row)
    rows = []
    for row in enemies.values():
        lead = row.get("lead_type") or _lead_type(row.get("buffs"))
        rows.append([
            str(row.get("name") or "—"),
            str(row.get("alliance") or "?"),
            f"{int(row.get('my_wins') or 0)}/{int(row.get('my_losses') or 0)}",
            _threat(row).title(),
            str(lead or "—").title(),
            _counter_names(lead),
            str(row.get("last_seen") or row.get("updated_at") or "—"),
        ])
    return rows


def _live_rallies() -> list[list[str]]:
    """Read only the already-shared frame; never fall back to adb or tap the device."""
    try:
        import live_rally
        import ocr_read
        import shared_capture

        frame = shared_capture.grab(fallback=False)
        if frame is None or not live_rally.on_war_screen(frame):
            return []
        tokens = ocr_read.read_all(frame)
    except Exception:
        return []
    rows = []
    for status in live_rally.read_rallies(frame):
        y = status.get("join_xy", (0, 0))[1] if status.get("join_xy") else 0
        nearby = " ".join(str(text) for text, (_x, cy), _cf in tokens if not y or abs(cy - y) < 120)
        match = re.search(r"\bLv\.?\s*(\d+)\s+(.+?)(?:\s+\d{1,2}:\d{2}|$)", nearby, re.I)
        countdown = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", nearby)
        rows.append([
            match.group(2).strip() if match else "Boss monster",
            match.group(1) if match else "—",
            countdown.group(0) if countdown else "—",
            str(status["status"]).title(),
        ])
    return rows


def monster_rows() -> list[list[str]]:
    live = _live_rallies()
    if live:
        return live
    rows = []
    for report in _reports():
        match = re.match(r"\s*Lv\.?\s*(\d+)\s+(.+)", str(report.get("title") or ""), re.I)
        if match:
            rows.append([
                match.group(2).strip(),
                match.group(1),
                "Complete",
                "Joined · complete" if report.get("outcome") == "win" else str(report.get("outcome") or "Seen"),
            ])
        if len(rows) == 25:
            break
    return rows


def _captured_rows(kind: str) -> list[list[str]]:
    for path in (ROOT / "game_brain" / "live" / f"{kind}.json", ROOT / "game_brain" / f"{kind}.json"):
        data = _read_json(path)
        if isinstance(data, list):
            return [[str(cell) for cell in row] for row in data if isinstance(row, list)]
    return _manual_rows[kind]


def _ocr_lines(tokens) -> list[str]:
    lines: list[list[tuple[int, str]]] = []
    centers: list[int] = []
    for text, (x, y), confidence in sorted(tokens, key=lambda item: (item[1][1], item[1][0])):
        if confidence < 0.5:
            continue
        target = next((i for i, center in enumerate(centers) if abs(center - y) < 28), None)
        if target is None:
            centers.append(y)
            lines.append([])
            target = len(lines) - 1
        lines[target].append((x, str(text).strip()))
    return [" ".join(text for _x, text in sorted(line)) for line in lines]


def parse_mail(tokens) -> list[list[str]]:
    rows = []
    for line in _ocr_lines(tokens):
        stamp = re.search(r"\b(?:\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?|\d+\s*[mhd]\s+ago)\b", line, re.I)
        if not stamp:
            continue
        text = line.replace(stamp.group(0), "").strip(" -|")
        parts = re.split(r"\s{2,}|\s+[|·]\s+", text, maxsplit=1)
        rows.append([parts[0] if len(parts) > 1 else "—", parts[-1] or "—", stamp.group(0)])
    return rows


def parse_announcements(tokens) -> list[list[str]]:
    rows = []
    for line in _ocr_lines(tokens):
        if not re.search(r"announcement|notice|server|alliance", line, re.I):
            continue
        stamp = re.search(r"\b(?:\d{1,2}:\d{2}|\d+\s*[mhd]\s+ago)\b", line, re.I)
        kind = "Server" if "server" in line.lower() else "Alliance"
        rows.append([kind, line, stamp.group(0) if stamp else "—"])
    return rows


def manual_refresh(kind: str) -> str:
    """One explicit, read-only OCR pass; no forward navigation or control taps."""
    try:
        import game_mapper
        import live_map
        import ocr_read
        import screen_fsm
        import shared_capture

        frame = shared_capture.grab(fallback=False)
        if frame is None:
            return "No fresh shared frame; no device capture was attempted."
        if screen_fsm.is_disconnect(frame):
            return "Disconnected screen detected; refresh aborted without tapping."
        tokens = ocr_read.read_all(frame)
        if game_mapper._is_forbidden(*(text for text, _center, _confidence in tokens)):
            return "Unsafe purchase/action wording detected; refresh refused."
        parser = parse_mail if kind == "mail" else parse_announcements
        rows = parser(tokens)
        _manual_rows[kind] = rows
        return f"Read {len(rows)} row(s) from the current screen."
    except Exception as error:
        return f"Refresh unavailable: {type(error).__name__}."
    finally:
        try:
            live_map.clear_popups(max_iters=4)
        except Exception:
            pass


def _cell(value: str, index: int) -> str:
    cls = "num" if index > 1 else ""
    if value.lower() == "win":
        cls += " win"
    elif value.lower() == "loss":
        cls += " loss"
    return f'<td class="{cls.strip()}">{html.escape(value)}</td>'


def render_page(key: str, headers: list[str], rows: list[list[str]], empty: str) -> str:
    title, _path = PAGES[key]
    nav = "".join(
        f'<a class="{"active" if page == key else ""}" href="{path}">{html.escape(label)}</a>'
        for page, (label, path) in PAGES.items()
    )
    rail = [
        ("/", "▚", "Dashboard"),
        ("/live", "⧉", "Live"),
        ("/tasks", "☰", "Tasks"),
        ("/config", "⚙", "Config"),
        ("/generals", "♜", "Generals"),
        ("/knowledge", "◈", "Knowledge"),
        ("/tables/battlefield", "▤", "Game tables"),
    ]
    rail_html = "".join(
        f'<a class="{"active" if label == "Game tables" else ""}" href="{path}" title="{label}" '
        f'aria-label="{label}">{icon}</a>' for path, icon, label in rail
    )
    head = "".join(f"<th><button>{html.escape(label)}</button></th>" for label in headers)
    body = "".join("<tr>" + "".join(_cell(value, i) for i, value in enumerate(row)) + "</tr>" for row in rows)
    if not body:
        body = f'<tr><td class="empty" colspan="{len(headers)}">{html.escape(empty)}</td></tr>'
    refresh = ""
    notice = ""
    if key in _manual_rows:
        refresh = f'<form method="post" action="/tables/{key}/refresh"><button class="refresh" type="submit">Refresh once</button></form>'
        notice = (
            '<p class="notice">Manual only: reads the current shared game screen once, refuses '
            "purchase/action wording, then returns safely to the city.</p>"
        )
        if _refresh_status[key]:
            notice += f'<p class="notice">{html.escape(_refresh_status[key])}</p>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — Murder Bot</title>
<style>{CSS}</style></head><body><nav class="rail" aria-label="Dashboard"><span class="brand">MB</span>{rail_html}</nav>
<main><div class="heading"><div><p class="eyebrow">Evony data tables</p><h1>{html.escape(title)}</h1></div>
<div class="actions">{refresh}</div></div><nav class="tabs" aria-label="Game tables">{nav}</nav>{notice}
<section class="card"><div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
</div></section></main><script>{SCRIPT}</script></body></html>"""


def register_game_tables(app) -> None:
    """Register table routes before the keep frontend's catch-all static mount."""
    router = APIRouter(tags=["game-tables"])

    @router.get("/tables")
    def tables():
        return RedirectResponse("/tables/battlefield", status_code=307)

    @router.get("/tables/battlefield", response_class=HTMLResponse)
    def battlefield():
        return HTMLResponse(render_page(
            "battlefield", ["Attacker", "Defender", "Troops lost", "Troops killed", "Result", "Time"],
            battlefield_rows(), "No recorded PvP battle reports yet.",
        ))

    @router.get("/tables/pvp", response_class=HTMLResponse)
    def pvp():
        return HTMLResponse(render_page(
            "pvp", ["Enemy", "Alliance", "W/L", "Threat", "Lead", "Recommended counters", "Last seen"],
            pvp_rows(), "No tracked enemies yet.",
        ))

    @router.get("/tables/monster-rallies", response_class=HTMLResponse)
    def monsters():
        return HTMLResponse(render_page(
            "monster-rallies", ["Boss", "Level", "Time left", "Join status"],
            monster_rows(), "No monster rallies have been captured yet.",
        ))

    @router.get("/tables/mail", response_class=HTMLResponse)
    def mail():
        return HTMLResponse(render_page(
            "mail", ["Sender", "Subject / snippet", "Time"], _captured_rows("mail"),
            "No parsed mail captured. Open Mail in Evony, then use Refresh once.",
        ))

    @router.get("/tables/announcements", response_class=HTMLResponse)
    def announcements():
        return HTMLResponse(render_page(
            "announcements", ["Scope", "Announcement", "Time"], _captured_rows("announcements"),
            "No announcements captured. Open the announcements screen, then use Refresh once.",
        ))

    @router.post("/tables/{kind}/refresh")
    def refresh(kind: str):
        if kind not in _manual_rows:
            return RedirectResponse("/tables/battlefield", status_code=303)
        _refresh_status[kind] = manual_refresh(kind)
        return RedirectResponse(f"/tables/{kind}?{urlencode({'refreshed': '1'})}", status_code=303)

    mounts = [route for route in app.router.routes if isinstance(route, Mount) and route.path == ""]
    app.router.routes[:] = [route for route in app.router.routes if route not in mounts]
    app.include_router(router)
    app.router.routes.extend(mounts)
