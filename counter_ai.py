#!/usr/bin/env python3
"""counter_ai.py — advanced AI game-countering engine for the Murder Bot.

Read-only, gem/resource-safe strategic ADVISOR. It DECIDES; it never taps the
game, never spends gems, never touches ADB. Given a game state (opponent, their
scouted troops/buffs, an incoming rally, or a target I am eyeing, plus my roster
and buffs) it returns a RANKED COUNTER PLAN encoding the real Evony PvP doctrine
distilled in game_brain/pvp_brain.md:

  * the counter triangle (lead the type that beats their lead),
  * the 50% debuff cap (you can remove at most half an enemy buff),
  * "a solo poke into a whale = feeding" (never attack > ~2x my march),
  * "rally-train a big target to overflow its hospital → permanent kills",
  * "bubble/ghost any 100M+ coordinated rally" (the cap can't save a 60x wall),
  * Battlefield-event free-heal zeroing (CoC/BoC/BoG losses heal → be aggressive).

Where it helps, it QUANTIFIES a candidate plan by running the cloned Evony battle
simulator (node + evony-battle-simulator/js: createArmy/simulate) and reading the
predicted loss %. If the simulator or node is unavailable it falls back to an
analytic effective-power estimate — the rules path always works with no network.

An OPTIONAL LLM layer (Moonshot / Kimi, OpenAI-compatible) turns the state + a
pvp_brain summary into a natural-language strategic call when MOONSHOT_API_KEY is
set; it runs on a short timeout and NEVER blocks or overrides the safety rules.

  python counter_ai.py --demo         # run example states, print plans (no network)
  python counter_ai.py --demo --json  # same, machine-readable
  python counter_ai.py --state -       # read one state as JSON on stdin, decide

decide(state) is the single public entry point.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TROOP_TYPES = ("GROUND", "RANGED", "MOUNTED", "SIEGE")

# --- Counter triangle (pvp_brain.md §1). modifier = attacker row vs target col,
# T1-T10 base table; the type that scores 1.2x on the enemy lead is the counter. ---
DAMAGE_MATRIX = {
    "GROUND":  {"GROUND": 1.0,  "RANGED": 1.2, "MOUNTED": 0.7, "SIEGE": 1.1},
    "RANGED":  {"GROUND": 0.8,  "RANGED": 1.0, "MOUNTED": 1.2, "SIEGE": 1.1},
    "MOUNTED": {"GROUND": 1.2,  "RANGED": 0.8, "MOUNTED": 1.0, "SIEGE": 0.9},
    "SIEGE":   {"GROUND": 0.35, "RANGED": 0.4, "MOUNTED": 0.3, "SIEGE": 0.5},
}

# What I LEAD my defense/rally with against each enemy lead (pvp_brain.md §9/§12,
# sim-verified). Siege is special: ground meat-shield tanks + my siege out-ranges.
COUNTER_LEAD = {
    "SIEGE":   "GROUND",
    "GROUND":  "MOUNTED",
    "RANGED":  "GROUND",
    "MOUNTED": "RANGED",
}

# The mayor + defending beast to pull to the front for each enemy lead (§12 table).
COUNTER_KIT = {
    "SIEGE":   {"debuff_mayor": "Cimon",         "beast": "Tarasque (enemy siege atk -104%)"},
    "GROUND":  {"debuff_mayor": "Narses",        "beast": "Duneyrr (enemy ground HP)"},
    "RANGED":  {"debuff_mayor": "Gilgamesh",     "beast": "Rainbow Crow (enemy ground atk)"},
    "MOUNTED": {"debuff_mayor": "Hojo Ujiyasu",  "beast": "Otso (enemy mounted HP)"},
}

# Doctrine thresholds (pvp_brain.md §§11-13 + pvp_advisor break-even).
BUBBLE_GHOST_MILLIONS = 100.0      # bubble/ghost any 100M+ coordinated rally
COORD_RALLY_BREAKEVEN = 480.0      # a coordinated rally at/above this overwhelms the wall
SOLO_FEED_RATIO = 2.0              # never attack a target > 2x my march (else = feeding)
WHALE_BUFF_PCT = 3000.0           # can't out-debuff a 3,000%+ whale (50% cap floor too high)
DEBUFF_CAP = 0.5                   # a debuff removes at most half of the enemy's buff for a stat
MEASURED_SOLO_LOSS_PCT = 84.0      # measured: an 11M solo poke into a 660M-2,120M keep loses 84%

# Simulator location. Override with COUNTER_AI_SIM_JS; else the scratchpad clone.
SIM_JS_CANDIDATES = [
    os.environ.get("COUNTER_AI_SIM_JS"),
    "/private/tmp/claude-501/-Users-sward-work-scratch/"
    "c2e71639-9f51-4ec5-b5ef-685684771afc/scratchpad/evony-battle-simulator/js",
    str(Path.home() / "work/scratch/evony-bot/scratchpad/evony-battle-simulator/js"),
]

# Node harness: load troop-data + battle-engine into a VM context, read one JSON
# battle spec from stdin, print {winner, rounds, attacker, defender} summaries.
SIM_RUNNER = r"""
const fs = require("fs"), vm = require("vm");
const spec = JSON.parse(fs.readFileSync(0, "utf8"));
const ctx = {}; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1] + "/troop-data.js", "utf8"), ctx);
vm.runInContext(fs.readFileSync(process.argv[1] + "/battle-engine.js", "utf8"), ctx);
const be = ctx.BattleEngine;
const r = be.simulate(
  be.createArmy(spec.attacker.troops, spec.attacker.buffs),
  be.createArmy(spec.defender.troops, spec.defender.buffs),
  { maxRounds: spec.maxRounds || 250 }
);
process.stdout.write(JSON.stringify({
  winner: r.winner, rounds: r.rounds,
  attacker: { start: r.attacker._totalStart, remaining: r.attacker._total },
  defender: { start: r.defender._totalStart, remaining: r.defender._total }
}));
"""

# --- My real army, from parsed reports + sim_analysis_rally.js (NeoIsTlatoani). ---
DEFAULT_ROSTER = {
    "GROUND":  {"13": 31_000_000, "14": 31_000_000, "15": 30_100_000, "16": 25_969_677},
    "RANGED":  {"13": 71_000_000, "14": 25_500_000, "15": 21_000_000, "16": 15_222_740},
    "MOUNTED": {"13": 21_000_000, "14": 25_000_000, "15": 20_000_000, "16": 12_499_959},
    "SIEGE":   {"13": 101_001_000, "14": 50_000_000, "15": 30_050_000, "16": 20_280_000},
}
# My measured in-city (defense) buffs — pvp_brain.md §7. Siege is my strongest branch.
DEFAULT_IN_CITY_BUFFS = {
    "GROUND":  {"atk": 3498, "def": 4545, "hp": 4398, "range": 0, "rangeFlat": 0},
    "RANGED":  {"atk": 5162, "def": 4351, "hp": 4341, "range": 0, "rangeFlat": 0},
    "MOUNTED": {"atk": 3798, "def": 4362, "hp": 4515, "range": 0, "rangeFlat": 0},
    "SIEGE":   {"atk": 5861, "def": 4680, "hp": 4851, "range": 0, "rangeFlat": 0},
}
# Marching (attack) buffs — I drop the wall general + in-city gear when I march out
# (~60% of in-city, per OVERNIGHT_BRIEFING). Flagged as a model, not measured.
DEFAULT_MARCH_BUFFS = {
    t: {"atk": round(b["atk"] * 0.6), "def": round(b["def"] * 0.6),
        "hp": round(b["hp"] * 0.6), "range": 0, "rangeFlat": 0}
    for t, b in DEFAULT_IN_CITY_BUFFS.items()
}
DEFAULT_MARCH_MILLIONS = 11.0       # my measured single-march size
DEFAULT_RALLY_CAP_MILLIONS = 72.0   # War Hall L50 total rally capacity


# --------------------------------------------------------------------------- #
# State normalisation                                                          #
# --------------------------------------------------------------------------- #
def _troop_type(name):
    if not name:
        return None
    key = str(name).strip().upper()
    aliases = {"ARCHER": "RANGED", "CAVALRY": "MOUNTED", "HORSE": "MOUNTED",
               "INFANTRY": "GROUND", "GROUND": "GROUND", "RANGED": "RANGED",
               "MOUNTED": "MOUNTED", "SIEGE": "SIEGE"}
    return aliases.get(key, key if key in TROOP_TYPES else None)


def _as_buff(value, default=0.0):
    """A per-type buff dict from a scalar (applied to atk/def/hp) or an explicit dict."""
    if isinstance(value, dict):
        return {"atk": float(value.get("atk", default)), "def": float(value.get("def", default)),
                "hp": float(value.get("hp", default)),
                "range": float(value.get("range", 0)), "rangeFlat": float(value.get("rangeFlat", 0))}
    if isinstance(value, (int, float)):
        return {"atk": float(value), "def": float(value), "hp": float(value), "range": 0, "rangeFlat": 0}
    return {"atk": default, "def": default, "hp": default, "range": 0, "rangeFlat": 0}


def _enemy_buff_map(raw, lead_type, coordinated):
    """Build a per-type enemy buff map. `raw` may be a scalar, a per-type dict, or
    None (then default a whale-ish buff on the lead type: 6000% coordinated / 3000% solo)."""
    out = {t: {"atk": 0.0, "def": 0.0, "hp": 0.0, "range": 0, "rangeFlat": 0} for t in TROOP_TYPES}
    if isinstance(raw, dict) and any(_troop_type(k) in TROOP_TYPES for k in raw):
        for k, v in raw.items():
            tt = _troop_type(k)
            if tt:
                out[tt] = _as_buff(v)
        return out
    if raw is not None:
        base = _as_buff(raw)
    else:
        default = 6000.0 if coordinated else 3000.0
        base = {"atk": default, "def": default, "hp": default, "range": 0, "rangeFlat": 0}
    for t in TROOP_TYPES:
        out[t] = dict(base)
    if lead_type in TROOP_TYPES:
        out[lead_type] = dict(base)
    return out


def _synth_troops(total_millions, lead_type):
    """Model a scouted force of `total_millions` (millions) as a layered army:
    ~55% in the scouted lead type, the rest spread as decoy layers, across T14-16."""
    total = max(0.0, float(total_millions)) * 1_000_000
    if total <= 0:
        return {}
    shares = {t: 0.15 for t in TROOP_TYPES}
    if lead_type in TROOP_TYPES:
        shares = {t: (0.55 if t == lead_type else 0.15) for t in TROOP_TYPES}
    s = sum(shares.values())
    troops = {}
    for t in TROOP_TYPES:
        chunk = total * shares[t] / s
        if chunk <= 0:
            continue
        troops[t] = {"14": round(chunk * 0.30), "15": round(chunk * 0.35), "16": round(chunk * 0.35)}
    return troops


def _apply_debuff(enemy_buffs, my_debuff):
    """Reduce the enemy's buffs by my debuff, honouring the 50% cap (pvp_brain.md §10):
    you can remove at most half of the enemy's buff for a given stat/type."""
    if not my_debuff:
        return enemy_buffs
    out = {}
    for t in TROOP_TYPES:
        eb = dict(enemy_buffs.get(t, {"atk": 0, "def": 0, "hp": 0, "range": 0, "rangeFlat": 0}))
        db = my_debuff.get(t, my_debuff.get(t.lower(), {})) if isinstance(my_debuff, dict) else {}
        db = _as_buff(db) if db else {"atk": 0, "def": 0, "hp": 0}
        for stat in ("atk", "def", "hp"):
            base = float(eb.get(stat, 0))
            reduced = max(base * DEBUFF_CAP, base - float(db.get(stat, 0)))
            eb[stat] = reduced
        out[t] = eb
    return out


def _normalize(state):
    """Coerce a loose input dict into the fields decide() relies on."""
    state = dict(state or {})
    my = dict(state.get("my", {}))
    roster = my.get("roster") or DEFAULT_ROSTER
    roster = {(_troop_type(k) or k): {str(tier): int(c) for tier, c in v.items()}
              for k, v in roster.items() if _troop_type(k)}
    ctx = {
        "mode": str(state.get("mode", "open_map")).lower(),
        "free_heal": bool(state.get("event_free_heal") or state.get("free_heal")
                          or str(state.get("mode", "")).lower() in ("battlefield", "coc", "boc", "bog")),
        "opponent": state.get("opponent") or {},
        "incoming": state.get("incoming"),
        "target": state.get("target"),
        "my": {
            "roster": roster,
            "buffs": my.get("buffs") or DEFAULT_IN_CITY_BUFFS,
            "march_buffs": my.get("march_buffs") or DEFAULT_MARCH_BUFFS,
            "debuff": my.get("debuff") or {},
            "march_millions": float(my.get("march_millions", DEFAULT_MARCH_MILLIONS)),
            "rally_cap_millions": float(my.get("rally_cap_millions", DEFAULT_RALLY_CAP_MILLIONS)),
            "can_bubble": my.get("can_bubble", True),
            "sub_cities_up": my.get("sub_cities_up"),
        },
    }
    return ctx


# --------------------------------------------------------------------------- #
# Simulator + analytic loss model                                             #
# --------------------------------------------------------------------------- #
def _sim_js_dir():
    for cand in SIM_JS_CANDIDATES:
        if cand and (Path(cand) / "battle-engine.js").is_file() and (Path(cand) / "troop-data.js").is_file():
            return cand
    return None


def _node():
    for cand in (os.environ.get("COUNTER_AI_NODE"), shutil.which("node"),
                 str(Path.home() / ".local/share/mise/installs/node/lts/bin/node"),
                 "/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if not cand:
            continue
        try:
            if subprocess.run([cand, "--version"], capture_output=True, timeout=5).returncode == 0:
                return cand
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def run_simulator(attacker_troops, attacker_buffs, defender_troops, defender_buffs,
                  max_rounds=250, timeout=25):
    """Run one battle in the cloned Evony engine. Returns
    {winner, rounds, attacker:{start,remaining}, defender:{start,remaining}} or None
    if the simulator/node is unavailable or errors (caller falls back to analytic)."""
    js = _sim_js_dir()
    node = _node()
    if not js or not node:
        return None
    spec = {"attacker": {"troops": attacker_troops, "buffs": attacker_buffs},
            "defender": {"troops": defender_troops, "buffs": defender_buffs},
            "maxRounds": max_rounds}
    try:
        proc = subprocess.run([node, "-e", SIM_RUNNER, js], input=json.dumps(spec),
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _loss_pct(side):
    start = side.get("start") or 0
    if start <= 0:
        return 0.0
    return max(0.0, (start - (side.get("remaining") or 0)) / start * 100.0)


def _effective_strength(troops, buffs, offense=True):
    """Directional effective-power proxy: Σ count × 1.3^tier × (1 + buff/100).
    Offense weights ATK; defense weights (DEF+HP)/2. Tier weight 1.3x/tier per
    pvp_brain.md §3. Only used when the real simulator is unavailable."""
    total = 0.0
    for t in TROOP_TYPES:
        tb = _as_buff(buffs.get(t, {})) if isinstance(buffs, dict) else _as_buff(0)
        mult = 1.0 + (tb["atk"] if offense else (tb["def"] + tb["hp"]) / 2.0) / 100.0
        for tier, count in (troops.get(t, {}) or {}).items():
            try:
                total += float(count) * (1.3 ** int(tier)) * mult
            except (ValueError, TypeError):
                continue
    return total


def _analytic_battle(attacker_troops, attacker_buffs, defender_troops, defender_buffs, counter_side=None):
    """Fallback estimate when the simulator can't run. `counter_side` names which side
    (me) leads the type that counters the other's lead → gets the 1.2x matchup edge.
    Returns the same shape as a winner/loss forecast, flagged method='analytic'."""
    atk = _effective_strength(attacker_troops, attacker_buffs, offense=True)
    dfn = _effective_strength(defender_troops, defender_buffs, offense=False)
    if counter_side == "defender":
        dfn *= 1.2
    elif counter_side == "attacker":
        atk *= 1.2
    ratio = (dfn / atk) if atk > 0 else 999.0
    defender_loss = max(5.0, min(90.0, 100.0 / (1.0 + 0.8 * ratio ** 1.3)))
    attacker_loss = max(5.0, min(95.0, 100.0 / (1.0 + 0.8 * (1.0 / ratio) ** 1.3))) if ratio > 0 else 95.0
    winner = "DEFENDER" if ratio >= 1.1 else "ATTACKER"
    return {"winner": winner, "rounds": None, "method": "analytic", "ratio": round(ratio, 2),
            "defender_loss_pct": round(defender_loss, 1), "attacker_loss_pct": round(attacker_loss, 1)}


# --------------------------------------------------------------------------- #
# Plan builders                                                               #
# --------------------------------------------------------------------------- #
def _plan(action, lead_type, reasoning, confidence, expected_loss_pct, score,
          label=None, method=None, extra=None):
    plan = {
        "action": action,
        "lead_type": lead_type,
        "reasoning": reasoning,
        "confidence": round(float(confidence), 2),
        "expected_loss_pct": (round(float(expected_loss_pct), 1)
                              if expected_loss_pct is not None else None),
        "score": round(float(score), 1),
        "label": label or action,
        "method": method,
    }
    if extra:
        plan.update(extra)
    return plan


def _defense_plans(ctx):
    """Rank DEFEND / BUBBLE / GHOST / IGNORE for an incoming attack or rally."""
    inc = ctx["incoming"] or {}
    lead = _troop_type(inc.get("lead_type"))
    counter = COUNTER_LEAD.get(lead, "GROUND")
    kit = COUNTER_KIT.get(lead, {})
    coordinated = bool(inc.get("coordinated")) or str(inc.get("kind", "")).lower() == "rally"
    total_m = inc.get("total_millions")
    total_m = float(total_m) if isinstance(total_m, (int, float)) else None
    lead_buffs = _enemy_buff_map(inc.get("buffs"), lead, coordinated)
    lead_buff_pct = max(lead_buffs.get(lead, {}).get("atk", 0), lead_buffs.get(lead, {}).get("hp", 0)) \
        if lead in TROOP_TYPES else 0.0
    my = ctx["my"]

    enemy_troops = inc.get("troops") or _synth_troops(total_m if total_m else 0, lead)
    enemy_troops = {(_troop_type(k) or k): {str(tt): int(c) for tt, c in v.items()}
                    for k, v in (enemy_troops or {}).items() if _troop_type(k)}
    enemy_after_debuff = _apply_debuff(lead_buffs, my["debuff"])

    forecast = None
    method = "rule"
    if enemy_troops:
        sim = run_simulator(enemy_troops, enemy_after_debuff, my["roster"], my["buffs"])
        if sim:
            forecast = {"winner": sim["winner"], "rounds": sim["rounds"], "method": "simulator",
                        "defender_loss_pct": round(_loss_pct(sim["defender"]), 1),
                        "attacker_loss_pct": round(_loss_pct(sim["attacker"]), 1)}
            method = "simulator"
        else:
            forecast = _analytic_battle(enemy_troops, enemy_after_debuff, my["roster"], my["buffs"],
                                        counter_side="defender")
            method = forecast["method"]

    hold = forecast is None or forecast["winner"] == "DEFENDER"
    def_loss = forecast["defender_loss_pct"] if forecast else None

    plans = []
    kit_note = (f" Pull {kit['debuff_mayor']} + {kit['beast']} to the front."
                if kit else "")
    lead_label = f"{counter} (counters their {lead or 'lead'})" if lead else counter

    if ctx["free_heal"]:
        # Battlefield free-heal: every loss heals for free → stand and tank, hold
        # objectives, let broken rallies feed kill points. Bubble/ghost wastes it.
        plans.append(_plan(
            "defend", counter,
            f"Free-heal battlefield event: casualties heal at no permanent cost. STAND and tank, "
            f"lead {lead_label}, and HOLD objectives (Rally Hall / Turret / Battlefield Hospital "
            f"= 30,000 pts/hr).{kit_note} Never bubble/ghost here — it throws away the free heal.",
            0.9, 0.0, 100.0, label="defend (free-heal)", method=method,
            extra={"permanent_loss_pct": 0.0, "forecast": forecast}))
        plans.append(_plan("bubble", None,
                           "A truce here is wasted — losses are free-healed; do not spend the item.",
                           0.4, 0.0, 10.0, label="bubble (wasteful)", method="rule"))
        return plans, forecast, {"lead": lead, "counter": counter, "kit": kit}

    big_rally = coordinated and (
        (total_m is not None and total_m >= BUBBLE_GHOST_MILLIONS)
        or lead_buff_pct >= WHALE_BUFF_PCT
        or (total_m is not None and total_m >= COORD_RALLY_BREAKEVEN)
    )
    sim_says_lose = forecast is not None and forecast["winner"] == "ATTACKER"

    if big_rally or sim_says_lose:
        size_txt = f"{total_m:,.0f}M" if total_m is not None else "a coordinated rally"
        why = (f"{size_txt} coordinated rally" if big_rally else "the model predicts I get wiped")
        reason = (f"Deny the kill: {why}. The 50% debuff cap can't save a wall this outnumbered "
                  f"(pvp_brain.md §12). Bubble is the best reactive save (activate right up to impact — "
                  f"check the TIMER, not the cached shield); ghost only if no truce banked.")
        if my["can_bubble"]:
            plans.append(_plan("bubble", None, reason, 0.9, 0.0, 96.0, label="bubble", method="rule",
                               extra={"forecast": forecast}))
            plans.append(_plan("ghost", None,
                               "Fallback if you'd rather not spend a truce: send every troop out on "
                               "60-min player-rallies (no stamina) so scouts read 0 troops; recall lands "
                               "them instantly. Stash resources below cap first.",
                               0.75, 0.0, 88.0, label="ghost", method="rule"))
        else:
            plans.append(_plan("ghost", None,
                               reason + " No truce banked → GHOST: send every troop out on 60-min "
                               "player-rallies so scouts read 0; recall lands them instantly.",
                               0.82, 0.0, 92.0, label="ghost", method="rule", extra={"forecast": forecast}))
            plans.append(_plan("bubble", None, "No truce item available to bubble.",
                               0.3, 0.0, 20.0, label="bubble (unavailable)", method="rule"))
        # standing is the wrong call here, but surface its modeled cost for contrast
        stand_loss = def_loss if def_loss is not None else 70.0
        plans.append(_plan("defend", counter,
                           f"Standing loses ~{stand_loss:.0f}% permanently on the open map (no free heal). "
                           f"Not recommended vs this rally.",
                           0.5, stand_loss, max(5.0, 40.0 - stand_loss / 2), label="defend (risky)",
                           method=method, extra={"forecast": forecast}))
        return plans, forecast, {"lead": lead, "counter": counter, "kit": kit}

    # Solo / small coordinated hit the wall can math out → STAND with the counter lead.
    conf = 0.85 if method == "simulator" else 0.6
    if hold:
        loss = def_loss if def_loss is not None else 15.0
        reason = (f"Solo/small hit I can hold. Reinforce {lead_label} behind a meat-shield; "
                  f"defensive casualties WOUND and heal (in-city is my strength).{kit_note} "
                  + (f"Model: hold, ~{loss:.0f}% wounded" + (f" in {forecast['rounds']} rounds"
                     if forecast and forecast.get("rounds") else "") + "."
                     if forecast else "No scout numbers — standing a solo march is safe by default."))
        plans.append(_plan("defend", counter, reason, conf, loss, 100.0 - loss,
                           label="defend (stand)", method=method, extra={"forecast": forecast}))
        plans.append(_plan("ignore", None,
                           "Let it land — a solo march barely dents the garrison and wounds heal.",
                           0.5, loss, 55.0, label="ignore", method="rule"))
    else:
        loss = def_loss if def_loss is not None else 60.0
        plans.append(_plan("bubble" if my["can_bubble"] else "ghost", None,
                           f"Even this hit models a loss (~{loss:.0f}%): buffs/tiers favor them. "
                           f"Bubble or ghost rather than feed permanent kills.",
                           conf, 0.0, 90.0, label="bubble/ghost", method="rule", extra={"forecast": forecast}))
        plans.append(_plan("defend", counter,
                           f"Standing models ~{loss:.0f}% permanent loss — not recommended.",
                           0.4, loss, max(5.0, 30.0 - loss / 3), label="defend (risky)",
                           method=method, extra={"forecast": forecast}))
    return plans, forecast, {"lead": lead, "counter": counter, "kit": kit}


def _offense_plans(ctx):
    """Rank RALLY / IGNORE (/ solo, always flagged as feeding) for a target I'm eyeing."""
    tgt = ctx["target"] or {}
    lead = _troop_type(tgt.get("lead_type"))
    counter = COUNTER_LEAD.get(lead, "GROUND")
    defending_m = tgt.get("defending_millions")
    defending_m = float(defending_m) if isinstance(defending_m, (int, float)) else None
    my = ctx["my"]
    march_m = my["march_millions"]
    rally_cap_m = my["rally_cap_millions"]

    tgt_buffs = _enemy_buff_map(tgt.get("buffs"), lead, coordinated=True)
    tgt_after_debuff = _apply_debuff(tgt_buffs, my["debuff"])
    tgt_troops = tgt.get("troops") or _synth_troops(defending_m if defending_m else 0, lead)
    tgt_troops = {(_troop_type(k) or k): {str(tt): int(c) for tt, c in v.items()}
                  for k, v in (tgt_troops or {}).items() if _troop_type(k)}

    def _my_force(total_m, buffs):
        total = sum(sum(v.values()) for v in my["roster"].values())
        want = total_m * 1_000_000
        if total <= 0:
            return {}
        f = min(1.0, want / total)
        return {t: {tier: max(0, round(c * f)) for tier, c in v.items()} for t, v in my["roster"].items()}

    plans = []
    ratio = (defending_m / march_m) if (defending_m and march_m) else None

    # RALLY forecast: my rally (capacity-scaled, marching buffs) vs the target.
    rally_troops = _my_force(rally_cap_m, my["march_buffs"])
    forecast = None
    method = "rule"
    if tgt_troops and rally_troops:
        sim = run_simulator(rally_troops, my["march_buffs"], tgt_troops, tgt_after_debuff)
        if sim:
            forecast = {"winner": sim["winner"], "rounds": sim["rounds"], "method": "simulator",
                        "attacker_loss_pct": round(_loss_pct(sim["attacker"]), 1),
                        "defender_loss_pct": round(_loss_pct(sim["defender"]), 1)}
            method = "simulator"
        else:
            forecast = _analytic_battle(rally_troops, my["march_buffs"], tgt_troops, tgt_after_debuff,
                                        counter_side="attacker")
            method = forecast["method"]

    if ctx["free_heal"]:
        plans.append(_plan("rally", counter,
                           f"Free-heal battlefield: rally-to-ZERO at no permanent cost. Lead {counter} "
                           f"(counters their {lead or 'lead'}), stack the leader's buffs on the whole march, "
                           f"clear defenders off objectives, then hold them (30,000 pts/hr).",
                           0.85, 0.0, 100.0, label="rally-to-zero", method=method,
                           extra={"permanent_loss_pct": 0.0, "forecast": forecast}))
        return plans, forecast, {"lead": lead, "counter": counter}

    solo_feeds = defending_m is not None and ratio is not None and ratio > SOLO_FEED_RATIO
    rally_wins = forecast is not None and forecast["winner"] == "ATTACKER"
    my_rally_loss = forecast.get("attacker_loss_pct") if forecast else None

    if rally_wins:
        loss = my_rally_loss if my_rally_loss is not None else 40.0
        plans.append(_plan("rally", counter,
                           f"A capacity rally (~{rally_cap_m:,.0f}M) models a WIN leading {counter} vs their "
                           f"{lead or 'lead'} (~{loss:.0f}% of the combined march lost). To shrink them "
                           f"PERMANENTLY, chain winning rallies faster than they heal → hospital overflow → "
                           f"kills (pvp_brain.md §13A). Scout that their buffs/reinforcements are DOWN first.",
                           0.8 if method == "simulator" else 0.55, loss, 100.0 - loss,
                           label="coordinated rally", method=method, extra={"forecast": forecast}))
    if solo_feeds:
        plans.append(_plan("ignore", None,
                           f"Do NOT solo-poke: {defending_m:,.0f}M defending is {ratio:.0f}x my ~{march_m:,.0f}M "
                           f"march — measured outcome is ~{MEASURED_SOLO_LOSS_PCT:.0f}% of my march KILLED "
                           f"permanently (no attacker hospital) for ~2% of theirs. That is feeding "
                           f"(pvp_brain.md §13A). Rally it with the alliance or leave it.",
                           0.9, MEASURED_SOLO_LOSS_PCT, 85.0 if not rally_wins else 60.0,
                           label="ignore (solo=feeding)", method="rule",
                           extra={"solo_loss_pct": MEASURED_SOLO_LOSS_PCT}))
    if not rally_wins and not solo_feeds:
        loss = my_rally_loss if my_rally_loss is not None else 60.0
        plans.append(_plan("ignore", None,
                           f"Not worth it: even a full rally models a loss (~{loss:.0f}% of my march). "
                           f"Marching buffs are weaker than in-city and PvP-attack losses are permanent. "
                           f"Make them come to you.",
                           0.7 if method == "simulator" else 0.5, loss, 70.0,
                           label="ignore", method=method, extra={"forecast": forecast}))
    return plans, forecast, {"lead": lead, "counter": counter}


def _idle_plan(ctx):
    return [_plan("ignore", None,
                  "No incoming attack and no target specified — nothing to counter. Keep the anvil "
                  "garrisoned, sub-cities up, and a 3-day + 24h truce banked for a surprise rally.",
                  0.5, 0.0, 50.0, label="idle", method="rule")]


# --------------------------------------------------------------------------- #
# LLM layer (optional, non-blocking)                                          #
# --------------------------------------------------------------------------- #
def _pvp_brain_summary():
    """Compact doctrine brief for the LLM prompt (and human context)."""
    return (
        "Evony PvP doctrine (NeoIsTlatoani, siege-anvil defender, ~530M army):\n"
        "- Counter triangle: Mounted>Ground>Ranged>Mounted (1.2x); Ground & hi-tier Mounted > Siege (1.1-1.2x); "
        "Siege counters nothing (0.3-0.5x) but out-ranges. Lead the type that counters their lead.\n"
        "- 50% debuff cap: you can remove at most half an enemy buff for a stat; over-stacking is wasted.\n"
        "- Attacker losses in open-map PvP are ~100% KILLED (no attacker hospital); defender losses WOUND and heal. "
        "Offense is the trap.\n"
        "- Solo poke into a whale = feeding (measured 84% of my march killed vs 660M-2,120M keeps). Never attack a "
        "target > ~2x my ~11M march. Take big targets with a COORDINATED RALLY, and chain rallies to overflow their "
        "hospital → permanent kills.\n"
        "- Bubble or ghost any 100M+ coordinated rally; the cap can't save a 60x-outnumbered wall. Bubble is the best "
        "reactive save (check the timer, not the cached shield); ghost = send all troops out on 60-min rallies.\n"
        "- Battlefield events (CoC/BoC/BoG) FREE-HEAL every loss → stand/rally aggressively, zero the enemy, and HOLD "
        "objectives (30,000 pts/hr). Open-map SvS has no free heal → highest caution."
    )


def llm_call(state, rules_plan, timeout=None, model=None):
    """Optional Moonshot/Kimi natural-language strategic call. Returns
    {"used": True, "text": ...} or {"used": False, "reason": ...}. Never raises,
    never blocks longer than `timeout`, and never overrides the rules plan."""
    key = os.environ.get("MOONSHOT_API_KEY")
    if not key:
        return {"used": False, "reason": "MOONSHOT_API_KEY not set"}
    import urllib.error
    import urllib.request
    timeout = float(timeout if timeout is not None else os.environ.get("COUNTER_AI_LLM_TIMEOUT", 8))
    base = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
    models = [m for m in (model, os.environ.get("MOONSHOT_MODEL"),
                          "kimi-k2-0711-preview", "moonshot-v1-8k") if m]
    system = ("You are the PvP war-room advisor for an Evony account. Use ONLY the doctrine and the "
              "rules-engine plan provided. Give a crisp 2-4 sentence strategic call: the single action, "
              "the lead type, and the one reason. Do not invent numbers. Never advise spending gems.")
    user = (f"{_pvp_brain_summary()}\n\nGAME STATE:\n{json.dumps(state, default=str)[:2500]}\n\n"
            f"RULES-ENGINE PLAN (authoritative — explain/confirm it, do not contradict):\n"
            f"{json.dumps({k: rules_plan.get(k) for k in ('action', 'lead_type', 'expected_loss_pct', 'reasoning')}, default=str)[:1500]}")
    for m in models:
        payload = json.dumps({"model": m, "temperature": 0.3, "max_tokens": 260,
                              "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(f"{base}/chat/completions", data=payload,
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
            text = (body.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            if text:
                return {"used": True, "model": m, "text": text}
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404) and m != models[-1]:
                continue  # unknown model on this account — try the next id
            return {"used": False, "reason": f"HTTP {exc.code}"}
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return {"used": False, "reason": "request failed or timed out"}
    return {"used": False, "reason": "no model accepted the request"}


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #
def decide(state, use_llm=None, use_sim=None):
    """Return a RANKED COUNTER PLAN for a game state.

    state (all optional):
      mode: "open_map" | "battlefield" | "coc" | "boc" | "bog" | "svs"
      event_free_heal: bool                     # force free-heal doctrine
      opponent: {"alliance": "DTP", "name": "Karu"}
      incoming: {                               # → a DEFENSE decision
         kind: "rally"|"solo"|"scout", lead_type: "SIEGE",
         total_millions: 130, coordinated: true,
         buffs: 7000 | {"SIEGE": {"atk":7000,...}},   # scouted (Watchtower)
         troops: {"SIEGE": {"16": ...}} }             # scouted per-tier (optional)
      target: {                                 # → an OFFENSE decision
         defending_millions: 660, lead_type: "GROUND", buffs: ..., troops: ... }
      my: { roster, buffs, march_buffs, debuff, march_millions,
            rally_cap_millions, can_bubble, sub_cities_up }   # defaults baked in

    Returns a dict that IS the top-ranked plan — action, lead_type, reasoning,
    confidence, expected_loss_pct — plus: situation, ranked_plans, doctrine,
    counter (lead/kit), sim_used, and llm (natural-language call or why it was skipped).
    """
    ctx = _normalize(state or {})

    if ctx["incoming"]:
        situation = "defense"
        plans, forecast, meta = _defense_plans(ctx)
    elif ctx["target"]:
        situation = "offense"
        plans, forecast, meta = _offense_plans(ctx)
    else:
        situation = "idle"
        plans, forecast, meta = _idle_plan(ctx), None, {}

    plans.sort(key=lambda p: p["score"], reverse=True)
    top = plans[0]

    doctrine_notes = []
    if ctx["free_heal"]:
        doctrine_notes.append("Free-heal battlefield event → losses are recoverable; be aggressive.")
    else:
        doctrine_notes.append("Open map (no free heal) → attacker losses are permanent; defense is cheaper.")
    if meta.get("lead"):
        doctrine_notes.append(
            f"Their lead {meta['lead']} → counter with {meta['counter']} (1.2x on their lead).")
    if meta.get("kit"):
        doctrine_notes.append(
            f"Front the {meta['kit'].get('debuff_mayor')} debuff mayor + {meta['kit'].get('beast')}.")

    sim_used = any(p.get("method") == "simulator" for p in plans) or (
        forecast is not None and forecast.get("method") == "simulator")

    result = dict(top)
    result.update({
        "situation": situation,
        "opponent": ctx["opponent"],
        "ranked_plans": plans,
        "forecast": forecast,
        "counter_lead": meta.get("counter"),
        "counter_kit": meta.get("kit"),
        "doctrine": doctrine_notes,
        "sim_used": sim_used,
        "sim_available": _sim_js_dir() is not None,
    })

    # SELF-EVOLVING: cite what the bot has LEARNED (distilled from ingested YouTube/Discord)
    # relevant to this situation, so watched content actually shapes the decision. Best-effort.
    try:
        import knowledge_synth
        _q = " ".join(str(x) for x in (result.get("action"), result.get("lead_type"),
                                       result.get("counter_lead"), situation) if x)
        result["learned"] = knowledge_synth.relevant(_q, k=3)
    except Exception:
        result["learned"] = []

    want_llm = use_llm if use_llm is not None else bool(os.environ.get("MOONSHOT_API_KEY"))
    if want_llm:
        result["llm"] = llm_call(state or {}, top)
    else:
        result["llm"] = {"used": False, "reason": "disabled" if use_llm is False else "MOONSHOT_API_KEY not set"}
    return result


def lookup_enemy(name, dsn="dbname=murderbot"):
    """Pull an opponent's scouted intel from the `enemies` DB (troops, buffs, generals,
    W/L record, threat). Returns None if unknown or the DB is unavailable. Best-effort."""
    try:
        import psycopg2
        cur = psycopg2.connect(dsn).cursor()
        cur.execute("""SELECT name, alliance, max_troops, buffs, generals, my_wins, my_losses, threat, coords
                       FROM enemies WHERE name ILIKE %s ORDER BY battles DESC NULLS LAST LIMIT 1""",
                    ("%" + str(name).strip("[]").split("]")[-1] + "%",))
        row = cur.fetchone()
        if not row:
            return None
        n, alliance, troops, buffs, generals, w, l, threat, coords = row
        return {"name": n, "alliance": alliance, "max_troops": troops, "buffs": buffs,
                "generals": generals, "record": f"{w or 0}-{l or 0}", "threat": threat, "coords": coords}
    except Exception:
        return None


def decide_vs(opponent, situation="open_map", incoming=None, lead_type=None):
    """Auto-intel counter call: look the opponent up in the enemies DB and feed their scouted
    troops/buffs into decide(), so the bot uses what it has LEARNED about that specific player."""
    intel = lookup_enemy(opponent)
    state = {"opponent": opponent, "mode": situation}
    inc = dict(incoming or {})
    if intel:
        if intel.get("max_troops"):
            inc.setdefault("total_millions", (intel["max_troops"] or 0) / 1e6)
        if intel.get("buffs"):
            inc.setdefault("buffs", intel["buffs"])
    if lead_type:
        inc.setdefault("lead_type", lead_type)
    if inc:
        inc.setdefault("kind", "rally")
        inc.setdefault("coordinated", (inc.get("total_millions", 0) or 0) >= 100)
        state["incoming"] = inc
    d = decide(state)
    d["intel_used"] = bool(intel)
    d["intel"] = intel
    return d


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
DEMO_STATES = [
    ("Mega-rally incoming (my #1 loss cause)", {
        "mode": "open_map",
        "opponent": {"alliance": "DTP", "name": "Karu"},
        "incoming": {"kind": "rally", "lead_type": "siege", "total_millions": 130,
                     "coordinated": True, "buffs": 7000},
    }),
    ("Solo siege poke I can hold", {
        "mode": "open_map",
        "opponent": {"alliance": "ViG", "name": "Viper2302"},
        "incoming": {"kind": "solo", "lead_type": "siege", "total_millions": 18, "buffs": 3000},
    }),
    ("Incoming ground march (counter with mounted)", {
        "mode": "open_map",
        "opponent": {"alliance": "ViG", "name": "Katar"},
        "incoming": {"kind": "solo", "lead_type": "ground", "total_millions": 25, "buffs": 3200},
    }),
    ("Tempting solo poke into a whale = feeding", {
        "mode": "open_map",
        "opponent": {"alliance": "DTP", "name": "Polaris"},
        "target": {"defending_millions": 660, "lead_type": "ground", "buffs": 4500},
    }),
    ("Coordinated rally on a soft target", {
        "mode": "open_map",
        "opponent": {"alliance": "DTP", "name": "scout-target"},
        "target": {"defending_millions": 40, "lead_type": "ranged", "buffs": 3000},
    }),
    ("Clash of Civilizations — free-heal, zero them", {
        "mode": "coc",
        "opponent": {"alliance": "enemy-server", "name": "objective-holder"},
        "target": {"defending_millions": 300, "lead_type": "mounted", "buffs": 5000},
    }),
]


def _fmt_plan(p, indent="   "):
    loss = f"{p['expected_loss_pct']:.0f}%" if p.get("expected_loss_pct") is not None else "n/a"
    return (f"{indent}[{p['score']:5.1f}] {p['action'].upper():7s} "
            f"lead={str(p.get('lead_type') or '-'):7s} loss={loss:>4s} "
            f"conf={p['confidence']:.2f} via {p.get('method') or 'rule'}\n"
            f"{indent}        {p['reasoning']}")


def _print_decision(title, state, use_llm):
    print("=" * 92)
    print(title)
    opp = state.get("opponent") or {}
    if opp:
        print(f"opponent: [{opp.get('alliance', '?')}]{opp.get('name', '?')}   mode: {state.get('mode', 'open_map')}")
    d = decide(state, use_llm=use_llm)
    print(f"\n>>> RECOMMEND: {d['action'].upper()}"
          + (f" leading {d['lead_type']}" if d.get("lead_type") else "")
          + f"   (confidence {d['confidence']:.2f}, "
          + (f"expected loss {d['expected_loss_pct']:.0f}%" if d.get("expected_loss_pct") is not None else "no loss est")
          + f", {'simulator' if d['sim_used'] else 'rules'})")
    print(f"    {d['reasoning']}")
    print(f"\n    situation={d['situation']}  sim_available={d['sim_available']}  sim_used={d['sim_used']}")
    print("    ranked plans:")
    for p in d["ranked_plans"]:
        print(_fmt_plan(p))
    if d.get("doctrine"):
        print("    doctrine:")
        for note in d["doctrine"]:
            print(f"      - {note}")
    llm = d.get("llm") or {}
    if llm.get("used"):
        print(f"\n    LLM ({llm.get('model')}): {llm['text']}")
    else:
        print(f"\n    LLM: not used ({llm.get('reason')})")
    print()
    return d


def _run_demo(as_json, use_llm):
    if as_json:
        out = [{"title": t, "decision": decide(s, use_llm=use_llm)} for t, s in DEMO_STATES]
        print(json.dumps(out, indent=2, default=str))
        return
    print(f"counter_ai demo — simulator {'AVAILABLE' if _sim_js_dir() else 'NOT FOUND (analytic fallback)'}; "
          f"node {'ok' if _node() else 'missing'}; "
          f"LLM {'ON' if use_llm else 'off'} (MOONSHOT_API_KEY {'set' if os.environ.get('MOONSHOT_API_KEY') else 'unset'})\n")
    for title, state in DEMO_STATES:
        _print_decision(title, state, use_llm)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Advanced AI game-countering engine (read-only advisory).")
    ap.add_argument("--demo", action="store_true", help="run example states and print counter plans")
    ap.add_argument("--state", metavar="FILE", help="decide on one state read as JSON ('-' for stdin)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--llm", action="store_true", help="enable the Moonshot/Kimi layer (needs MOONSHOT_API_KEY)")
    ap.add_argument("--no-llm", action="store_true", help="force the LLM layer off")
    args = ap.parse_args(argv)

    use_llm = True if args.llm else (False if args.no_llm else None)
    if args.demo and use_llm is None:
        use_llm = False  # keep the demo network-free unless --llm is passed

    if args.state:
        raw = sys.stdin.read() if args.state == "-" else Path(args.state).read_text()
        state = json.loads(raw)
        decision = decide(state, use_llm=use_llm)
        if args.json:
            print(json.dumps(decision, indent=2, default=str))
        else:
            _print_decision(state.get("title", "decision"), state, use_llm)
        return 0

    if args.demo:
        _run_demo(args.json, bool(use_llm))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
