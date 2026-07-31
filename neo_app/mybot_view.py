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


def _total_troops(report: dict) -> int:
    try:
        return sum(int(t.get("own") or 0) for t in report.get("roster", []))
    except Exception:
        return 0


DEMO_COUNTER_WIDGET = """
<style>
.counter-demo{margin:2.2rem 0}
.cbox{border:1px solid var(--line);border-radius:14px;padding:1.2rem;background:linear-gradient(180deg,rgba(42,33,18,.6),rgba(16,12,7,.9))}
.crow{display:flex;gap:1rem;flex-wrap:wrap;align-items:flex-end}
.crow label{display:flex;flex-direction:column;gap:.35rem;font-size:.76rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}
.crow input,.crow select{padding:.55rem .6rem;background:#0d0a06;color:var(--ink);border:1px solid var(--line);border-radius:8px;font-size:.95rem;min-width:8.5rem}
.crow button{padding:.62rem 1.3rem;background:linear-gradient(180deg,#f7dd8f,#e6c35c);color:#2a1f08;border:0;border-radius:9px;font-weight:800;cursor:pointer;font-size:.98rem}
.cout{margin-top:1rem;padding:1rem 1.1rem;border:1px solid var(--line);border-radius:10px;background:#0d0a06;font-size:.92rem;line-height:1.55}
.cout .act{font-size:1.25rem;font-weight:800;color:var(--gold2);text-wrap:balance}
.cout .conf{color:var(--mut);font-size:.82rem;margin-top:.35rem}
</style>
<section class="counter-demo">
  <h2>Watch the AI counter a live attack</h2>
  <p class="muted">Set an incoming rally, hit counter &mdash; the exact battle-sim brain that runs on every account. No signup.</p>
  <div class="cbox">
    <div class="crow">
      <label>Incoming power (M)<input id="cd-power" type="number" value="60" min="1" max="5000"></label>
      <label>Their lead<select id="cd-lead"><option>SIEGE</option><option>GROUND</option><option>RANGED</option><option>MOUNTED</option></select></label>
      <button id="cd-go" type="button">Counter it &rarr;</button>
    </div>
    <div id="cd-out" class="cout">Set an attack and hit <b>Counter it</b>.</div>
  </div>
</section>
<script>
async function mbRunCounter(){
  var out=document.getElementById("cd-out"); if(!out) return;
  var power=document.getElementById("cd-power").value||60;
  var lead=document.getElementById("cd-lead").value||"SIEGE";
  out.textContent="Running the battle sim…";
  try{
    var r=await fetch("/api/demo-counter?power="+encodeURIComponent(power)+"&lead="+encodeURIComponent(lead));
    var p=await r.json();
    var conf=(p.confidence!=null)?Math.round(p.confidence*100)+"% confidence":"";
    var lt=p.lead_type?" · counter-lead "+p.lead_type:"";
    var gens="";
    if(p.counter_generals&&p.counter_generals.length){
      gens='<div style="margin-top:10px"><div style="font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;opacity:.7">Field these generals</div>'+
        p.counter_generals.slice(0,3).map(function(g){return '<div style="margin-top:4px"><b>'+((g.general||"")+"").replace(/[<>&]/g,"")+'</b><span style="opacity:.7"> — '+((g.counter_type||"")+"")+(g.tier?' · Tier '+g.tier:"")+'</span></div>';}).join("")+'</div>';
    }
    out.innerHTML='<div class="act">'+((p.action||"—")+"").replace(/[<>]/g,"")+lt+'</div><div style="margin-top:8px">'+((p.reasoning||"")+"").replace(/[<>]/g,"")+'</div><div class="conf">'+conf+'</div>'+gens;
  }catch(e){out.textContent="Brain unavailable, try again in a moment.";}
}
(function(){var b=document.getElementById("cd-go"); if(b){b.addEventListener("click",mbRunCounter); mbRunCounter();}})();
</script>
"""


def render_demo(report: dict | None) -> str:
    """PUBLIC, anonymized live-demo landing page: proof the bot runs 24/7, plus a free-trial
    CTA. Deliberately shows NO monarch name and NO per-unit roster (publicly naming a botted
    account is a ban risk) — only aggregate activity that proves the automation is alive."""
    if report is None:
        rally = {"total_joined": 0, "cycles": 0, "last_ts": None}
        claims: dict = {}
        daemons: list = []
        activity: list = []
        status = {"running": False, "uptime": None}
        troops = 0
    else:
        rally = report.get("rally", {})
        claims = report.get("claims") or {}
        daemons = report.get("daemons") or []
        activity = report.get("activity") or []
        status = report.get("status", {})
        troops = _total_troops(report)

    up = sum(1 for d in daemons if d.get("running"))
    total_d = len(daemons) or 6
    gifts = int(claims.get("gift_open_alls", 0)) + int(claims.get("gift_claims", 0))
    treasure = int(claims.get("treasure_open_alls", 0)) + int(claims.get("treasure_opens", 0))
    # "Live" = the automation is running, i.e. the rally daemon is up. A single-frame grab
    # (status.running) momentarily returns None during a game reload, so it's too flaky to
    # gate the badge on; the rally daemon being up is the honest, stable signal.
    rally_up = any(d.get("name") == "rally" and d.get("running") for d in daemons)
    live = rally_up or bool(status.get("running"))
    live_badge = ('<span class="live"><span class="dot"></span>LIVE NOW</span>' if live
                  else '<span class="live off"><span class="dot"></span>STARTING…</span>')

    def tile(label, value):
        return (f'<div class="tile"><b>{_display(value)}</b>'
                f'<span>{html.escape(label)}</span></div>')

    tiles = "".join([
        tile("Rallies joined", rally.get("total_joined", 0)),
        tile("Loop cycles", rally.get("cycles", 0)),
        tile("Alliance gifts claimed", gifts),
        tile("Treasure chests opened", treasure),
        tile("Troops under management", troops),
        tile("Daemons online", f"{up}/{total_d}"),
    ])
    feed = "".join(
        f'<li><span class="ts">{html.escape(str(e.get("ts") or ""))}</span>'
        f'{html.escape(str(e.get("text", "")))}</li>'
        for e in activity
    ) or '<li class="empty">warming up…</li>'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<meta name="description" content="Watch Murder Bot run a live Evony account 24/7 — joining rallies, claiming alliance gifts and treasure, and countering attacks with a battle-sim AI. Try the counter engine free.">
<title>Murder Bot — a live Evony bot, running right now</title>{SHARED_CSS}
<style>
.hero{{text-align:center;padding:2.4rem 0 1rem}}
.hero h1{{font-size:clamp(2rem,6vw,3.4rem);margin:.4rem 0;text-wrap:balance}}
.hero p.sub{{color:var(--mut);font-size:1.05rem;max-width:44ch;margin:.4rem auto 1.2rem}}
.live{{display:inline-flex;align-items:center;gap:.5rem;font-weight:800;letter-spacing:.08em;
  color:#7be07b;background:rgba(70,200,90,.12);border:1px solid rgba(70,200,90,.4);
  padding:.35rem .85rem;border-radius:999px;font-size:.85rem}}
.live.off{{color:#e6c35c;background:rgba(230,195,92,.12);border-color:rgba(230,195,92,.4)}}
.live .dot{{width:.6rem;height:.6rem;border-radius:50%;background:currentColor;
  box-shadow:0 0 0 0 currentColor;animation:pulse 1.6s infinite}}
@keyframes pulse{{0%{{box-shadow:0 0 0 0 rgba(123,224,123,.6)}}70%{{box-shadow:0 0 0 .7rem rgba(123,224,123,0)}}100%{{box-shadow:0 0 0 0 rgba(123,224,123,0)}}}}
@media (prefers-reduced-motion:reduce){{.live .dot{{animation:none}}}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin:1.6rem 0}}
.tile{{border:1px solid var(--line);border-radius:14px;padding:1.2rem 1rem;text-align:center;
  background:linear-gradient(180deg,rgba(42,33,18,.6),rgba(16,12,7,.9))}}
.tile b{{display:block;font-family:Georgia,serif;color:var(--gold2);font-size:1.7rem;
  font-variant-numeric:tabular-nums;line-height:1.1}}
.tile span{{color:var(--mut);font-size:.76rem;text-transform:uppercase;letter-spacing:.05em}}
.cta{{text-align:center;margin:2rem 0 1rem}}
.cta a.btn{{display:inline-block;background:linear-gradient(180deg,#f7dd8f,#e6c35c);color:#2a1f08;
  font-weight:800;padding:.9rem 1.8rem;border-radius:12px;font-size:1.05rem;box-shadow:0 6px 22px rgba(230,195,92,.25)}}
.cta p{{color:var(--mut);font-size:.85rem;margin-top:.7rem}}
.feed{{list-style:none;margin:0;padding:.4rem .2rem}}
.feed li{{padding:.55rem .8rem;border-bottom:1px solid var(--line);font-size:.9rem}}
.feed li:last-child{{border-bottom:0}}.feed .ts{{color:var(--gold);margin-right:.6rem;font-variant-numeric:tabular-nums}}
</style></head>
<body><main>
<section class="hero">
  {live_badge}
  <h1>A real Evony bot, running right now.</h1>
  <p class="sub">Murder Bot plays a live alliance account 24/7 — joining every rally, claiming
  alliance gifts &amp; treasure, and mapping the game. Gem-safe: it never spends a gem.</p>
</section>
<div class="tiles">{tiles}</div>
{DEMO_COUNTER_WIDGET}
<div class="cta"><a class="btn" href="/">Start your free trial &rarr;</a>
<p>No credit card. Runs for your alliance while you sleep.</p></div>
<h2>Live activity</h2>
<div class="table-wrap"><ul class="feed">{feed}</ul></div>
<p class="muted" style="text-align:center;margin-top:1.4rem">Auto-refreshes every 60s &middot;
<a href="/">Murder Bot</a></p>
</main></body></html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the local-bot router wired to the host app's auth dependency."""
    router = APIRouter(tags=["mybot"])

    @router.get("/demo", response_class=HTMLResponse)
    def demo_page():
        """Public (no-auth), anonymized live proof-it-works page for user acquisition."""
        return HTMLResponse(render_demo(latest_report()))

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
