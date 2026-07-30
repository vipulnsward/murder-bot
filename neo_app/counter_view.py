"""Strategic Counter view — the Murder Bot's live PvP counter call.

Self-contained FastAPI APIRouter built with the ``build_router(current_user,
database)`` factory (same pattern as ``generals_view.py``). It does NOT import
``app.py`` — the host app injects its own auth dependency and ``database``
context manager.

What it does
------------
* Pulls the current known state from Postgres ``murderbot``: our troop roster
  (``troops``), our latest recorded battle buffs (``battle_buffs``) and the most
  recent opponents (``report_extracts``).
* Feeds that state to ``counter_ai.decide(...)`` (imported from the repo root)
  to produce the recommended action, lead type, reasoning, confidence and
  expected loss.
* If ``counter_ai`` is unavailable (not yet built, import error, or an
  incompatible ``decide`` signature), it degrades gracefully to a built-in
  heuristic grounded in the pvp_brain counter triangle. The engine that
  produced each call is always reported honestly via a ``source`` field, so a
  fallback call is never presented as the real AI call.

The ``counter_ai`` module is expected at the repo root
(``<repo>/counter_ai.py``); its parent directory is added to ``sys.path``
before import. Set ``COUNTER_AI_ROOT`` to override where it is imported from.
"""

from __future__ import annotations

import html
import inspect
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

# --- Combat model (pvp_brain §1, §12) -------------------------------------

TROOP_TYPES = ("ground", "ranged", "mounted", "siege")

# Map the Postgres troops.building column onto a field type.
BUILDING_TYPE = {
    "barracks": "ground",
    "archer_camp": "ranged",
    "stable": "mounted",
    "workshop": "siege",
}

TYPE_META = {
    "ground": {"label": "Ground", "glyph": "🛡️", "color": "#3fb950"},
    "ranged": {"label": "Ranged", "glyph": "🏹", "color": "#58a6ff"},
    "mounted": {"label": "Mounted", "glyph": "🐎", "color": "#ff7b72"},
    "siege": {"label": "Siege", "glyph": "🏰", "color": "#a371f7"},
    "unknown": {"label": "Unknown", "glyph": "❔", "color": "#8b949e"},
}

# "They lead -> lead your defense with" (pvp_brain §9 / §12 counter table).
COUNTER_TABLE = {
    "ground": {
        "lead": "mounted",
        "mult": 1.2,
        "note": "Mounted counters Ground (1.2x).",
        "mayor": "Narses (enemy ground -50/40)",
        "beast": "Duneyrr (enemy ground HP) / Hati (enemy mounted atk)",
    },
    "ranged": {
        "lead": "ground",
        "mult": 1.2,
        "note": "Ground counters Ranged (1.2x) and hunts Ranged first.",
        "mayor": "Gilgamesh (enemy ranged/siege def -40)",
        "beast": "Rainbow Crow (enemy ground atk)",
    },
    "mounted": {
        "lead": "ranged",
        "mult": 1.2,
        "note": "Ranged counters Mounted (1.2x).",
        "mayor": "Hojo Ujiyasu",
        "beast": "Otso (enemy mounted HP)",
    },
    "siege": {
        "lead": "ground",
        "mult": 1.1,
        "note": "Ground meat-shield + your own siege; needs a +15% siege-range ring.",
        "mayor": "Cimon (enemy ranged & siege -40 across atk/def/hp)",
        "beast": "Tarasque (enemy siege atk)",
    },
}

# Damage multiplier matrix (attacker row -> target col), pvp_brain §1.
MULT = {
    "ground": {"ground": 1.0, "ranged": 1.2, "mounted": 0.7, "siege": 1.1},
    "ranged": {"ground": 0.8, "ranged": 1.0, "mounted": 1.2, "siege": 1.1},
    "mounted": {"ground": 1.2, "ranged": 0.8, "mounted": 1.0, "siege": 0.9},
    "siege": {"ground": 0.35, "ranged": 0.4, "mounted": 0.3, "siege": 0.5},
}

LEAD_SYNONYMS = {
    "ground": "ground", "infantry": "ground", "inf": "ground", "melee": "ground",
    "ranged": "ranged", "archer": "ranged", "archers": "ranged", "bow": "ranged",
    "mounted": "mounted", "cavalry": "mounted", "cav": "mounted", "horse": "mounted",
    "siege": "siege", "catapult": "siege", "artillery": "siege", "machine": "siege",
}

OUR_TAG = "NFG"
OUR_NAME_HINT = "tlatoani"


def normalize_type(value) -> str | None:
    if not value:
        return None
    return LEAD_SYNONYMS.get(str(value).strip().lower())


def _is_us(name) -> bool:
    if not name:
        return False
    lowered = str(name).lower()
    return OUR_TAG.lower() in lowered or OUR_NAME_HINT in lowered


def _fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_ts(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(value)


# --- counter_ai integration ------------------------------------------------


def load_counter_ai():
    """Return (module, error). error is a string when the module is unavailable."""
    roots = [os.environ.get("COUNTER_AI_ROOT"), str(REPO_ROOT)]
    for root in roots:
        if root and root not in sys.path:
            sys.path.insert(0, root)
    try:
        import counter_ai  # type: ignore

        return counter_ai, None
    except Exception as error:  # ImportError or anything raised at import time
        return None, f"{type(error).__name__}: {error}"


def _as_mapping(obj) -> dict:
    if isinstance(obj, dict):
        return dict(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if hasattr(obj, "_asdict"):  # namedtuple
        try:
            return dict(obj._asdict())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {"value": obj}


def _pick(mapping: dict, *names):
    for name in names:
        if name in mapping and mapping[name] not in (None, "", []):
            return mapping[name]
    return None


def normalize_plan(result, source: str) -> dict:
    mapping = _as_mapping(result)
    reasoning = _pick(
        mapping, "reasoning", "reason", "rationale", "why", "explanation", "notes", "note"
    )
    if reasoning is None:
        reasons = _pick(mapping, "reasons")
        if isinstance(reasons, (list, tuple)):
            reasoning = "; ".join(str(item) for item in reasons)
    lead = _pick(
        mapping, "lead_type", "lead", "lead_with", "counter_type", "recommended_lead", "type"
    )
    confidence = _pick(mapping, "confidence", "confidence_pct", "conf", "certainty")
    expected_loss = _pick(
        mapping, "expected_loss", "expected_losses", "loss", "losses", "expected_loss_pct"
    )
    action = _pick(
        mapping, "action", "recommended_action", "recommendation", "recommend", "plan", "move"
    )
    return {
        "action": action if action is not None else "See reasoning",
        "lead_type": normalize_type(lead) or (str(lead).lower() if lead else None),
        "reasoning": reasoning or "",
        "confidence": confidence,
        "expected_loss": expected_loss,
        "source": source,
        "raw": {k: v for k, v in mapping.items() if k != "raw"},
    }


def invoke_decide(module, state: dict):
    """Call counter_ai.decide adapting to whatever signature it exposes.

    Returns (plan, error). Tries, in order: filtered keyword args (when every
    required parameter can be satisfied from ``state``), then the whole state
    as a single positional argument.
    """
    decide = getattr(module, "decide", None)
    if not callable(decide):
        return None, "counter_ai has no callable decide()"

    attempts: list[tuple[str, object]] = []
    try:
        signature = inspect.signature(decide)
    except (TypeError, ValueError):
        signature = None

    if signature is not None:
        params = signature.parameters
        has_var_keyword = any(p.kind == p.VAR_KEYWORD for p in params.values())
        if has_var_keyword:
            attempts.append(("kwargs", dict(state)))
        else:
            kwargs = {name: state[name] for name in params if name in state}
            required = [
                name
                for name, param in params.items()
                if param.default is inspect.Parameter.empty
                and param.kind
                in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
            ]
            if all(name in kwargs for name in required):
                attempts.append(("kwargs", kwargs))
    attempts.append(("positional", dict(state)))

    last_error = None
    for mode, payload in attempts:
        try:
            result = decide(**payload) if mode == "kwargs" else decide(payload)
            return normalize_plan(result, "counter_ai.decide()"), None
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
    return None, last_error


# --- Built-in fallback (heuristic, clearly labelled) -----------------------


def fallback_decide(state: dict) -> dict:
    opp_lead = normalize_type(state.get("opponent_lead"))
    opp_troops = state.get("opponent_troops")
    my_troops = state.get("my_troops") or {}
    my_total = sum(int(v) for v in my_troops.values() if isinstance(v, (int, float)))

    if opp_lead is None:
        return {
            "action": "Scout first (Watchtower) — enemy lead type unknown",
            "lead_type": None,
            "reasoning": (
                "No enemy lead type is known for the current state. Scout with the "
                "Watchtower (L21 reveals types) before committing, then lead with the "
                "type that beats their lead per the counter triangle."
            ),
            "confidence": "low",
            "expected_loss": None,
            "source": "built-in fallback (counter_ai unavailable)",
            "raw": {},
        }

    row = COUNTER_TABLE[opp_lead]
    lead = row["lead"]
    have = int(my_troops.get(lead, 0) or 0)
    advantage = MULT.get(lead, {}).get(opp_lead, 1.0)

    # Rough loss estimate: favourable matchup + adequate mass => low losses.
    base_loss = 0.18 if advantage >= 1.2 else (0.30 if advantage >= 1.0 else 0.55)
    if isinstance(opp_troops, (int, float)) and opp_troops > 0 and my_total > 0:
        ratio = my_total / float(opp_troops)
        if ratio < 0.75:
            base_loss = min(0.9, base_loss + 0.25)
        elif ratio > 1.5:
            base_loss = max(0.05, base_loss - 0.08)
    expected_loss = f"~{round(base_loss * 100)}%"

    if have <= 0:
        confidence = "low"
        confidence_note = (
            f"You hold no {TYPE_META[lead]['label']} troops on record — acquire/train "
            "the counter type or reinforce from an ally."
        )
    elif isinstance(opp_troops, (int, float)) and opp_troops > 0 and have < opp_troops * 0.5:
        confidence = "medium"
        confidence_note = (
            f"You hold {_fmt_int(have)} {TYPE_META[lead]['label']} vs an estimated "
            f"{_fmt_int(opp_troops)} enemy — mass may be short; stack all tiers."
        )
    else:
        confidence = "high"
        confidence_note = f"You hold {_fmt_int(have)} {TYPE_META[lead]['label']} to lead with."

    action = (
        f"Lead with {TYPE_META[lead]['label']} vs their {TYPE_META[opp_lead]['label']}; "
        f"run debuff mayor {row['mayor']}"
    )
    reasoning = (
        f"They lead {TYPE_META[opp_lead]['label']}. {row['note']} "
        f"{confidence_note} Debuff mayor: {row['mayor']}. Defending beast: {row['beast']}. "
        "Keep full 4-type layers so you always hold the counter. "
        "(Heuristic estimate from pvp_brain §1/§9/§12 — not a counter_ai call.)"
    )
    return {
        "action": action,
        "lead_type": lead,
        "reasoning": reasoning,
        "confidence": confidence,
        "expected_loss": expected_loss,
        "source": "built-in fallback (counter_ai unavailable)",
        "raw": {"advantage_mult": advantage, "my_counter_troops": have},
    }


def counter_call(state: dict) -> dict:
    """Produce a counter plan, preferring counter_ai.decide, else the fallback."""
    module, import_error = load_counter_ai()
    if module is not None:
        plan, call_error = invoke_decide(module, state)
        if plan is not None:
            plan["engine_note"] = "counter_ai loaded"
            return plan
        fallback = fallback_decide(state)
        fallback["engine_note"] = f"counter_ai.decide() failed: {call_error}"
        return fallback
    fallback = fallback_decide(state)
    fallback["engine_note"] = f"counter_ai import failed: {import_error}"
    return fallback


def build_call_state(known: dict, opponent_lead=None, opponent_troops=None, our_lead=None) -> dict:
    """Assemble a broad, alias-rich state dict for decide()/fallback."""
    lead = normalize_type(opponent_lead)
    state = {
        "my_troops": known.get("my_troops", {}),
        "my_buffs": known.get("my_buffs", {}),
        "opponents": known.get("opponents", []),
        "opponent_lead": lead,
        "opponent_troops": opponent_troops,
        "our_lead": normalize_type(our_lead),
        # aliases to maximise the chance a named decide() parameter matches
        "roster": known.get("my_troops", {}),
        "army": known.get("my_troops", {}),
        "buffs": known.get("my_buffs", {}),
        "enemy_lead": lead,
        "lead_type": lead,
        "lead": lead,
        "enemy_troops": opponent_troops,
        "troop_count": opponent_troops,
        "opponent": {"lead": lead, "troops": opponent_troops},
        "enemy": {"lead": lead, "troops": opponent_troops},
    }
    return state


# --- Known-state DB pull ---------------------------------------------------


def _roster(cursor) -> tuple[dict, dict]:
    """Return (totals_by_type, per_type_tier_rows)."""
    totals = {kind: 0 for kind in TROOP_TYPES}
    tiers: dict[str, list] = {kind: [] for kind in TROOP_TYPES}
    cursor.execute(
        "SELECT building, tier, name, own FROM troops WHERE own IS NOT NULL AND own > 0"
    )
    for building, tier, name, own in cursor.fetchall():
        kind = BUILDING_TYPE.get((building or "").lower())
        if kind is None:
            continue
        totals[kind] += int(own or 0)
        tiers[kind].append({"tier": tier, "name": name, "own": int(own or 0)})
    for kind in tiers:
        tiers[kind].sort(key=lambda row: (row.get("tier") or 0), reverse=True)
    return totals, tiers


def _latest_buffs(cursor) -> dict:
    """Latest recorded battle buffs, keyed by side ('att'/'def') then type."""
    cursor.execute(
        """
        SELECT side, troop_type, attack_pct, defense_pct, hp_pct
        FROM battle_buffs
        WHERE report_id = (SELECT max(report_id) FROM battle_buffs)
        """
    )
    result: dict[str, dict] = {}
    for side, troop_type, attack, defense, hp in cursor.fetchall():
        result.setdefault(side or "?", {})[troop_type or "?"] = {
            "attack": attack,
            "defense": defense,
            "hp": hp,
        }
    return result


def _infer_lead_from_buffs(buffs, our_role: str) -> str | None:
    """Enemy lead = the branch where the enemy side has the highest attack buff."""
    if not isinstance(buffs, dict):
        return None
    enemy_side = "attacker" if our_role == "defender" else "defender"
    best_type, best_attack = None, -1
    for branch, entry in buffs.items():
        if branch not in TROOP_TYPES or not isinstance(entry, dict):
            continue
        side = entry.get(enemy_side)
        if not isinstance(side, dict):
            continue
        attack = side.get("attack")
        if isinstance(attack, (int, float)) and attack > best_attack:
            best_type, best_attack = branch, attack
    return best_type


def _classify_role(title) -> str:
    lowered = (title or "").lower()
    if "defen" in lowered:
        return "defender"
    return "attacker"


def _recent_opponents(cursor, limit: int = 8) -> list[dict]:
    cursor.execute(
        """
        SELECT rid, title, outcome, ts, defender, attacker, participants, buffs
        FROM report_extracts
        ORDER BY ts DESC NULLS LAST, updated_at DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )
    opponents = []
    for rid, title, outcome, ts, defender, attacker, participants, buffs in cursor.fetchall():
        name = None
        if isinstance(participants, list):
            for participant in participants:
                if isinstance(participant, dict) and participant.get("name"):
                    if not _is_us(participant["name"]):
                        name = participant["name"]
                        break
        if name is None:
            for candidate in (defender, attacker):
                if candidate and not _is_us(candidate):
                    name = candidate
                    break
        our_role = _classify_role(title)
        lead = _infer_lead_from_buffs(buffs, our_role)
        opponents.append(
            {
                "rid": rid,
                "name": name or "Unknown",
                "title": title or "",
                "outcome": outcome or "unknown",
                "ts": ts,
                "our_role": our_role,
                "lead_type": lead,
                "has_buffs": isinstance(buffs, dict) and bool(buffs),
            }
        )
    return opponents


def build_known_state(database) -> dict:
    warnings: list[str] = []
    totals, tiers = {kind: 0 for kind in TROOP_TYPES}, {kind: [] for kind in TROOP_TYPES}
    buffs: dict = {}
    opponents: list[dict] = []
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                try:
                    totals, tiers = _roster(cursor)
                except Exception as error:
                    warnings.append(f"roster ({type(error).__name__}): {error}")
                    connection.rollback()
                try:
                    buffs = _latest_buffs(cursor)
                except Exception as error:
                    warnings.append(f"buffs ({type(error).__name__}): {error}")
                    connection.rollback()
                try:
                    opponents = _recent_opponents(cursor)
                except Exception as error:
                    warnings.append(f"opponents ({type(error).__name__}): {error}")
                    connection.rollback()
    except Exception as error:
        warnings.append(f"database ({type(error).__name__}): {error}")

    current = next((opp for opp in opponents if opp.get("lead_type")), None)
    if current is None and opponents:
        current = opponents[0]

    return {
        "my_troops": totals,
        "my_tiers": tiers,
        "my_buffs": buffs,
        "opponents": opponents,
        "current_opponent": current,
        "warnings": warnings,
    }


# --- HTML rendering --------------------------------------------------------


def _type_pill(kind) -> str:
    meta = TYPE_META.get(kind or "unknown", TYPE_META["unknown"])
    return (
        f'<span class="pill" style="--pc:{meta["color"]}">'
        f'{meta["glyph"]} {html.escape(meta["label"])}</span>'
    )


def _plan_card_html(plan: dict, heading: str, opponent_line: str = "") -> str:
    action = html.escape(str(plan.get("action") or "—"))
    lead = plan.get("lead_type")
    reasoning = html.escape(str(plan.get("reasoning") or ""))
    confidence = plan.get("confidence")
    conf_str = html.escape(str(confidence)) if confidence not in (None, "") else "—"
    loss = plan.get("expected_loss")
    loss_str = html.escape(str(loss)) if loss not in (None, "") else "—"
    source = html.escape(str(plan.get("source") or ""))
    engine_note = html.escape(str(plan.get("engine_note") or ""))
    is_fallback = "fallback" in (plan.get("source") or "").lower()
    source_class = "src-fallback" if is_fallback else "src-ai"
    return f"""
<div class="plan">
  <div class="plan-head">
    <h2>{html.escape(heading)}</h2>
    <span class="engine {source_class}">{source}</span>
  </div>
  {opponent_line}
  <div class="action">{action}</div>
  <div class="plan-grid">
    <div class="metric"><span>Lead type</span>{_type_pill(lead)}</div>
    <div class="metric"><span>Confidence</span><b>{conf_str}</b></div>
    <div class="metric"><span>Expected loss</span><b>{loss_str}</b></div>
  </div>
  <p class="reasoning">{reasoning}</p>
  <p class="engine-note">{engine_note}</p>
</div>"""


def _roster_html(totals: dict) -> str:
    cells = []
    for kind in TROOP_TYPES:
        meta = TYPE_META[kind]
        cells.append(
            f'<div class="rt" style="--pc:{meta["color"]}">'
            f'<span class="rt-glyph">{meta["glyph"]}</span>'
            f'<span class="rt-label">{html.escape(meta["label"])}</span>'
            f'<b>{_fmt_int(totals.get(kind, 0))}</b></div>'
        )
    return f'<div class="roster">{"".join(cells)}</div>'


def _buffs_html(buffs: dict) -> str:
    if not buffs:
        return '<p class="muted">No battle buffs recorded yet.</p>'
    sides = [side for side in ("att", "def") if side in buffs] or list(buffs.keys())
    rows = []
    header = "".join(
        f"<th>{TYPE_META[kind]['glyph']} {TYPE_META[kind]['label']}</th>" for kind in TROOP_TYPES
    )
    for side in sides:
        side_label = "Attacker" if side == "att" else ("Defender" if side == "def" else side)
        cells = []
        for kind in TROOP_TYPES:
            entry = (buffs.get(side) or {}).get(kind) or {}
            atk = entry.get("attack")
            deff = entry.get("defense")
            hp = entry.get("hp")
            cells.append(
                f'<td><span class="b atk">A {_fmt_int(atk) if atk is not None else "—"}</span>'
                f'<span class="b def">D {_fmt_int(deff) if deff is not None else "—"}</span>'
                f'<span class="b hp">H {_fmt_int(hp) if hp is not None else "—"}</span></td>'
            )
        rows.append(f"<tr><th>{html.escape(side_label)}</th>{''.join(cells)}</tr>")
    return (
        '<div class="table-wrap"><table class="buffs"><thead><tr><th>Side</th>'
        f"{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _opponents_html(opponents: list) -> str:
    if not opponents:
        return '<p class="muted">No opponents on record.</p>'
    rows = []
    for opp in opponents:
        lead = opp.get("lead_type")
        lead_html = _type_pill(lead) if lead else '<span class="muted">lead ?</span>'
        rows.append(
            f'<li class="opp">'
            f'<span class="opp-name">{html.escape(str(opp.get("name") or "Unknown"))}</span>'
            f'<span class="opp-title">{html.escape(str(opp.get("title") or ""))}</span>'
            f'<span class="opp-outcome {html.escape(str(opp.get("outcome") or ""))}">'
            f'{html.escape(str(opp.get("outcome") or ""))}</span>'
            f"{lead_html}"
            f'<span class="opp-ts">{html.escape(_fmt_ts(opp.get("ts")))}</span>'
            f"</li>"
        )
    return f'<ul class="opps">{"".join(rows)}</ul>'


def render_page(known: dict, headline: dict) -> str:
    warnings = known.get("warnings") or []
    warn_html = ""
    if warnings:
        items = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings)
        warn_html = f'<div class="warn"><b>Degraded:</b><ul>{items}</ul></div>'

    current = known.get("current_opponent")
    if current:
        lead = current.get("lead_type")
        opp_line = (
            f'<div class="opp-line">vs '
            f'<b>{html.escape(str(current.get("name") or "Unknown"))}</b> '
            f'{html.escape(str(current.get("title") or ""))} '
            f'{_type_pill(lead) if lead else "(lead unknown)"}</div>'
        )
    else:
        opp_line = '<div class="opp-line muted">No current opponent — use the form below.</div>'

    headline_card = _plan_card_html(headline, "Live strategic call", opp_line)
    options = "".join(
        f'<option value="{kind}">{TYPE_META[kind]["glyph"]} {TYPE_META[kind]["label"]}</option>'
        for kind in TROOP_TYPES
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Strategic Counter — Murder Bot</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }}
main {{ width: min(1000px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }}
a {{ color: #58a6ff; text-decoration: none; }}
h1, h2, h3 {{ margin: 0; }}
header.top {{ display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }}
.sub {{ color: #8b949e; font-size: .9rem; margin-top: .3rem; }}
.warn {{ margin: 1rem 0; padding: .7rem 1rem; color: #d29922; background: #3d2f0b; border: 1px solid #9e6a03; border-radius: 8px; font-size: .85rem; }}
.warn ul {{ margin: .35rem 0 0; padding-left: 1.1rem; }}
.plan {{ margin: 1.4rem 0; padding: 1.2rem 1.3rem; background: #161b22; border: 1px solid #30363d; border-radius: 14px; }}
.plan-head {{ display: flex; align-items: center; justify-content: space-between; gap: .6rem; flex-wrap: wrap; }}
.plan-head h2 {{ font-size: 1.15rem; }}
.engine {{ padding: .2rem .6rem; border-radius: 999px; font-size: .72rem; font-weight: 700; letter-spacing: .02em; }}
.engine.src-ai {{ color: #3fb950; background: #12331d; border: 1px solid #238636; }}
.engine.src-fallback {{ color: #d29922; background: #3d2f0b; border: 1px solid #9e6a03; }}
.opp-line {{ margin: .7rem 0 .2rem; color: #adbac7; font-size: .95rem; }}
.action {{ margin: .8rem 0; font-size: 1.35rem; font-weight: 800; line-height: 1.25; color: #fff; }}
.plan-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; margin: .8rem 0; }}
.metric {{ background: #0d1117; border: 1px solid #21262d; border-radius: 9px; padding: .6rem .7rem; display: flex; flex-direction: column; gap: .35rem; }}
.metric span {{ color: #8b949e; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; }}
.metric b {{ font-size: 1.05rem; }}
.pill {{ display: inline-block; padding: .12rem .5rem; font-size: .8rem; font-weight: 700; color: var(--pc); border: 1px solid var(--pc); border-radius: 999px; white-space: nowrap; }}
.reasoning {{ margin: .6rem 0 0; color: #c9d1d9; font-size: .92rem; line-height: 1.5; }}
.engine-note {{ margin: .5rem 0 0; color: #6e7681; font-size: .76rem; font-family: ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }}
section.state {{ margin-top: 2rem; }}
section.state > h3 {{ font-size: .82rem; text-transform: uppercase; letter-spacing: .05em; color: #8b949e; margin-bottom: .7rem; }}
.roster {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .7rem; }}
.rt {{ background: #161b22; border: 1px solid #30363d; border-top: 3px solid var(--pc); border-radius: 10px; padding: .7rem; text-align: center; }}
.rt-glyph {{ display: block; font-size: 1.3rem; }}
.rt-label {{ display: block; color: #8b949e; font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; margin: .2rem 0; }}
.rt b {{ font-size: 1.05rem; font-variant-numeric: tabular-nums; }}
.table-wrap {{ overflow-x: auto; border: 1px solid #21262d; border-radius: 9px; margin-top: .3rem; }}
table.buffs {{ width: 100%; border-collapse: collapse; font-size: .8rem; }}
table.buffs th, table.buffs td {{ padding: .5rem .6rem; border-bottom: 1px solid #21262d; text-align: left; white-space: nowrap; }}
table.buffs thead th {{ color: #8b949e; font-weight: 600; text-transform: uppercase; font-size: .68rem; letter-spacing: .04em; }}
table.buffs td .b {{ display: inline-block; margin-right: .4rem; font-variant-numeric: tabular-nums; }}
table.buffs td .atk {{ color: #ff7b72; }} table.buffs td .def {{ color: #58a6ff; }} table.buffs td .hp {{ color: #3fb950; }}
ul.opps {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .5rem; }}
li.opp {{ display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; background: #161b22; border: 1px solid #30363d; border-radius: 9px; padding: .55rem .7rem; }}
.opp-name {{ font-weight: 700; }}
.opp-title {{ color: #8b949e; font-size: .82rem; }}
.opp-outcome {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; padding: .1rem .45rem; border-radius: 999px; }}
.opp-outcome.win {{ color: #3fb950; background: #12331d; }}
.opp-outcome.loss {{ color: #ff7b72; background: #3d1518; }}
.opp-ts {{ margin-left: auto; color: #6e7681; font-size: .76rem; }}
.muted {{ color: #6e7681; }}
form.hypo {{ margin-top: .7rem; display: flex; gap: .7rem; flex-wrap: wrap; align-items: flex-end; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1rem; }}
form.hypo label {{ display: flex; flex-direction: column; gap: .3rem; font-size: .78rem; color: #8b949e; }}
form.hypo select, form.hypo input {{ padding: .5rem .6rem; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 8px; font-size: .95rem; min-width: 9rem; }}
form.hypo button {{ padding: .55rem 1.1rem; background: #1f6feb; color: #fff; border: 0; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: .95rem; }}
form.hypo button:hover {{ background: #388bfd; }}
#hypo-result {{ margin-top: .2rem; }}
@media (max-width: 620px) {{
  main {{ padding: 1.25rem 0 3rem; }}
  .plan-grid {{ grid-template-columns: 1fr; }}
  .roster {{ grid-template-columns: repeat(2, 1fr); }}
  .action {{ font-size: 1.15rem; }}
}}
</style>
</head>
<body>
<main>
<header class="top">
  <div>
    <h1>Strategic Counter</h1>
    <div class="sub">Murder Bot — live AI counter call from current known state</div>
  </div>
  <a href="/">&larr; Dashboard</a>
</header>
{warn_html}
{headline_card}

<section class="state">
  <h3>Try a hypothetical opponent</h3>
  <form class="hypo" id="hypo-form">
    <label>Enemy lead type
      <select name="lead" id="hypo-lead">{options}</select>
    </label>
    <label>Enemy troop count
      <input type="number" name="troops" id="hypo-troops" min="0" step="1000" placeholder="e.g. 5000000">
    </label>
    <button type="submit">Get counter call</button>
  </form>
  <div id="hypo-result"></div>
</section>

<section class="state">
  <h3>Our roster (troops on record)</h3>
  {_roster_html(known.get("my_troops", {}))}
</section>

<section class="state">
  <h3>Latest recorded battle buffs (%)</h3>
  {_buffs_html(known.get("my_buffs", {}))}
</section>

<section class="state">
  <h3>Recent opponents</h3>
  {_opponents_html(known.get("opponents", []))}
</section>
</main>
<script>
const TYPE_META = {{
  ground: {{glyph: "\\u{{1F6E1}}", label: "Ground", color: "#3fb950"}},
  ranged: {{glyph: "\\u{{1F3F9}}", label: "Ranged", color: "#58a6ff"}},
  mounted: {{glyph: "\\u{{1F40E}}", label: "Mounted", color: "#ff7b72"}},
  siege: {{glyph: "\\u{{1F3F0}}", label: "Siege", color: "#a371f7"}},
  unknown: {{glyph: "?", label: "Unknown", color: "#8b949e"}}
}};
function esc(value) {{
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}}
function pill(kind) {{
  const meta = TYPE_META[kind] || TYPE_META.unknown;
  return '<span class="pill" style="--pc:' + meta.color + '">' + meta.glyph + ' ' + meta.label + '</span>';
}}
function planCard(plan) {{
  const fallback = String(plan.source || "").toLowerCase().includes("fallback");
  const cls = fallback ? "src-fallback" : "src-ai";
  return '<div class="plan">'
    + '<div class="plan-head"><h2>Hypothetical call</h2>'
    + '<span class="engine ' + cls + '">' + esc(plan.source) + '</span></div>'
    + '<div class="action">' + esc(plan.action || "—") + '</div>'
    + '<div class="plan-grid">'
    + '<div class="metric"><span>Lead type</span>' + pill(plan.lead_type) + '</div>'
    + '<div class="metric"><span>Confidence</span><b>' + esc(plan.confidence == null ? "—" : plan.confidence) + '</b></div>'
    + '<div class="metric"><span>Expected loss</span><b>' + esc(plan.expected_loss == null ? "—" : plan.expected_loss) + '</b></div>'
    + '</div>'
    + '<p class="reasoning">' + esc(plan.reasoning || "") + '</p>'
    + '<p class="engine-note">' + esc(plan.engine_note || "") + '</p>'
    + '</div>';
}}
document.getElementById("hypo-form").addEventListener("submit", async (event) => {{
  event.preventDefault();
  const lead = document.getElementById("hypo-lead").value;
  const troops = document.getElementById("hypo-troops").value;
  const box = document.getElementById("hypo-result");
  box.innerHTML = '<p class="muted">Computing…</p>';
  try {{
    const params = new URLSearchParams({{ lead }});
    if (troops) params.set("troops", troops);
    const response = await fetch("/api/counter?" + params.toString());
    if (!response.ok) throw new Error("failed");
    const plan = await response.json();
    box.innerHTML = planCard(plan);
  }} catch (error) {{
    box.innerHTML = '<p class="warn">Could not compute counter call.</p>';
  }}
}});
</script>
</body>
</html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the strategic-counter router wired to the host app's auth + DB."""
    router = APIRouter(tags=["counter"])

    @router.get("/counter", response_class=HTMLResponse)
    def counter_page(_user_id: int = Depends(current_user)):
        known = build_known_state(database)
        current = known.get("current_opponent") or {}
        state = build_call_state(
            known,
            opponent_lead=current.get("lead_type"),
            opponent_troops=current.get("troops"),
        )
        headline = counter_call(state)
        return HTMLResponse(render_page(known, headline))

    @router.get("/api/counter")
    def counter_api(
        _user_id: int = Depends(current_user),
        lead: str | None = Query(default=None, description="Enemy lead type"),
        troops: int | None = Query(default=None, ge=0, description="Enemy troop count"),
        our_lead: str | None = Query(default=None, description="Force our lead type"),
    ):
        known = build_known_state(database)
        state = build_call_state(
            known, opponent_lead=lead, opponent_troops=troops, our_lead=our_lead
        )
        plan = counter_call(state)
        plan["state"] = {
            "my_troops": known.get("my_troops", {}),
            "opponent_lead": normalize_type(lead),
            "opponent_troops": troops,
        }
        return JSONResponse(plan)

    return router
