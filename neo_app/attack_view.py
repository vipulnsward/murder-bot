"""Attack Planner view — the ATTACK pillar of the Murder Bot manager.

Self-contained FastAPI APIRouter built with the ``build_router(current_user,
database)`` factory (same pattern as ``generals_view.py`` / ``counter_view.py``).
It does NOT import ``app.py`` — the host app injects its own auth dependency and
``database`` context manager.

What it does
------------
* Imports ``attack_planner`` from the repo root (``<repo>/attack_planner.py``;
  its parent directory is added to ``sys.path`` before import, exactly like
  ``counter_view`` does for ``counter_ai``). Set ``ATTACK_PLANNER_ROOT`` to
  override where it is imported from.
* Calls ``attack_planner.pick_targets()`` to get a RANKED list of favorable
  attack targets scored from the Postgres ``enemies`` table via ``counter_ai``.
* Renders each target as a card: name / alliance, trade score, GO/NO-GO verdict,
  recommended vector (solo / rally / skip), lead type, expected loss %, and the
  counter_ai reasoning.

Safety
------
This page is ADVISORY ONLY. It never imports or calls ``execute_attack`` — there
is no launch endpoint here at all. Real launches live in ``attack_planner`` and
are gated on ``bot_config.json advanced.auto_attack == true`` AND ``dry_run=False``,
neither of which this page can trigger. The live value of ``auto_attack`` is
surfaced honestly on the page, but "nothing is launched" holds unconditionally.

If ``attack_planner`` / ``counter_ai`` cannot be imported, or the ``enemies``
table is empty or unreadable, the page degrades to a clear empty / error state
rather than fabricating targets.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

# The exact mandated safety line. It is TRUE unconditionally for this page:
# there is no execute endpoint here, so nothing is ever launched regardless of
# the live config value (which is additionally surfaced for honesty).
SAFETY_BANNER = (
    "Attack execution is OFF by default (config advanced.auto_attack=false); "
    "this page is advisory only — nothing is launched."
)

# counter_ai scenario modes accepted by attack_planner.pick_targets(mode=...).
MODES = {
    "open_map": "Open map",
    "battlefield": "Battlefield",
    "coc": "Clash of Civilizations",
    "boc": "Battle of Constantinople",
    "bog": "Battle of Gods",
    "svs": "Server vs Server",
}

TYPE_META = {
    "ground": {"label": "Ground", "glyph": "🛡️", "color": "#3fb950"},
    "ranged": {"label": "Ranged", "glyph": "🏹", "color": "#58a6ff"},
    "mounted": {"label": "Mounted", "glyph": "🐎", "color": "#ff7b72"},
    "siege": {"label": "Siege", "glyph": "🏰", "color": "#a371f7"},
    "unknown": {"label": "Scout first", "glyph": "❔", "color": "#8b949e"},
}

# Recommended-vector presentation (solo / rally / skip family).
VECTOR_META = {
    "coordinated_rally": {"label": "🤝 Rally (coordinated)", "cls": "vec-rally"},
    "scout_then_rally": {"label": "🔭 Scout → Rally", "cls": "vec-scout"},
    "rally": {"label": "🤝 Rally", "cls": "vec-rally"},
    "solo": {"label": "🗡️ Solo march", "cls": "vec-solo"},
    "skip": {"label": "⛔ Skip (solo = feeding)", "cls": "vec-skip"},
    "none": {"label": "✋ Hold — make them come to you", "cls": "vec-skip"},
}


# --- attack_planner integration -------------------------------------------


def load_attack_planner():
    """Return (module, error). ``error`` is a string when the module (or its
    ``counter_ai`` dependency) cannot be imported."""
    roots = [os.environ.get("ATTACK_PLANNER_ROOT"), str(REPO_ROOT)]
    for root in roots:
        if root and root not in sys.path:
            sys.path.insert(0, root)
    try:
        import attack_planner  # type: ignore

        return attack_planner, None
    except Exception as error:  # ImportError or anything raised at import time
        return None, f"{type(error).__name__}: {error}"


def _sim_available(module) -> bool | None:
    """Whether the JS combat simulator is wired up (affects whether forecasts
    are measured or analytic). None when it cannot be determined."""
    try:
        return module.counter_ai._sim_js_dir() is not None
    except Exception:
        return None


def _auto_attack(module) -> bool:
    try:
        return bool(module.auto_attack_enabled())
    except Exception:
        return False


def gather_plans(mode: str = "open_map") -> dict:
    """Produce the ranked-target payload with graceful degradation.

    Returns a dict: targets, counts, auto_attack, sim_available, mode, engine,
    error (import/DB failure string or None), empty (bool).
    """
    if mode not in MODES:
        mode = "open_map"

    module, import_error = load_attack_planner()
    base = {
        "mode": mode,
        "auto_attack": False,
        "sim_available": None,
        "targets": [],
        "counts": {"total": 0, "attackable": 0, "go": 0, "scout": 0, "nogo": 0},
        "engine": "",
        "error": None,
        "empty": True,
    }
    if module is None:
        base["error"] = (
            f"attack_planner / counter_ai could not be imported ({import_error}). "
            "The attack engine is unavailable; no targets can be ranked."
        )
        base["engine"] = "attack_planner unavailable"
        return base

    base["auto_attack"] = _auto_attack(module)
    base["sim_available"] = _sim_available(module)
    base["engine"] = (
        "attack_planner + counter_ai — "
        + (
            "combat simulator AVAILABLE (measured forecasts)"
            if base["sim_available"]
            else "analytic fallback (no simulator)"
            if base["sim_available"] is False
            else "engine loaded"
        )
    )

    try:
        targets = module.pick_targets(mode=mode)
    except Exception as error:
        # RuntimeError from load_enemies (psycopg2/DB down) lands here — surface
        # it verbatim rather than inventing targets.
        base["error"] = (
            f"Could not read the enemies table ({type(error).__name__}: {error})."
        )
        return base

    if not isinstance(targets, list):
        targets = []

    counts = {
        "total": len(targets),
        "attackable": sum(1 for t in targets if t.get("attackable")),
        "go": sum(1 for t in targets if str(t.get("go_no_go") or "").startswith("GO")),
        "scout": sum(1 for t in targets if str(t.get("go_no_go") or "").startswith("SCOUT")),
        "nogo": sum(1 for t in targets if str(t.get("go_no_go") or "").startswith("NO-GO")),
    }
    base.update({"targets": targets, "counts": counts, "empty": len(targets) == 0})
    return base


# --- formatting helpers ----------------------------------------------------


def _fmt_int(value) -> str:
    """Full comma-separated integer (never abbreviated)."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.0f}%"
    except (TypeError, ValueError):
        return html.escape(str(value))


def _fmt_conf(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    # counter_ai confidence is a 0..1 scalar; show as a percentage.
    return f"{number * 100:.0f}%" if 0 <= number <= 1 else f"{number:.2f}"


def _verdict_class(go_no_go: str) -> str:
    text = str(go_no_go or "")
    if text.startswith("GO"):
        return "go"
    if text.startswith("SCOUT"):
        return "scout"
    if text.startswith("NO-GO"):
        return "nogo"
    return "unknown"


def _type_pill(lead_type) -> str:
    kind = str(lead_type or "").strip().lower() or "unknown"
    meta = TYPE_META.get(kind, TYPE_META["unknown"])
    return (
        f'<span class="pill" style="--pc:{meta["color"]}">'
        f'{meta["glyph"]} {html.escape(meta["label"])}</span>'
    )


def _vector_pill(vector) -> str:
    meta = VECTOR_META.get(str(vector or "none"), VECTOR_META["none"])
    return f'<span class="vec {meta["cls"]}">{html.escape(meta["label"])}</span>'


def _forecast_line(forecast) -> str:
    if not isinstance(forecast, dict) or not forecast:
        return '<p class="forecast muted">No scout numbers → scout-gated (no forecast).</p>'
    winner = html.escape(str(forecast.get("winner") or "?"))
    method = html.escape(str(forecast.get("method") or "rule"))
    my_loss = forecast.get("attacker_loss_pct")
    their_loss = forecast.get("defender_loss_pct")
    rounds = forecast.get("rounds")
    rounds_str = f" · {int(rounds)} rounds" if isinstance(rounds, (int, float)) else ""
    winner_cls = "win" if winner.upper() == "ATTACKER" else "loss"
    return (
        f'<p class="forecast">Forecast (<span class="method">{method}</span>): '
        f'winner <b class="{winner_cls}">{winner}</b> · '
        f'my losses <b>{_fmt_pct(my_loss)}</b> · their losses <b>{_fmt_pct(their_loss)}</b>'
        f"{rounds_str}</p>"
    )


def _target_card(index: int, target: dict) -> str:
    name = html.escape(str(target.get("name") or "Unknown"))
    alliance = target.get("alliance")
    alliance_html = f'<span class="alliance">[{html.escape(str(alliance))}]</span>' if alliance else ""
    verdict = str(target.get("go_no_go") or "—")
    verdict_cls = _verdict_class(verdict)
    score = target.get("trade_score")
    try:
        score_str = f"{float(score):+.1f}"
    except (TypeError, ValueError):
        score_str = "—"

    outcome = target.get("expected_outcome") or {}
    lead = outcome.get("lead_type") or outcome.get("counter_lead")
    action = html.escape(str(outcome.get("action") or "—")).upper()
    sim_flag = (
        '<span class="engine-flag sim">simulator</span>'
        if outcome.get("sim_used")
        else '<span class="engine-flag rules">analytic</span>'
    )
    reasoning = html.escape(str(outcome.get("reasoning") or ""))

    max_troops = target.get("max_troops")
    troops_str = _fmt_int(max_troops) if max_troops else "unscouted"
    coords = target.get("coords")
    coords_str = html.escape(str(coords)) if coords else "—"
    record = html.escape(str(target.get("record") or "0-0"))
    threat = target.get("threat")
    threat_str = html.escape(str(threat)) if threat else "—"

    reasons = target.get("reasons") or []
    reasons_html = ""
    if isinstance(reasons, (list, tuple)) and reasons:
        items = "".join(f"<li>{html.escape(str(r))}</li>" for r in reasons)
        reasons_html = f'<ul class="reasons">{items}</ul>'

    reasoning_html = f'<p class="reasoning">{reasoning}</p>' if reasoning else ""

    return f"""
<article class="tcard {verdict_cls}">
  <header class="thead">
    <div class="tname">
      <span class="rank">#{index}</span>
      <h2>{name}</h2>
      {alliance_html}
    </div>
    <div class="tflags">
      <span class="score" title="Favorable-trade score">score {score_str}</span>
      <span class="verdict {verdict_cls}">{html.escape(verdict)}</span>
    </div>
  </header>
  <div class="tmetrics">
    <div class="metric"><span>Vector</span>{_vector_pill(target.get("vector"))}</div>
    <div class="metric"><span>Lead type</span>{_type_pill(lead)}</div>
    <div class="metric"><span>Expected loss</span><b>{_fmt_pct(outcome.get("expected_loss_pct"))}</b></div>
    <div class="metric"><span>Confidence</span><b>{_fmt_conf(outcome.get("confidence"))}</b></div>
  </div>
  <div class="tfacts">
    <span>counter_ai call: <b>{action}</b> {sim_flag}</span>
    <span>Head-to-head: <b>{record}</b></span>
    <span>Threat: <b>{threat_str}</b></span>
    <span>Defending troops: <b>{troops_str}</b></span>
    <span>Coords: <b>{coords_str}</b></span>
  </div>
  {reasoning_html}
  {_forecast_line(outcome.get("forecast"))}
  {reasons_html}
</article>"""


def _mode_selector(mode: str) -> str:
    options = "".join(
        f'<option value="{key}"{" selected" if key == mode else ""}>{html.escape(label)}</option>'
        for key, label in MODES.items()
    )
    return f"""
<form class="mode-form" method="get" action="/attack">
  <label>Scenario
    <select name="mode" onchange="this.form.submit()">{options}</select>
  </label>
  <noscript><button type="submit">Apply</button></noscript>
</form>"""


def render_page(payload: dict) -> str:
    mode = payload.get("mode", "open_map")
    counts = payload.get("counts") or {}
    auto_attack = bool(payload.get("auto_attack"))
    sim_available = payload.get("sim_available")
    engine = html.escape(str(payload.get("engine") or ""))
    error = payload.get("error")
    targets = payload.get("targets") or []

    # Live config chip — honest reflection of the actual gate value.
    if auto_attack:
        config_chip = (
            '<span class="cfg cfg-on">⚠ live config: advanced.auto_attack = true</span>'
        )
    else:
        config_chip = (
            '<span class="cfg cfg-off">live config: advanced.auto_attack = false</span>'
        )

    sim_note = (
        "Forecasts are measured by the combat simulator."
        if sim_available
        else "Forecasts use the analytic fallback (no simulator)."
        if sim_available is False
        else ""
    )

    banner = f"""
<div class="safety" role="alert">
  <span class="safety-icon">🛡️</span>
  <div>
    <b>{html.escape(SAFETY_BANNER)}</b>
    <div class="safety-sub">
      This view has no launch endpoint — it only ranks and explains targets.
      {config_chip}
    </div>
  </div>
</div>"""

    if error:
        body = (
            f'<div class="warn"><b>Attack engine degraded:</b> {html.escape(str(error))}</div>'
            '<div class="empty"><h2>No targets to show</h2>'
            "<p>Scout enemies into the <code>enemies</code> table (name, alliance, "
            "max_troops, buffs, coords) and the planner will rank favorable trades here.</p></div>"
        )
    elif not targets:
        body = (
            '<div class="empty"><h2>No enemies scouted yet</h2>'
            "<p>The <code>enemies</code> table is empty. Scout targets (Watchtower + open-map "
            "recon) so counter_ai can model favorable rallies. Nothing to attack until then — "
            "and nothing is launched from here regardless.</p></div>"
        )
    else:
        summary = f"""
<div class="summary">
  <span class="stat"><b>{counts.get('total', 0)}</b> targets ranked</span>
  <span class="stat go"><b>{counts.get('go', 0)}</b> GO (rally)</span>
  <span class="stat scout"><b>{counts.get('scout', 0)}</b> scout-first</span>
  <span class="stat nogo"><b>{counts.get('nogo', 0)}</b> no-go</span>
</div>"""
        cards = "".join(_target_card(i, t) for i, t in enumerate(targets, 1))
        body = summary + f'<div class="cards">{cards}</div>'

    engine_line = f'<div class="engine-line">{engine}. {html.escape(sim_note)}</div>' if engine else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Attack Planner — Murder Bot</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }}
main {{ width: min(1040px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }}
a {{ color: #58a6ff; text-decoration: none; }}
h1, h2 {{ margin: 0; }}
header.top {{ display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }}
.sub {{ color: #8b949e; font-size: .9rem; margin-top: .3rem; }}
.safety {{ display: flex; gap: .8rem; align-items: flex-start; margin: 1.3rem 0; padding: 1rem 1.15rem; background: #3d1518; border: 1px solid #b62324; border-left: 5px solid #f85149; border-radius: 12px; color: #ffd7d3; }}
.safety-icon {{ font-size: 1.5rem; line-height: 1; }}
.safety b {{ color: #ffb4ad; font-size: 1.02rem; line-height: 1.45; }}
.safety-sub {{ margin-top: .5rem; color: #d7a9a6; font-size: .84rem; line-height: 1.5; }}
.cfg {{ display: inline-block; margin-left: .3rem; padding: .12rem .55rem; border-radius: 999px; font-size: .74rem; font-weight: 700; font-family: ui-monospace, SFMono-Regular, monospace; }}
.cfg-off {{ color: #3fb950; background: #12331d; border: 1px solid #238636; }}
.cfg-on {{ color: #f0b429; background: #3d2f0b; border: 1px solid #9e6a03; }}
.engine-line {{ color: #6e7681; font-size: .8rem; margin: .2rem 0 .6rem; font-family: ui-monospace, SFMono-Regular, monospace; }}
.mode-form {{ margin: .4rem 0 1rem; }}
.mode-form label {{ display: inline-flex; align-items: center; gap: .5rem; color: #8b949e; font-size: .82rem; }}
.mode-form select {{ padding: .45rem .6rem; background: #161b22; color: #e6edf3; border: 1px solid #30363d; border-radius: 8px; font-size: .9rem; }}
.mode-form button {{ margin-left: .5rem; padding: .45rem .9rem; background: #1f6feb; color: #fff; border: 0; border-radius: 8px; font-weight: 700; cursor: pointer; }}
.warn {{ margin: 1rem 0; padding: .8rem 1rem; color: #d29922; background: #3d2f0b; border: 1px solid #9e6a03; border-radius: 8px; font-size: .88rem; }}
.empty {{ margin: 2rem 0; padding: 2rem 1.5rem; text-align: center; background: #161b22; border: 1px dashed #30363d; border-radius: 14px; color: #8b949e; }}
.empty h2 {{ color: #adbac7; margin-bottom: .5rem; }}
.empty code {{ color: #79c0ff; }}
.summary {{ display: flex; flex-wrap: wrap; gap: .55rem; margin: 1rem 0 1.4rem; }}
.stat {{ padding: .45rem .85rem; background: #161b22; border: 1px solid #30363d; border-radius: 999px; font-size: .86rem; color: #adbac7; }}
.stat b {{ color: #fff; }}
.stat.go {{ border-color: #238636; }} .stat.go b {{ color: #3fb950; }}
.stat.scout {{ border-color: #1f6feb; }} .stat.scout b {{ color: #58a6ff; }}
.stat.nogo {{ border-color: #b62324; }} .stat.nogo b {{ color: #ff7b72; }}
.cards {{ display: grid; gap: 1rem; }}
.tcard {{ padding: 1.15rem 1.25rem; background: #161b22; border: 1px solid #30363d; border-left: 4px solid #6e7681; border-radius: 14px; }}
.tcard.go {{ border-left-color: #3fb950; }}
.tcard.scout {{ border-left-color: #58a6ff; }}
.tcard.nogo {{ border-left-color: #f85149; }}
.thead {{ display: flex; align-items: flex-start; justify-content: space-between; gap: .8rem; flex-wrap: wrap; }}
.tname {{ display: flex; align-items: baseline; gap: .5rem; flex-wrap: wrap; }}
.rank {{ color: #6e7681; font-weight: 800; font-size: .95rem; }}
.thead h2 {{ font-size: 1.2rem; }}
.alliance {{ color: #8b949e; font-size: .9rem; font-weight: 600; }}
.tflags {{ display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }}
.score {{ padding: .2rem .6rem; border-radius: 999px; font-size: .78rem; font-weight: 700; color: #d2a8ff; background: #1c1633; border: 1px solid #3a2d63; font-variant-numeric: tabular-nums; }}
.verdict {{ padding: .22rem .65rem; border-radius: 999px; font-size: .76rem; font-weight: 800; letter-spacing: .02em; }}
.verdict.go {{ color: #3fb950; background: #12331d; border: 1px solid #238636; }}
.verdict.scout {{ color: #58a6ff; background: #0d2f4d; border: 1px solid #1f6feb; }}
.verdict.nogo {{ color: #ff7b72; background: #3d1518; border: 1px solid #b62324; }}
.verdict.unknown {{ color: #adbac7; background: #21262d; border: 1px solid #30363d; }}
.tmetrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .6rem; margin: 1rem 0 .8rem; }}
.metric {{ background: #0d1117; border: 1px solid #21262d; border-radius: 9px; padding: .55rem .65rem; display: flex; flex-direction: column; gap: .35rem; }}
.metric span {{ color: #8b949e; font-size: .68rem; text-transform: uppercase; letter-spacing: .05em; }}
.metric b {{ font-size: 1.02rem; font-variant-numeric: tabular-nums; }}
.pill {{ display: inline-block; padding: .1rem .45rem; font-size: .78rem; font-weight: 700; color: var(--pc); border: 1px solid var(--pc); border-radius: 999px; white-space: nowrap; }}
.vec {{ display: inline-block; padding: .1rem .5rem; font-size: .78rem; font-weight: 700; border-radius: 999px; white-space: nowrap; }}
.vec-rally {{ color: #3fb950; background: #12331d; border: 1px solid #238636; }}
.vec-scout {{ color: #58a6ff; background: #0d2f4d; border: 1px solid #1f6feb; }}
.vec-solo {{ color: #f0b429; background: #3d2f0b; border: 1px solid #9e6a03; }}
.vec-skip {{ color: #ff7b72; background: #3d1518; border: 1px solid #b62324; }}
.tfacts {{ display: flex; flex-wrap: wrap; gap: .35rem 1.1rem; margin: .3rem 0 .7rem; color: #8b949e; font-size: .82rem; }}
.tfacts b {{ color: #c9d1d9; font-variant-numeric: tabular-nums; }}
.engine-flag {{ margin-left: .25rem; padding: .04rem .4rem; border-radius: 6px; font-size: .68rem; font-weight: 700; }}
.engine-flag.sim {{ color: #3fb950; background: #12331d; }}
.engine-flag.rules {{ color: #d29922; background: #3d2f0b; }}
.reasoning {{ margin: .6rem 0 0; padding: .6rem .75rem; color: #d2a8ff; background: #1c1633; border: 1px solid #3a2d63; border-radius: 9px; font-size: .9rem; line-height: 1.5; }}
.forecast {{ margin: .55rem 0 0; color: #c9d1d9; font-size: .84rem; }}
.forecast .method {{ color: #8b949e; }}
.forecast .win {{ color: #3fb950; }} .forecast .loss {{ color: #ff7b72; }}
.reasons {{ margin: .55rem 0 0; padding-left: 1.15rem; color: #adbac7; font-size: .84rem; line-height: 1.5; }}
.reasons li {{ margin: .2rem 0; }}
.muted {{ color: #6e7681; }}
@media (max-width: 640px) {{
  main {{ padding: 1.25rem 0 3rem; }}
  .tmetrics {{ grid-template-columns: repeat(2, 1fr); }}
  .thead h2 {{ font-size: 1.05rem; }}
}}
</style>
</head>
<body>
<main>
<header class="top">
  <div>
    <h1>Attack Planner</h1>
    <div class="sub">Murder Bot — favorable-trade target ranking (advisory, read-only)</div>
  </div>
  <a href="/">&larr; Dashboard</a>
</header>
{banner}
{engine_line}
{_mode_selector(mode)}
{body}
</main>
</body>
</html>"""


# --- router factory --------------------------------------------------------


def build_router(current_user, database) -> APIRouter:
    """Return the Attack Planner router wired to the host app's auth + DB.

    Parameters
    ----------
    current_user:
        The host app's FastAPI auth dependency (``request -> user_id``).
    database:
        The host app's ``@contextmanager`` yielding a psycopg2 connection.
        (Accepted for factory-signature parity; ``attack_planner`` opens its own
        connection to the ``enemies`` table via ``MURDERBOT_DSN``.)
    """
    router = APIRouter(tags=["attack"])

    @router.get("/attack", response_class=HTMLResponse)
    def attack_page(
        _user_id: int = Depends(current_user),
        mode: str = Query(default="open_map", description="counter_ai scenario mode"),
    ):
        return HTMLResponse(render_page(gather_plans(mode=mode)))

    @router.get("/api/attack")
    def attack_api(
        _user_id: int = Depends(current_user),
        mode: str = Query(default="open_map", description="counter_ai scenario mode"),
    ):
        payload = gather_plans(mode=mode)
        return JSONResponse(
            {
                "mode": payload["mode"],
                "safety": SAFETY_BANNER,
                "execution": "disabled — advisory only; no launch endpoint is exposed",
                "auto_attack": payload["auto_attack"],
                "auto_attack_gated": True,
                "sim_available": payload["sim_available"],
                "engine": payload["engine"],
                "counts": payload["counts"],
                "targets": payload["targets"],
                "error": payload["error"],
            }
        )

    return router
