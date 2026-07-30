#!/usr/bin/env python3
"""attack_planner.py — the ATTACK pillar of the Murder Bot ("learn how to attack,
independently, for an alliance").

This is the offensive counterpart to the read-only advisor in counter_ai.py. It
turns the scouted `enemies` table (Postgres murderbot) into a RANKED list of
favorable-trade targets, produces a full attack plan for any one of them via
counter_ai.decide(), and — only under an explicit, gem-safe, config-gated path —
launches the march/rally by tapping the game.

It encodes the attack doctrine distilled in game_brain/pvp_brain.md:
  * a SOLO poke into a whale = feeding (never attack a target > ~2x my ~11M march);
  * take big targets with a COORDINATED RALLY, chained to overflow their hospital
    → permanent kills ("rally big targets to make them small later");
  * LEAD the type that counters their lead (counter_ai.COUNTER_LEAD), bulk the
    march with Ground T11–T14 (my measured top attack killers) + Siege T14–17
    behind, add thin decoy layers;
  * pop MARCHING/attack buffs (the in-city wall general does not march); the rally
    leader's general buffs apply to the WHOLE combined march;
  * Battlefield events (CoC/BoC/BoG) free-heal every loss → rally to ZERO at no
    permanent cost.

SAFETY — this module NEVER spends. pick_targets/plan_attack are pure read-only
analysis (DB + counter_ai, no emulator). execute_attack DEFAULTS to dry_run=True
(it only LOGS the intended taps). A real launch requires ALL of:
    dry_run=False  AND  bot_config.json advanced.auto_attack == true
and even then it taps ONLY target → Attack/Rally → troop preset → March. It never
taps Buy / Confirm-purchase / Instant / gem / Quit, aborts on any purchase/gem
popup, and sends only troops you already own (the saved preset caps the count).

  python attack_planner.py --plan     # rank targets + print plans (dry-run, no emulator)
  python attack_planner.py --plan --json
  python attack_planner.py --stats

Public API: pick_targets(), plan_attack(target), execute_attack(target, dry_run=True).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _repo_roots():
    """Directories to search for sibling modules/config. In a git worktree the
    untracked deps (counter_ai.py, bot_config.json) live in the main checkout, so
    fall back to it after the script's own directory."""
    roots = [HERE]
    s = str(HERE)
    if "/.claude/worktrees/" in s:
        roots.append(Path(s.split("/.claude/worktrees/")[0]))
    seen, out = set(), []
    for r in roots:
        if str(r) not in seen:
            seen.add(str(r))
            out.append(r)
    return out


ROOTS = _repo_roots()

for _r in ROOTS:
    if (_r / "counter_ai.py").is_file() and str(_r) not in sys.path:
        sys.path.insert(0, str(_r))
        break

import counter_ai  # noqa: E402  (path set up above)

DEV = "127.0.0.1:5555"
MARCH_XY = (810, 1830)          # gold "March" on the setup screen (from live_rally)
MARCH_MILLIONS = counter_ai.DEFAULT_MARCH_MILLIONS          # my measured single march (~11M)
RALLY_CAP_MILLIONS = counter_ai.DEFAULT_RALLY_CAP_MILLIONS  # War Hall L50 total (~72M)
SOLO_FEED_RATIO = counter_ai.SOLO_FEED_RATIO               # never solo a target > 2x my march

# Never let a tap land on any of these — spending controls / game-exit.
FORBIDDEN_TAP_TOKENS = (
    "buy", "purchase", "gem", "gems", "recharge", "instant", "speed up", "speedup",
    "pay", "checkout", "top up", "top-up", "topup", "refill", "use gold", "use gems",
    "confirm purchase", "subscribe", "vip", "unlock", "chf", "usd", "€", "£", "₫", "$",
    "quit", "exit game",
)
# The ONLY button labels execute_attack is ever allowed to tap.
ALLOWED_BUTTON_TOKENS = ("attack", "rally", "march", "preset", "new troop", "deploy", "join")

ATTACK_DOCTRINE = {
    "lead_priority": (
        "Lead the type that counters their lead (counter_ai.COUNTER_LEAD). Bulk the "
        "march with Ground T11–T14 (my measured top attack killers, per pvp_brain §13) "
        "and keep Siege T14–17 behind them. Add 1–10k of every OTHER type as sacrificial "
        "decoy layers so their high-tier chews junk while my top tiers keep firing."
    ),
    "buffs_to_pop": [
        "Swap to the ATTACK general — the in-city wall general does NOT march; his buffs "
        "fire only on defense.",
        "Pop Marching/Attacking-troop buffs (research + gear + blazons refined to Attacking "
        "Atk/HP); marching buffs are ~60% of in-city, so respect the weaker number.",
        "For a RALLY: the leader's general buffs apply to the WHOLE combined march — leader "
        "= strongest attack general + biggest War Hall + the correct counter type.",
        "Debuff their lead type where the rally leader can (sub-city mayor debuffs do not "
        "march out — they are a defensive lever only).",
        "NEVER pop gem / speed / instant items. Send only troops already trained.",
    ],
}


# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #
def _config_path():
    for r in ROOTS:
        p = r / "bot_config.json"
        if p.is_file():
            return p
    return HERE / "bot_config.json"


def load_config():
    """Read bot_config.json (worktree copy preferred, else the main checkout). Returns
    {} if it cannot be read — callers must treat a missing value as the safe default."""
    try:
        return json.loads(_config_path().read_text())
    except (OSError, ValueError):
        return {}


def auto_attack_enabled(cfg=None):
    """True ONLY if bot_config.json advanced.auto_attack is exactly true. Any other
    value (missing, false, null, truthy-non-true) is treated as OFF."""
    cfg = cfg if cfg is not None else load_config()
    return (cfg.get("advanced") or {}).get("auto_attack") is True


# --------------------------------------------------------------------------- #
# enemies table -> counter_ai target state                                    #
# --------------------------------------------------------------------------- #
def _db_dsn():
    return os.environ.get("MURDERBOT_DSN") or "dbname=murderbot"


ENEMY_COLS = ("name", "alliance", "battles", "my_wins", "my_losses", "max_troops",
              "coords", "buffs", "generals", "threat", "last_seen")


def load_enemies():
    """All rows of the Postgres `enemies` table as dicts. Raises RuntimeError with a
    clear message if psycopg2 or the DB is unavailable (never fabricates targets)."""
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError("psycopg2 not installed — cannot read the enemies table "
                           "(run under the project .venv).") from exc
    try:
        conn = psycopg2.connect(_db_dsn())
    except Exception as exc:  # noqa: BLE001 — surface any connection failure verbatim
        raise RuntimeError(f"cannot connect to Postgres murderbot: {exc}") from exc
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(ENEMY_COLS)} FROM enemies")
        rows = [dict(zip(ENEMY_COLS, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    return rows


def _norm_name(name):
    return "".join(str(name or "").lower().split())


def find_enemy(name):
    """Look one enemy up by name (whitespace/case-insensitive; tolerates OCR spacing
    like 'Katar a'). Returns the row dict or None."""
    want = _norm_name(name)
    if not want:
        return None
    for row in load_enemies():
        if _norm_name(row.get("name")) == want or want in _norm_name(row.get("name")):
            return row
    return None


def _infer_lead(row):
    """Best-effort enemy lead type from a scouted per-type buff map (highest atk).
    Returns a counter_ai troop type or None — never guesses from thin air."""
    buffs = row.get("buffs")
    if isinstance(buffs, dict):
        best, best_val = None, float("-inf")
        for k, v in buffs.items():
            tt = counter_ai._troop_type(k)
            if not tt:
                continue
            atk = v.get("atk") if isinstance(v, dict) else v
            try:
                atk = float(atk)
            except (TypeError, ValueError):
                continue
            if atk > best_val:
                best, best_val = tt, atk
        if best:
            return best
    return None


def enemy_to_target(row):
    """Map an `enemies` row to a counter_ai OFFENSE target dict. Unknown fields stay
    None (counter_ai then scout-gates the call rather than inventing a matchup)."""
    row = row or {}
    mt = row.get("max_troops")
    defending_millions = (float(mt) / 1_000_000) if mt else None
    tgt = {"defending_millions": defending_millions, "lead_type": _infer_lead(row)}
    if isinstance(row.get("buffs"), dict):
        tgt["buffs"] = row["buffs"]
    if isinstance(row.get("troops"), dict):
        tgt["troops"] = row["troops"]
    return tgt


def enemy_state(row, mode="open_map"):
    """A full counter_ai state (opponent + target) for one enemy row."""
    row = row or {}
    return {
        "mode": mode,
        "opponent": {"alliance": row.get("alliance"), "name": row.get("name")},
        "target": enemy_to_target(row),
    }


# --------------------------------------------------------------------------- #
# Favorable-trade assessment                                                  #
# --------------------------------------------------------------------------- #
def _assess(row, decision):
    """Score/label one target from its counter_ai decision + historical record.
    Returns {trade_score, attackable, vector, go_no_go, reasons}."""
    row = row or {}
    reasons = []
    action = decision.get("action")
    forecast = decision.get("forecast") or {}
    exp_loss = decision.get("expected_loss_pct")
    defending_m = enemy_to_target(row).get("defending_millions")

    wins = int(row.get("my_wins") or 0)
    losses = int(row.get("my_losses") or 0)
    battles = wins + losses
    win_rate = (wins / battles) if battles else None

    rally_wins = bool(forecast) and forecast.get("winner") == "ATTACKER"
    solo_feeds = (defending_m is not None
                  and defending_m > SOLO_FEED_RATIO * MARCH_MILLIONS
                  and not rally_wins)

    score = 0.0
    if action == "rally" and rally_wins:
        score += 60 - (exp_loss if exp_loss is not None else 40) * 0.4
        reasons.append(f"counter_ai models a coordinated rally WIN "
                       f"(~{exp_loss:.0f}% of the combined march lost)")
        vector, go = "coordinated_rally", "GO (rally)"
    elif rally_wins:
        score += 45
        reasons.append("counter_ai: a coordinated rally can win the engagement")
        vector, go = "coordinated_rally", "GO (rally)"
    elif defending_m is None:
        score += 18
        reasons.append("no scouted troop count / buffs in DB — counter_ai cannot green-light "
                       "a hit; SCOUT with Watchtower first")
        vector, go = "scout_then_rally", "SCOUT-FIRST"
    else:
        score += 6
        reasons.append(f"counter_ai: no favorable engagement modeled "
                       f"(~{exp_loss:.0f}% loss) — make them come to me")
        vector, go = "none", "NO-GO"

    if solo_feeds:
        ratio = defending_m / MARCH_MILLIONS
        reasons.append(f"{defending_m:,.0f}M defending ≈ {ratio:.0f}x my ~{MARCH_MILLIONS:.0f}M "
                       f"march — a SOLO poke = feeding (pvp_brain §13A); rally-only")
        if rally_wins:
            vector = "coordinated_rally"
        else:
            vector = "skip"
            go = "NO-GO (solo=feeding, no modeled rally win)"

    if win_rate is not None:
        score += (win_rate - 0.5) * 40
        reasons.append(f"head-to-head {wins}-{losses} ({win_rate:.0%} win rate)")
    threat = str(row.get("threat") or "").lower()
    if "i beat" in threat:
        score += 12
        reasons.append("threat tag 'i beat' — favorable history")
    elif "beat" in threat:  # 'beats me'
        score -= 16
        reasons.append("threat tag 'beats me' — engage ONLY via a coordinated rally, never solo")
        if go == "SCOUT-FIRST":
            go = "SCOUT-FIRST (rally only)"

    attackable = vector not in ("skip", "none")
    return {"trade_score": round(score, 1), "attackable": attackable,
            "vector": vector, "go_no_go": go, "reasons": reasons}


def _outcome(decision):
    """The compact expected-outcome view carried alongside each ranked target."""
    return {
        "action": decision.get("action"),
        "lead_type": decision.get("lead_type"),
        "counter_lead": decision.get("counter_lead"),
        "confidence": decision.get("confidence"),
        "expected_loss_pct": decision.get("expected_loss_pct"),
        "forecast": decision.get("forecast"),
        "sim_used": decision.get("sim_used"),
        "reasoning": decision.get("reasoning"),
    }


def pick_targets(mode="open_map", include_unattackable=True):
    """Rank ATTACKABLE enemies by favorable trade.

    For each row in `enemies`: build a counter_ai OFFENSE state, run counter_ai.decide,
    then score it — a modeled rally win scores highest, a favorable head-to-head record
    and an 'i beat' threat tag lift it, a 'beats me' tag and a whale/feeding matchup sink
    it. Whales I'd only feed are marked vector='skip'/'none' (not attackable) unless a
    coordinated rally is modeled to win.

    Returns a list (attackable first, then by trade_score desc). Each item:
      name, alliance, record, threat, max_troops, coords,
      trade_score, attackable, vector, go_no_go, reasons,
      expected_outcome (action / lead / loss% / forecast / sim_used / reasoning).
    """
    out = []
    for row in load_enemies():
        decision = counter_ai.decide(enemy_state(row, mode=mode), use_llm=False)
        assessment = _assess(row, decision)
        out.append({
            "name": row.get("name"),
            "alliance": row.get("alliance"),
            "record": f"{int(row.get('my_wins') or 0)}-{int(row.get('my_losses') or 0)}",
            "threat": row.get("threat"),
            "max_troops": row.get("max_troops"),
            "coords": row.get("coords"),
            **assessment,
            "expected_outcome": _outcome(decision),
        })
    out.sort(key=lambda t: (t["attackable"], t["trade_score"]), reverse=True)
    if not include_unattackable:
        out = [t for t in out if t["attackable"]]
    return out


# --------------------------------------------------------------------------- #
# Per-target plan                                                             #
# --------------------------------------------------------------------------- #
def _looks_like_state(d):
    return isinstance(d, dict) and isinstance(d.get("target"), dict)


def _looks_like_raw_target(d):
    return isinstance(d, dict) and any(
        k in d for k in ("defending_millions", "lead_type", "troops")) and "name" not in d


def _resolve(target):
    """Coerce a target argument into (row_or_None, counter_ai_state). Accepts:
      * an enemy name (str)                       -> DB lookup
      * a pick_targets item / enemy row (dict w/ 'name') -> DB lookup, enriched by its fields
      * a counter_ai state (dict w/ 'target')     -> used as-is
      * a raw target dict (defending_millions/lead_type/troops) -> wrapped into a state
    """
    if isinstance(target, str):
        row = find_enemy(target) or {"name": target}
        return row, enemy_state(row)
    if _looks_like_state(target):
        return None, target
    if _looks_like_raw_target(target):
        return None, {"mode": target.get("mode", "open_map"),
                      "opponent": target.get("opponent", {}), "target": target}
    if isinstance(target, dict) and target.get("name"):
        row = find_enemy(target["name"])
        if row is None:
            row = {k: target.get(k) for k in ENEMY_COLS if k in target}
            row["name"] = target["name"]
        return row, enemy_state(row)
    raise ValueError(f"unrecognised target: {target!r}")


def _build_tap_plan(vector, coords=None):
    """The gem-safe launch sequence as structured steps (pure — sends nothing).
    target tile -> Attack/Rally -> troop preset -> March."""
    is_rally = vector in ("coordinated_rally", "scout_then_rally", "rally")
    action_btn = "Rally" if is_rally else "Attack"
    where = f"at {coords}" if coords else "on the world map (must already be on screen)"
    return [
        {"n": 1, "action": "tap_tile", "locate": "coords" if coords else "on_screen",
         "desc": f"Tap the target city/tile {where} to open its action menu"},
        {"n": 2, "action": "tap_button", "locate": f"ocr:{action_btn.lower()}", "allow": action_btn.lower(),
         "desc": f"Tap '{action_btn}' in the tile menu"},
        {"n": 3, "action": "tap_preset", "locate": "ocr:preset",
         "desc": "Tap the saved troop PRESET (auto-fills generals + a capped troop count; no gems)"},
        {"n": 4, "action": "tap_march", "locate": "ocr:march", "fallback_xy": MARCH_XY, "allow": "march",
         "desc": "Tap 'March' to launch — sends only owned troops (no gem / speed / instant spend)"},
    ]


def plan_attack(target, mode="open_map"):
    """Full attack plan for one target via counter_ai.decide (the target as the state).

    Returns a dict:
      opponent, situation, vector, lead_type (the counter lead), go_no_go,
      solo_vs_rally (the vector rationale), layering + buffs_to_pop (doctrine),
      launch_sequence (the dry-run tap plan, NOT sent),
      decision (the full counter_ai output: ranked_plans, forecast, doctrine, sim_used…).
    """
    row, state = _resolve(target)
    decision = counter_ai.decide(state, use_llm=False)
    assessment = _assess(row, decision)
    counter_lead = decision.get("counter_lead") or counter_ai.COUNTER_LEAD.get(
        counter_ai._troop_type((state.get("target") or {}).get("lead_type")), "GROUND")

    if assessment["vector"] == "coordinated_rally":
        solo_vs_rally = ("COORDINATED RALLY — the alliance combines into one hit; chain winning "
                         "rallies faster than they heal to overflow their hospital → permanent kills.")
    elif assessment["vector"] == "scout_then_rally":
        solo_vs_rally = ("SCOUT then RALLY — no scouted numbers yet; a solo march is a fraction of "
                         "my army with weaker marching buffs, so plan for an alliance rally.")
    elif assessment["vector"] == "skip":
        solo_vs_rally = ("SKIP (solo) — this is a whale; a solo poke feeds it. Only a modeled, "
                         "hospital-overflowing rally train is worth it.")
    else:
        solo_vs_rally = "NO-GO — make them come to me (defense is cheaper; attacker losses are permanent)."

    return {
        "opponent": state.get("opponent") or {"name": (row or {}).get("name")},
        "situation": decision.get("situation"),
        "vector": assessment["vector"],
        "lead_type": counter_lead,
        "go_no_go": assessment["go_no_go"],
        "trade_score": assessment["trade_score"],
        "solo_vs_rally": solo_vs_rally,
        "layering": ATTACK_DOCTRINE["lead_priority"],
        "buffs_to_pop": ATTACK_DOCTRINE["buffs_to_pop"],
        "reasons": assessment["reasons"],
        "launch_sequence": _build_tap_plan(assessment["vector"], (row or {}).get("coords")),
        "decision": decision,
    }


# --------------------------------------------------------------------------- #
# Gem-safe execution (config-gated, dry-run by default)                       #
# --------------------------------------------------------------------------- #
class _AbortSpend(Exception):
    """Raised to bail out of a real launch the instant a spend/gem control is seen."""


def _forbidden(label):
    low = str(label).lower()
    return any(tok in low for tok in FORBIDDEN_TAP_TOKENS)


def _allowed(label):
    low = str(label).lower()
    return any(tok in low for tok in ALLOWED_BUTTON_TOKENS)


def execute_attack(target, dry_run=True, logger=print):
    """Launch (or, by default, only LOG) the gem-safe attack tap sequence for a target.

    DEFAULT dry_run=True → logs the intended taps and sends NOTHING. A real launch
    requires dry_run=False AND bot_config.json advanced.auto_attack == true AND a
    non-NO-GO counter_ai call. Even then it taps ONLY target → Attack/Rally → preset →
    March, guards every tap against Buy/Confirm-purchase/Instant/gem/Quit, and aborts
    (safe-back, never Confirm) on any purchase/gem popup.

    Returns {sent, reason, vector, go_no_go, steps, decision}.
    """
    row, state = _resolve(target)
    decision = counter_ai.decide(state, use_llm=False)
    assessment = _assess(row, decision)
    vector = assessment["vector"]
    coords = (row or {}).get("coords")
    steps = _build_tap_plan(vector, coords)
    opp = state.get("opponent") or {}
    label = f"[{opp.get('alliance', '?')}]{opp.get('name', '?')}"
    cfg_on = auto_attack_enabled()

    logger(f"[attack_planner] EXECUTE {label}  vector={vector}  go_no_go={assessment['go_no_go']}")
    logger(f"[attack_planner]   would send = {'YES' if (not dry_run and cfg_on) else 'NO'}  "
           f"(dry_run={dry_run}, auto_attack={cfg_on})")
    for s in steps:
        logger(f"[attack_planner]   {s['n']}. {s['action']:10s} : {s['desc']}")
    logger("[attack_planner]   SAFETY: never taps Buy / Confirm-purchase / Instant / gem / Quit; "
           "sends only owned troops (preset-capped).")

    if dry_run:
        return {"sent": False, "reason": "dry_run (default) — logged intended taps only, nothing sent",
                "vector": vector, "go_no_go": assessment["go_no_go"], "steps": steps, "decision": decision}
    if not cfg_on:
        return {"sent": False, "reason": "bot_config advanced.auto_attack is not true — refusing to launch",
                "vector": vector, "go_no_go": assessment["go_no_go"], "steps": steps, "decision": decision}
    if str(assessment["go_no_go"]).startswith("NO-GO"):
        return {"sent": False, "reason": f"counter_ai go/no-go = {assessment['go_no_go']} — refusing to feed",
                "vector": vector, "go_no_go": assessment["go_no_go"], "steps": steps, "decision": decision}

    return _do_real_taps(steps, coords, logger,
                         base={"vector": vector, "go_no_go": assessment["go_no_go"],
                               "steps": steps, "decision": decision})


def _do_real_taps(steps, coords, logger, base):
    """The ONLY code path that touches the emulator. Reached only with dry_run=False +
    auto_attack + a GO call. Locates each button by OCR text, guards it, taps, and
    aborts on any spend/gem popup. The ADB/vision stack is imported lazily so --plan
    never needs cv2/adb."""
    import subprocess
    import time

    import live_map
    import ocr_read
    import shared_capture

    def cap():
        return shared_capture.grab_wait(DEV, timeout=6)

    def find(img, needle):
        if img is None:
            return None
        for txt, (cx, cy), conf in ocr_read.read_all(img):
            if conf >= 0.5 and needle in str(txt).lower():
                return (cx, cy, str(txt))
        return None

    def guarded_tap(x, y, label):
        if _forbidden(label):
            raise _AbortSpend(f"refused to tap forbidden control '{label}'")
        subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", str(int(x)), str(int(y))])
        time.sleep(1.6)

    def bail_if_spend(img, where):
        if img is not None and live_map.has_popup(img):
            live_map.safe_back(settle=1.0)  # Back = Cancel; never taps Confirm/Buy
            raise _AbortSpend(f"purchase/gem/confirm popup at {where} — cancelled, nothing sent")

    try:
        img = cap()
        bail_if_spend(img, "start")
        if coords:
            logger(f"[attack_planner]   (real) tile at {coords} must be centered on the map first")
        # 2. Attack / Rally
        btn = find(img, "rally") or find(img, "attack")
        if not btn:
            raise _AbortSpend("no Attack/Rally button visible — target tile not selected; nothing sent")
        if not _allowed(btn[2]):
            raise _AbortSpend(f"button '{btn[2]}' not an allowed action — nothing sent")
        guarded_tap(btn[0], btn[1], btn[2])
        # 3. troop preset (best-effort; the setup screen usually auto-fills the saved preset)
        img = cap()
        bail_if_spend(img, "march-setup")
        preset = find(img, "preset")
        if preset and _allowed(preset[2]):
            guarded_tap(preset[0], preset[1], preset[2])
            img = cap()
            bail_if_spend(img, "after-preset")
        # 4. March
        march = find(img, "march")
        mx, my = (march[0], march[1]) if march else MARCH_XY
        mlabel = march[2] if march else "march"
        if not _allowed(mlabel):
            raise _AbortSpend(f"march control '{mlabel}' not allowed — nothing sent")
        guarded_tap(mx, my, mlabel)
        img = cap()
        bail_if_spend(img, "post-march")  # a gem prompt here = insufficient troops/stamina → cancelled
    except _AbortSpend as exc:
        logger(f"[attack_planner]   ABORT: {exc}")
        return {**base, "sent": False, "reason": str(exc)}

    logger("[attack_planner]   launched (owned troops only; no spend).")
    return {**base, "sent": True, "reason": "march/rally launched with the saved preset (no gems spent)"}


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def _fmt_forecast(fc):
    if not fc:
        return "no scout numbers → scout-gated"
    al = fc.get("attacker_loss_pct")
    dl = fc.get("defender_loss_pct")
    return (f"{fc.get('method', 'rule')}: winner={fc.get('winner')} "
            f"my-loss={al if al is not None else '?'}% their-loss={dl if dl is not None else '?'}%"
            + (f" in {fc['rounds']} rounds" if fc.get("rounds") else ""))


def _print_plan(as_json, mode):
    targets = pick_targets(mode=mode)
    if as_json:
        plans = [plan_attack(t, mode=mode) for t in targets]
        print(json.dumps({"mode": mode, "sim_available": counter_ai._sim_js_dir() is not None,
                          "auto_attack": auto_attack_enabled(), "targets": targets, "plans": plans},
                         indent=2, default=str))
        return

    sim = counter_ai._sim_js_dir()
    print("=" * 96)
    print("ATTACK PLANNER — favorable-trade target ranking (DRY-RUN, no emulator)")
    print(f"mode={mode}   simulator={'AVAILABLE' if sim else 'NOT FOUND (analytic fallback)'}   "
          f"node={'ok' if counter_ai._node() else 'missing'}   auto_attack={auto_attack_enabled()}")
    print("SAFETY: analysis only here; execute_attack defaults to dry_run and never taps "
          "Buy/Confirm/Instant/gem/Quit.")
    print("=" * 96)
    if not targets:
        print("no rows in the enemies table.")
        return

    for i, t in enumerate(targets, 1):
        flag = "ATTACKABLE" if t["attackable"] else "skip"
        print(f"\n#{i}  [{t['alliance'] or '?'}]{t['name']}   score={t['trade_score']:+.1f}  "
              f"[{flag}]  vector={t['vector']}  {t['go_no_go']}")
        troops = f"{t['max_troops']:,}" if t.get("max_troops") else "unscouted"
        print(f"    record {t['record']}  threat={t['threat']!r}  defending_troops={troops}  "
              f"coords={t['coords'] or '-'}")
        eo = t["expected_outcome"]
        print(f"    counter_ai: {str(eo['action']).upper()}"
              + (f" leading {eo['lead_type']}" if eo.get("lead_type") else "")
              + f"  (conf {eo['confidence']}, "
              + (f"exp loss {eo['expected_loss_pct']:.0f}%" if eo.get("expected_loss_pct") is not None
                 else "no loss est")
              + f", {'sim' if eo.get('sim_used') else 'rules'})")
        print(f"    forecast: {_fmt_forecast(eo.get('forecast'))}")
        for r in t["reasons"]:
            print(f"      - {r}")

    print("\n" + "-" * 96)
    print("FULL PLANS (plan_attack) + gem-safe launch sequence (dry-run, sends nothing):")
    for t in targets:
        p = plan_attack(t, mode=mode)
        opp = p["opponent"]
        print(f"\n>>> [{opp.get('alliance', '?')}]{opp.get('name', '?')}  →  {p['go_no_go']}  "
              f"(vector={p['vector']}, lead {p['lead_type']})")
        print(f"    {p['solo_vs_rally']}")
        print(f"    layering: {p['layering']}")
        print("    buffs to pop:")
        for b in p["buffs_to_pop"]:
            print(f"      - {b}")
        print("    launch sequence (DRY-RUN):")
        execute_attack(t, dry_run=True,
                       logger=lambda m: print("      " + m.replace("[attack_planner] ", "")))


def _print_stats():
    rows = load_enemies()
    wins = sum(int(r.get("my_wins") or 0) for r in rows)
    losses = sum(int(r.get("my_losses") or 0) for r in rows)
    scouted = sum(1 for r in rows if r.get("max_troops"))
    beat = [r["name"] for r in rows if "i beat" in str(r.get("threat") or "").lower()]
    beats_me = [r["name"] for r in rows if "beats me" in str(r.get("threat") or "").lower()]
    print("=" * 72)
    print("ATTACK PLANNER — stats")
    print("=" * 72)
    print(f"enemies tracked      : {len(rows)}  (scouted troop counts: {scouted})")
    print(f"aggregate record     : {wins}-{losses}")
    print(f"i beat               : {', '.join(beat) or '-'}")
    print(f"beats me             : {', '.join(beats_me) or '-'}")
    print(f"my march / rally cap  : ~{MARCH_MILLIONS:.0f}M / ~{RALLY_CAP_MILLIONS:.0f}M troops")
    print(f"solo-feed threshold  : > {SOLO_FEED_RATIO:.0f}x my march = feeding (rally-only)")
    print(f"simulator            : {'AVAILABLE' if counter_ai._sim_js_dir() else 'NOT FOUND (analytic fallback)'}")
    print(f"node                 : {'ok' if counter_ai._node() else 'missing'}")
    print(f"auto_attack (config) : {auto_attack_enabled()}  (real launches gated on this + dry_run=False)")
    print(f"config file          : {_config_path()}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="ATTACK pillar — rank favorable-trade targets and "
                                             "plan gem-safe marches/rallies (read-only by default).")
    ap.add_argument("--plan", action="store_true",
                    help="rank targets + print full plans (dry-run: DB + counter_ai, NO emulator)")
    ap.add_argument("--stats", action="store_true", help="print target/record/safety stats")
    ap.add_argument("--mode", default="open_map",
                    help="counter_ai mode: open_map | battlefield | coc | boc | bog | svs")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON (with --plan)")
    args = ap.parse_args(argv)

    if args.stats:
        _print_stats()
        return 0
    if args.plan:
        _print_plan(args.json, args.mode)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
