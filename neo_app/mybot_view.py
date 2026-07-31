"""Latest local-bot report dashboard and sync endpoint."""

from __future__ import annotations

import hmac
import html
import json
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("MYBOT_DB_PATH") or (REPO_ROOT / "game_brain" / "mybot.db"))
LOCAL_LIVE_URL = "http://127.0.0.1:8088/"

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
h1,h2{font-family:Georgia,"Iowan Old Style",serif;color:var(--gold2)}h1{margin:0}
a{color:var(--gold);text-decoration:none}.muted{color:var(--mut)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;margin:1.25rem 0}
.card,.table-wrap{border:1px solid var(--line);border-radius:12px;
  background:linear-gradient(180deg,rgba(42,33,18,.6),rgba(16,12,7,.9));padding:1rem}
.card h2{margin:.1rem 0 .8rem;font-size:1rem}.stats{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}
.stats span{color:var(--mut);font-size:.78rem;text-transform:uppercase}.stats b{display:block;color:var(--ink);font-size:1.05rem}
.table-wrap{padding:0;overflow-x:auto}table{width:100%;border-collapse:collapse}
th,td{padding:.75rem;border-bottom:1px solid var(--line);text-align:left}
thead th{color:var(--gold);font-size:.78rem;letter-spacing:.04em;text-transform:uppercase}
tbody tr:last-child td{border-bottom:0}.empty{color:var(--mut)}
.badge{display:inline-block;padding:.18rem .55rem;border-radius:999px;font-size:.78rem;font-weight:700;
  color:var(--gold);background:rgba(230,195,92,.14)}.badge.off{color:#e58b7e;background:rgba(192,57,43,.18)}
</style>
"""


class Account(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    level: int | None = None
    vip: int | None = None
    alliance: str | None = Field(default=None, max_length=30)
    power: int | None = None


class Troop(BaseModel):
    building: str
    tier: int
    name: str
    own: int | None


class Rally(BaseModel):
    total_joined: int
    cycles: int
    last_ts: str | None = None


class Status(BaseModel):
    running: bool
    screen: str | None = None
    stamina: str | None = None
    uptime: str | None = None


class Claims(BaseModel):
    """Free resources auto-claimed by the bot (Alliance Gifts + Alliance Treasure)."""

    gift_open_alls: int = 0
    gift_claims: int = 0
    treasure_open_alls: int = 0
    treasure_opens: int = 0
    last_claim_ts: str | None = None


class Daemon(BaseModel):
    name: str = Field(max_length=40)
    running: bool


class Event(BaseModel):
    ts: str | None = None
    text: str = Field(max_length=240)


class BotReport(BaseModel):
    account: Account
    roster: list[Troop]
    rally: Rally
    status: Status
    # All optional so older sync clients keep validating (backward compatible).
    claims: Claims | None = None
    daemons: list[Daemon] = Field(default_factory=list)
    activity: list[Event] = Field(default_factory=list)


def _initialize(db_path: str | Path = DB_PATH) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mybot_reports (
                account_name TEXT PRIMARY KEY COLLATE NOCASE,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def store_report(report: BotReport, db_path: str | Path = DB_PATH) -> dict:
    payload = report.model_dump(mode="json")
    _initialize(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO mybot_reports (account_name, payload, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(account_name) DO UPDATE SET
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (report.account.name, json.dumps(payload, separators=(",", ":"))),
        )
    return payload


def latest_report(db_path: str | Path = DB_PATH) -> dict | None:
    _initialize(db_path)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT payload FROM mybot_reports ORDER BY updated_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    return json.loads(row[0]) if row else None


def _display(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, int):
        return f"{value:,}{suffix}"
    return f"{html.escape(str(value))}{suffix}"


def render_page(report: dict | None) -> str:
    if report is None:
        content = '<p class="card empty">No local-bot report received yet.</p>'
    else:
        account, rally, status = report["account"], report["rally"], report["status"]
        claims = report.get("claims") or {}
        daemons = report.get("daemons") or []
        activity = report.get("activity") or []
        rows = "".join(
            "<tr>"
            f'<td>{html.escape(troop["building"])}</td>'
            f'<td>{troop["tier"]}</td>'
            f'<td>{html.escape(troop["name"])}</td>'
            f'<td>{_display(troop["own"])}</td>'
            "</tr>"
            for troop in report["roster"]
        ) or '<tr><td class="empty" colspan="4">No roster data.</td></tr>'
        running = status["running"]

        gift_n = int(claims.get("gift_open_alls", 0)) + int(claims.get("gift_claims", 0))
        tre_n = int(claims.get("treasure_open_alls", 0)) + int(claims.get("treasure_opens", 0))

        daemon_html = "".join(
            f'<div><span>{html.escape(str(d.get("name", "")))}</span>'
            f'<b><span class="badge{"" if d.get("running") else " off"}">'
            f'{"UP" if d.get("running") else "DOWN"}</span></b></div>'
            for d in daemons
        ) or '<div class="muted">No daemon status.</div>'

        feed = "".join(
            f'<li><span class="ts">{html.escape(str(e.get("ts") or ""))}</span>'
            f'{html.escape(str(e.get("text", "")))}</li>'
            for e in activity
        ) or '<li class="empty">No recent activity.</li>'

        claims_card = f"""
  <section class="card"><h2>Free resources claimed</h2><div class="stats">
    <div><span>Alliance gifts</span><b>{_display(gift_n)}</b></div>
    <div><span>Treasure opens</span><b>{_display(tre_n)}</b></div>
    <div><span>Last claim</span><b>{_display(claims.get("last_claim_ts"))}</b></div>
  </div></section>""" if claims else ""

        daemons_card = f"""
  <section class="card"><h2>Daemons</h2><div class="stats">{daemon_html}</div></section>""" if daemons else ""

        activity_section = f"""
<h2>Recent activity</h2>
<div class="table-wrap"><ul class="feed">{feed}</ul></div>""" if activity else ""

        content = f"""
<div class="cards">
  <section class="card"><h2>Account</h2><div class="stats">
    <div><span>Name</span><b>{_display(account["name"])}</b></div>
    <div><span>Alliance</span><b>{_display(account["alliance"])}</b></div>
    <div><span>Level</span><b>{_display(account["level"])}</b></div>
    <div><span>VIP</span><b>{_display(account["vip"])}</b></div>
    <div><span>Power</span><b>{_display(account["power"])}</b></div>
  </div></section>
  <section class="card"><h2>Rally</h2><div class="stats">
    <div><span>Total joined</span><b>{_display(rally["total_joined"])}</b></div>
    <div><span>Cycles</span><b>{_display(rally["cycles"])}</b></div>
    <div><span>Last update</span><b>{_display(rally["last_ts"])}</b></div>
  </div></section>
  <section class="card"><h2>Live status</h2>
    <p><span class="badge{' off' if not running else ''}">{'RUNNING' if running else 'OFFLINE'}</span></p>
    <p class="muted">Screen: {_display(status["screen"])}</p>
    <p class="muted">Stamina: {_display(status.get("stamina"))} &middot; Uptime: {_display(status.get("uptime"))}</p>
    <a href="{LOCAL_LIVE_URL}" target="_blank" rel="noopener">Open local live view &rarr;</a>
  </section>{claims_card}{daemons_card}
</div>
{activity_section}
<h2>Troop roster</h2>
<div class="table-wrap"><table>
<thead><tr><th>Building</th><th>Tier</th><th>Name</th><th>Owned</th></tr></thead>
<tbody>{rows}</tbody>
</table></div>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>My Bot — Murder Bot</title>{SHARED_CSS}
<style>.feed{{list-style:none;margin:0;padding:.4rem .2rem}}
.feed li{{padding:.55rem .8rem;border-bottom:1px solid var(--line);font-size:.9rem}}
.feed li:last-child{{border-bottom:0}}.feed .ts{{color:var(--gold);margin-right:.6rem;font-variant-numeric:tabular-nums}}</style>
</head>
<body><main><header><div><h1>My Bot</h1><p class="muted">Live Evony bot telemetry &middot; auto-refreshes every 30s.</p></div>
<a href="/">&larr; Dashboard</a></header>{content}</main></body></html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the local-bot router wired to the host app's auth dependency."""
    router = APIRouter(tags=["mybot"])

    @router.post("/api/mybot/report")
    def report_bot(
        report: BotReport,
        x_sync_token: str | None = Header(default=None, alias="X-Sync-Token"),
    ):
        expected = os.environ.get("MYBOT_SYNC_TOKEN")
        if expected and (x_sync_token is None or not hmac.compare_digest(x_sync_token, expected)):
            raise HTTPException(status_code=401, detail="Invalid sync token")
        return JSONResponse(store_report(report))

    @router.get("/api/mybot")
    def mybot_api(_user_id: int = Depends(current_user)):
        report = latest_report()
        if report is None:
            raise HTTPException(status_code=404, detail="No bot report received yet")
        return JSONResponse(report)

    @router.get("/mybot", response_class=HTMLResponse)
    def mybot_page(_user_id: int = Depends(current_user)):
        return HTMLResponse(render_page(latest_report()))

    return router
