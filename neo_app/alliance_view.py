"""Alliance Threat Board.

Self-contained FastAPI router using the same ``build_router(current_user,
database)`` factory as the other feature views. Threats are stored in the
local ``game_brain/alliance.db`` SQLite database.
"""

from __future__ import annotations

import html
import os
import sqlite3
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DB_PATH = Path(os.environ.get("ALLIANCE_DB_PATH") or (REPO_ROOT / "game_brain" / "alliance.db"))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from counter_general import recommend_counters  # noqa: E402


SHARED_CSS = """
<style>
:root{color-scheme:dark;--bg:#0a0806;--card:#16120b;--line:#3a2f1a;
  --ink:#efe6d2;--mut:#b8a888;--gold:#e6c35c;--gold2:#f7dd8f;--red:#c0392b;
  font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--ink);
  background:radial-gradient(1200px 520px at 14% -8%,rgba(230,195,92,.10),transparent 60%),
  radial-gradient(1000px 480px at 100% 0%,rgba(192,57,43,.14),transparent 55%),var(--bg)}
main{width:min(1100px,92vw);margin:0 auto;padding:2.6rem 0}
header{display:flex;align-items:center;justify-content:space-between;gap:1rem}
h1{margin:0;font-family:Georgia,"Iowan Old Style",serif;color:var(--gold2)}
a{color:var(--gold);text-decoration:none}.status{color:var(--mut)}
.table-wrap{margin-top:1.25rem;overflow-x:auto;border:1px solid var(--line);border-radius:12px;
  background:linear-gradient(180deg,rgba(42,33,18,.6),rgba(16,12,7,.9))}
table{width:100%;border-collapse:collapse}
th,td{padding:.75rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
thead th{color:var(--gold);font-size:.78rem;letter-spacing:.04em;text-transform:uppercase}
tbody tr:last-child td{border-bottom:0}.empty{padding:1rem;color:var(--mut)}
.badge{display:inline-block;padding:.14rem .5rem;border-radius:999px;font-size:.78rem;
  font-weight:700;color:var(--gold);background:rgba(230,195,92,.14)}
.counter{display:block;margin-bottom:.25rem;white-space:nowrap}
</style>
"""


class ThreatInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    alliance: str = Field(default="?", max_length=20)
    power_millions: float = Field(ge=0)
    lead_type: Literal["ground", "ranged", "mounted", "siege"]
    coords: str = Field(default="", max_length=100)

    @field_validator("name", "alliance", "coords")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value:
            raise ValueError("name must not be blank")
        return value


def _initialize(db_path: str | Path = DB_PATH) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alliance_threats (
                name TEXT PRIMARY KEY COLLATE NOCASE,
                alliance TEXT NOT NULL DEFAULT '?',
                power_millions REAL NOT NULL CHECK (power_millions >= 0),
                lead_type TEXT NOT NULL
                    CHECK (lead_type IN ('ground', 'ranged', 'mounted', 'siege')),
                coords TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _threat_level(power_millions: float) -> str:
    if power_millions >= 1000:
        return "critical"
    if power_millions >= 500:
        return "high"
    if power_millions >= 100:
        return "medium"
    return "low"


def _counters(lead_type: str) -> list[dict]:
    try:
        return recommend_counters(lead_type, top=3).get("recommendations", [])
    except Exception:
        return []


def _shape(row: sqlite3.Row) -> dict:
    power = float(row["power_millions"])
    return {
        "name": row["name"],
        "alliance": row["alliance"],
        "power_millions": power,
        "lead_type": row["lead_type"],
        "coords": row["coords"],
        "threat": _threat_level(power),
        "counters": _counters(row["lead_type"]),
        "updated_at": row["updated_at"],
    }


def list_threats(db_path: str | Path = DB_PATH) -> list[dict]:
    """Return every tracked enemy, strongest first."""
    _initialize(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT name, alliance, power_millions, lead_type, coords, updated_at
            FROM alliance_threats
            ORDER BY power_millions DESC, name COLLATE NOCASE
            """
        ).fetchall()
    return [_shape(row) for row in rows]


def add_threat(enemy: ThreatInput, db_path: str | Path = DB_PATH) -> dict:
    """Add or update one scouted enemy and return the stored threat."""
    _initialize(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO alliance_threats
                (name, alliance, power_millions, lead_type, coords)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                name = excluded.name,
                alliance = excluded.alliance,
                power_millions = excluded.power_millions,
                lead_type = excluded.lead_type,
                coords = excluded.coords,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                enemy.name,
                enemy.alliance or "?",
                enemy.power_millions,
                enemy.lead_type,
                enemy.coords,
            ),
        )
        row = connection.execute(
            """
            SELECT name, alliance, power_millions, lead_type, coords, updated_at
            FROM alliance_threats WHERE name = ? COLLATE NOCASE
            """,
            (enemy.name,),
        ).fetchone()
    return _shape(row)


def render_page(threats: list[dict]) -> str:
    rows = []
    for threat in threats:
        counters = "".join(
            f'<span class="counter">{html.escape(counter["general"])}</span>'
            for counter in threat["counters"]
        ) or "—"
        rows.append(
            "<tr>"
            f'<td><b>{html.escape(threat["name"])}</b></td>'
            f'<td>{html.escape(threat["alliance"])}</td>'
            f'<td>{threat["power_millions"]:,.1f}M</td>'
            f'<td>{html.escape(threat["lead_type"].title())}</td>'
            f'<td><span class="badge">{html.escape(threat["threat"].upper())}</span></td>'
            f"<td>{counters}</td>"
            "</tr>"
        )
    body = (
        "".join(rows)
        if rows
        else '<tr><td class="empty" colspan="6">No enemies tracked yet.</td></tr>'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alliance Threat Board — Murder Bot</title>
{SHARED_CSS}
</head>
<body>
<main>
<header>
  <div>
    <h1>Alliance Threat Board</h1>
    <p class="status">Scouted enemies and the top generals to counter each lead.</p>
  </div>
  <a href="/">&larr; Dashboard</a>
</header>
<div class="table-wrap">
<table>
<thead><tr><th>Name</th><th>Alliance</th><th>Power</th><th>Lead type</th><th>Threat</th><th>Top counters</th></tr></thead>
<tbody>{body}</tbody>
</table>
</div>
</main>
</body>
</html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the alliance router wired to the host app's auth dependency."""
    router = APIRouter(tags=["alliance"])

    @router.get("/alliance", response_class=HTMLResponse)
    def alliance_page(_user_id: int = Depends(current_user)):
        return HTMLResponse(render_page(list_threats()))

    @router.get("/api/alliance/threats")
    def alliance_threats(_user_id: int = Depends(current_user)):
        return JSONResponse(list_threats())

    @router.post("/api/alliance/threats")
    def add_alliance_threat(
        enemy: ThreatInput, _user_id: int = Depends(current_user)
    ):
        return JSONResponse(add_threat(enemy))

    return router
