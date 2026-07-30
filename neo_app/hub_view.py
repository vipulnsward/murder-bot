"""hub_view.py — the manager HOME hub: one cohesive landing that links every page +
shows a live status strip. Self-contained FastAPI APIRouter (factory pattern, no app.py import).
"""
import os
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from alliance_view import SHARED_CSS

SECTIONS = (
    ("Intelligence", (
        ("/counter", "🧠", "AI counter engine", "Turn incoming attacks into quantified defense calls."),
        ("/intel", "🛰️", "Enemy intel", "Track enemy troops, buffs, generals, and battle history."),
        ("/alliance", "🛡️", "Alliance threat board", "Coordinate scouted threats and their strongest counters."),
        ("/brain", "📚", "Knowledge brain", "Explore tactics learned continuously from guides and reports."),
    )),
    ("Operations", (
        ("/map", "🗺️", "Vision-DB world map", "Survey explored screens and the latest captured intelligence."),
        ("/reports", "📜", "Battle reports", "Review every fight with detailed troop-tier results."),
        ("/attack", "⚔️", "Attack planner", "Rank targets where the projected trade is favorable."),
        ("/settings", "⚙️", "Accounts & settings", "Manage Evony accounts and encrypted integrations."),
    )),
    ("Account", (
        ("/billing", "💳", "Plans", "Compare access tiers and manage your subscription."),
        ("/generals-gallery", "🎖️", "General roster", "See owned and needed generals, portraits, and stats."),
    )),
)


def _stats(database):
    out = {"bot": "offline", "learn": "offline", "docs": "—", "enemies": "—", "tactics": "—"}
    try:
        pid = int(open("/tmp/video_report_loop.pid").read().strip()); os.kill(pid, 0); out["bot"] = "running"
    except Exception:
        pass
    try:
        pid = int(open("/tmp/knowledge_loop.pid").read().strip()); os.kill(pid, 0); out["learn"] = "running"
    except Exception:
        pass
    try:
        with database() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM knowledge"); out["docs"] = f"{cur.fetchone()[0]:,}"
            cur.execute("SELECT count(*) FROM enemies"); out["enemies"] = f"{cur.fetchone()[0]:,}"
    except Exception:
        pass
    try:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "game_brain", "knowledge_distilled.md")
        out["tactics"] = f"{sum(1 for ln in open(p) if ln.strip().startswith(('-', '*', '•'))):,}"
    except Exception:
        pass
    return out


def _onboarding(database, uid):
    """Per-user first-run checklist state: Evony account added? bot running? Discord connected?"""
    steps = []
    acct = False
    disc = False
    try:
        with database() as conn, conn.cursor() as cur:
            try:
                cur.execute("SELECT count(*) FROM evony_accounts WHERE user_id=%s", (uid,))
                acct = cur.fetchone()[0] > 0
            except Exception:
                pass
            try:
                cur.execute("SELECT count(*) FROM integrations WHERE user_id=%s AND kind='discord'", (uid,))
                disc = cur.fetchone()[0] > 0
            except Exception:
                pass
    except Exception:
        pass
    bot = False
    try:
        pid = int(open("/tmp/video_report_loop.pid").read().strip()); os.kill(pid, 0); bot = True
    except Exception:
        pass
    steps.append(("Add your Evony account", "Email/password, stored encrypted", "/settings", acct))
    steps.append(("Start the bot", "Joins rallies, tops stamina, scans reports 24/7", "/manager", bot))
    steps.append(("Connect Discord (optional)", "Feed the brain live alliance chatter", "/settings", disc))
    done = sum(1 for *_, ok in steps if ok)
    return steps, done, len(steps)


def _onboarding_html(steps, done, total):
    if done >= total:
        return ""  # fully set up — hide the checklist
    rows = "".join(
        f'<a class="ostep {"done" if ok else ""}" href="{href}">'
        f'<span class="obox">{"✓" if ok else ""}</span>'
        f'<span class="ot"><b>{t}</b><small>{d}</small></span>'
        f'<span class="oarr">{"" if ok else "→"}</span></a>'
        for t, d, href, ok in steps)
    return (f'<div class="onboard"><div class="oh">Get started · {done}/{total}</div>'
            f'<div class="obar"><i style="width:{done/total*100:.0f}%"></i></div>{rows}</div>')


def _page(s, onboard_html=""):
    def pill(label, val, on=None):
        cls = "on" if on else ("off" if on is False else "")
        return f'<div class="pill {cls}"><span class="pl">{label}</span><span class="pv">{val}</span></div>'
    sections = "".join(
        f'<section class="feature-section"><h2>{label}</h2><div class="grid">'
        + "".join(
            f'<a class="card" href="{href}"><div class="ic" aria-hidden="true">{ic}</div>'
            f'<div class="ct"><h3>{title}</h3><p>{desc}</p></div><div class="arr">→</div></a>'
            for href, ic, title, desc in pages
        )
        + "</div></section>"
        for label, pages in SECTIONS
    )
    strip = (pill("Game bot", s["bot"], s["bot"] == "running")
             + pill("Learning", s["learn"], s["learn"] == "running")
             + pill("Knowledge", s["docs"] + " docs")
             + pill("Tactics", s["tactics"])
             + pill("Enemies known", s["enemies"]))
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Easybot — command</title>
{SHARED_CSS}
<style>
 :root{{--grn:#57c08a}}
 main{{width:min(1100px,92vw);padding:2.25rem 0 4rem;line-height:1.5}}
 a{{text-decoration:none;color:inherit}}
 header{{flex-wrap:wrap;margin-bottom:.5rem}}
 .logo{{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.3rem;letter-spacing:-.02em}}
 .mk{{width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,var(--gold2),#8a5e12);display:grid;place-items:center;color:#150e02;font-weight:900;box-shadow:0 0 18px rgba(230,195,92,.32)}}
 .logout{{font-size:.85rem;color:var(--mut);border:1px solid var(--line);padding:8px 14px;border-radius:9px}}
 .logout:hover{{color:var(--gold2);border-color:var(--gold)}}
 .sub{{color:var(--mut);margin:2px 0 20px;font-size:.95rem}}
 .strip{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:26px}}
 .pill{{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:9px 13px;display:flex;flex-direction:column;gap:2px;min-width:120px}}
 .pill .pl{{font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}}
 .pill .pv{{font-weight:700;font-variant-numeric:tabular-nums}}
 .pill.on{{border-left:3px solid var(--grn)}}.pill.on .pv{{color:var(--grn)}}
 .pill.off{{border-left:3px solid var(--red)}}.pill.off .pv{{color:#ff7d5c}}
 .feature-section{{margin-top:2rem}}
 .feature-section h2{{margin-bottom:.75rem;font-size:1rem;text-transform:uppercase;letter-spacing:.12em}}
 .grid{{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
 .card{{display:flex;align-items:center;gap:15px;padding:18px 20px;transition:transform .15s ease,border-color .15s ease}}
 .card:hover{{border-color:var(--gold);transform:translateY(-2px)}}
 .card .ic{{font-size:26px;width:44px;height:44px;display:grid;place-items:center;background:rgba(230,195,92,.1);border:1px solid rgba(230,195,92,.16);border-radius:11px;flex:0 0 auto}}
 .card h3{{margin:0 0 3px;font-size:1.05rem;letter-spacing:-.01em}}.card p{{margin:0;color:var(--mut);font-size:.86rem}}
 .card .arr{{margin-left:auto;color:var(--gold);font-size:1.1rem}}
 .onboard{{background:var(--card);border:1px solid var(--gold);border-radius:14px;padding:16px 18px;margin-bottom:22px}}
 .onboard .oh{{font-weight:700;margin-bottom:9px;color:var(--gold)}}
 .obar{{height:6px;background:rgba(255,255,255,.08);border-radius:6px;overflow:hidden;margin-bottom:12px}}
 .obar i{{display:block;height:100%;background:linear-gradient(90deg,var(--gold),#8a5e12)}}
 .ostep{{display:flex;align-items:center;gap:12px;padding:9px 4px;border-top:1px solid var(--line)}}
 .ostep .obox{{width:22px;height:22px;border-radius:6px;border:1px solid var(--line);display:grid;place-items:center;color:var(--grn);font-weight:800;flex:0 0 auto}}
 .ostep.done .obox{{background:rgba(87,192,138,.14);border-color:var(--grn)}}
 .ostep .ot{{display:flex;flex-direction:column}}.ostep .ot small{{color:var(--mut);font-size:.8rem}}
 .ostep.done .ot b{{color:var(--mut);text-decoration:line-through}}
 .ostep .oarr{{margin-left:auto;color:var(--gold)}}
 @media(max-width:640px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
 <header><div class=logo><span class=mk>E</span> Easybot</div><a class=logout href="#" onclick="fetch('/api/logout',{{method:'POST'}}).then(()=>location.href='/')">Log out</a></header>
 <div class=sub>Your Evony command center — the PvP brain that never sleeps.</div>
 <div class=strip>{strip}</div>
 {onboard_html}
 {sections}
</main></body></html>"""


def build_router(current_user, database):
    router = APIRouter(tags=["hub"])

    @router.get("/home", response_class=HTMLResponse)
    def home(_uid: int = Depends(current_user)):
        steps, done, total = _onboarding(database, _uid)
        return HTMLResponse(_page(_stats(database), _onboarding_html(steps, done, total)))

    return router
