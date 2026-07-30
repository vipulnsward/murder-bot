import os
import re
import secrets
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

BASE_DIR = Path(__file__).resolve().parent
DB_DSN = os.environ.get("DB_DSN", "dbname=murderbot host=localhost")
COOKIE_NAME = "neo_session"
SESSION_MAX_AGE = 7 * 24 * 60 * 60
OUR_TAG = "NFG"
OUR_NAME_HINT = "tlatoani"
TOTAL_KEYS = (
    "troop_amount",
    "survived",
    "wounded",
    "killed",
    "deserter",
    "lost_power",
    "holy_palace_troop_soul",
)
TYPE_ORDER = {"ground": 0, "ranged": 1, "mounted": 2, "siege": 3}
ROMAN_VALUES = [
    ("XVII", 17), ("XVI", 16), ("XIV", 14), ("XIII", 13), ("XII", 12),
    ("XV", 15), ("XI", 11), ("IX", 9), ("VIII", 8), ("VII", 7),
    ("VI", 6), ("IV", 4), ("III", 3), ("II", 2), ("X", 10), ("V", 5), ("I", 1),
]


def persisted_secret(env_name: str, filename: str, factory) -> bytes:
    if value := os.environ.get(env_name):
        return value.encode()
    path = BASE_DIR / filename
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "wb") as file:
            file.write(factory())
    os.chmod(path, 0o600)
    return path.read_bytes().strip()


signer = TimestampSigner(
    persisted_secret("NEO_SECRET", ".secret", lambda: secrets.token_urlsafe(48).encode()),
    salt="neo-session",
)
router = APIRouter()


@contextmanager
def database():
    connection = psycopg2.connect(DB_DSN)
    try:
        yield connection
    finally:
        connection.close()


def session_user_id(request: Request) -> int | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return int(signer.unsign(token, max_age=SESSION_MAX_AGE).decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None


def current_user(request: Request) -> int:
    user_id = session_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM app_users WHERE id = %s", (user_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def to_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_alliance(name: str | None):
    if not name:
        return None, None
    match = re.match(r"^\s*\[?\s*([A-Za-z0-9]{2,8})\s*[\]J]\s*(.*)$", name)
    if match:
        return match.group(1), match.group(2).strip() or None
    return None, name.strip() or None


def is_us(name: str | None) -> bool:
    if not name:
        return False
    tag, _ = parse_alliance(name)
    return tag == OUR_TAG or OUR_NAME_HINT in name.lower()


def classify(title: str | None) -> tuple[str, str]:
    lower = (title or "").lower()
    if "defen" in lower:
        return "defense", "Defense"
    if lower.startswith("attack"):
        return "attack", "PvP Attack"
    if re.match(r"^lv\.?\s*\d+", lower):
        return "monster", "Monster Hunt"
    return "other", "Battle"


def resolve_opponent(participants, attacker_col, defender_col, title, kind):
    roled = [
        participant
        for participant in participants or []
        if isinstance(participant, dict) and participant.get("role")
    ]
    if roled:
        opponent = next(
            (participant for participant in roled if not is_us(participant.get("name"))),
            None,
        )
        if opponent is not None and opponent.get("name"):
            tag, name = parse_alliance(opponent["name"])
            return {"name": name or opponent["name"], "tag": tag, "role": opponent.get("role")}
        return {"name": None, "tag": None, "role": None}
    if kind == "monster":
        name = re.sub(r"^Lv\.?\s*\d+\s*", "", title or "").strip()
        return {"name": name or attacker_col or "Monster", "tag": "PvE", "role": "monster"}
    candidate = next(
        (column for column in (defender_col, attacker_col) if column and not is_us(column)),
        None,
    )
    if candidate:
        tag, name = parse_alliance(candidate)
        if tag:
            return {"name": name or candidate, "tag": tag, "role": None}
    return {"name": None, "tag": None, "role": None}


def our_role_for(kind, opponent) -> str:
    opponent_role = (opponent or {}).get("role")
    if opponent_role == "attacker":
        return "defender"
    if opponent_role == "defender":
        return "attacker"
    if kind == "defense":
        return "defender"
    return "attacker"


def reinforcement_totals(reinforcements):
    if not isinstance(reinforcements, dict):
        return None
    totals = {"attacker": {}, "defender": {}}
    seen = False
    for key in TOTAL_KEYS:
        pair = reinforcements.get(key)
        if not isinstance(pair, dict):
            continue
        for side in ("attacker", "defender"):
            value = to_int(pair.get(side))
            totals[side][key] = value
            if value is not None:
                seen = True
    return totals if seen else None


def battle_side_totals(side_list):
    summary = {
        "committed": 0,
        "survived": 0,
        "wounded": 0,
        "killed": 0,
        "deserter": 0,
        "enemy_killed": 0,
    }
    for participant in side_list or []:
        for troop in (participant.get("troops") or {}).values():
            summary["survived"] += to_int(troop.get("survived")) or 0
            summary["wounded"] += to_int(troop.get("wounded")) or 0
            summary["killed"] += to_int(troop.get("killed")) or 0
            summary["deserter"] += to_int(troop.get("deserter")) or 0
            summary["enemy_killed"] += to_int(troop.get("killing")) or 0
    summary["committed"] = (
        summary["survived"] + summary["wounded"] + summary["killed"] + summary["deserter"]
    )
    return summary


def battle_totals(battle_details):
    if not isinstance(battle_details, dict):
        return None
    return {
        "attacker": battle_side_totals(battle_details.get("attacker")),
        "defender": battle_side_totals(battle_details.get("defender")),
    }


def roman_to_int(roman: str) -> int:
    for token, value in ROMAN_VALUES:
        if roman == token:
            return value
    return 0


def tier_rows(side_list):
    rows = []
    for participant in side_list or []:
        name = participant.get("name")
        generals = participant.get("generals") or []
        for label, troop in (participant.get("troops") or {}).items():
            branch, _, tier = label.partition(":")
            rows.append(
                {
                    "owner": name,
                    "branch": branch,
                    "tier": tier,
                    "tier_num": roman_to_int(tier),
                    "generals": generals,
                    "killing": to_int(troop.get("killing")),
                    "survived": to_int(troop.get("survived")),
                    "wounded": to_int(troop.get("wounded")),
                    "killed": to_int(troop.get("killed")),
                    "deserter": to_int(troop.get("deserter")),
                }
            )
    rows.sort(key=lambda row: (TYPE_ORDER.get(row["branch"], 9), -row["tier_num"], row["tier"]))
    return rows


def _has_general(general) -> bool:
    if not isinstance(general, dict):
        return False
    return any(isinstance(side, dict) and side.get("name") for side in general.values())


def summarize(row) -> dict:
    (
        rid,
        title,
        outcome,
        ts,
        coords,
        defender,
        attacker,
        killed,
        wounded,
        lost_power,
        destroyed_traps,
        deserter,
        holy_palace,
        subcity_kills,
        participants,
        buffs,
        reinforcements,
        battle_details,
        main_general,
        assistant_general,
    ) = row
    kind, kind_label = classify(title)
    opponent = resolve_opponent(participants, attacker, defender, title, kind)
    reinf = reinforcement_totals(reinforcements)
    bd_totals = battle_totals(battle_details)
    return {
        "rid": rid,
        "title": title,
        "outcome": outcome or "unknown",
        "ts": ts,
        "coords": coords,
        "kind": kind,
        "kind_label": kind_label,
        "opponent": opponent,
        "our_role": our_role_for(kind, opponent),
        "summary": {
            "killed": to_int(killed),
            "wounded": to_int(wounded),
            "lost_power": to_int(lost_power),
            "deserter": to_int(deserter),
            "holy_palace": to_int(holy_palace),
            "subcity_kills": to_int(subcity_kills),
            "destroyed_traps": to_int(destroyed_traps),
        },
        "reinf": reinf,
        "bd_totals": bd_totals,
        "flags": {
            "battle_details": bool(bd_totals),
            "buffs": isinstance(buffs, dict) and bool(buffs),
            "generals": _has_general(main_general) or _has_general(assistant_general),
            "reinforcements": bool(reinf),
        },
    }


LIST_COLUMNS = """
    rid, title, outcome, ts, coords, defender, attacker,
    killed, wounded, lost_power, destroyed_traps, deserter, holy_palace, subcity_kills,
    participants, buffs, reinforcements, battle_details, main_general, assistant_general
"""


@router.get("/api/reports")
def api_reports(_user_id: int = Depends(current_user)):
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {LIST_COLUMNS}
                FROM report_extracts
                ORDER BY ts DESC NULLS LAST, updated_at DESC NULLS LAST
                """
            )
            rows = cursor.fetchall()
    return [summarize(row) for row in rows]


@router.get("/api/reports/{rid}")
def api_report(rid: str, _user_id: int = Depends(current_user)):
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {LIST_COLUMNS}, stats, subordinate_city, raw_text
                FROM report_extracts
                WHERE rid = %s
                """,
                (rid,),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    stats, subordinate_city, raw_text = row[-3], row[-2], row[-1]
    buffs = row[15]
    reinforcements = row[16]
    battle_details = row[17]
    main_general = row[18]
    assistant_general = row[19]
    detail = summarize(row[:20])
    detail.update(
        {
            "buffs": buffs if isinstance(buffs, dict) else {},
            "battle_details": {
                "attacker": tier_rows((battle_details or {}).get("attacker"))
                if isinstance(battle_details, dict)
                else [],
                "defender": tier_rows((battle_details or {}).get("defender"))
                if isinstance(battle_details, dict)
                else [],
            },
            "main_general": main_general if isinstance(main_general, dict) else {},
            "assistant_general": assistant_general if isinstance(assistant_general, dict) else {},
            "reinforcements_raw": reinforcements if isinstance(reinforcements, dict) else {},
            "subordinate_city": subordinate_city if isinstance(subordinate_city, dict) else {},
            "stats": stats if isinstance(stats, dict) else {},
            "raw_text": raw_text or "",
        }
    )
    return detail


REPORTS_PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Murder Bot — Battle Reports</title>
<style>
:root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }
main { width: min(1100px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }
a { color: #58a6ff; text-decoration: none; }
h1, h2, h3, h4 { margin: 0; }
header.top { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.sub { color: #8b949e; font-size: .9rem; margin-top: .25rem; }
.tabs { display: flex; gap: .5rem; flex-wrap: wrap; margin: 1rem 0 1.5rem; }
.tab { padding: .5rem .95rem; color: #c9d1d9; background: #161b22; border: 1px solid #30363d; border-radius: 999px; cursor: pointer; font-weight: 600; font-size: .9rem; }
.tab.active { color: #fff; background: #1f6feb; border-color: #1f6feb; }
.tab .count { margin-left: .35rem; color: #8b949e; font-weight: 500; }
.tab.active .count { color: #cfe1ff; }
.cards { display: grid; gap: 1rem; }
.card { background: #161b22; border: 1px solid #30363d; border-left-width: 4px; border-radius: 12px; padding: 1.1rem 1.2rem; }
.card.win { border-left-color: #3fb950; }
.card.loss { border-left-color: #f85149; }
.card.unknown { border-left-color: #8b949e; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: .75rem; flex-wrap: wrap; }
.badges { display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
.badge { display: inline-block; padding: .18rem .55rem; border-radius: 999px; font-size: .74rem; font-weight: 700; letter-spacing: .02em; text-transform: uppercase; }
.badge.win { color: #3fb950; background: #12331d; }
.badge.loss { color: #ff7b72; background: #3d1518; }
.badge.unknown { color: #c9d1d9; background: #21262d; }
.badge.kind { color: #d2a8ff; background: #221a38; text-transform: none; letter-spacing: 0; font-weight: 600; }
.opp { margin: .55rem 0 .2rem; font-size: 1.15rem; font-weight: 700; overflow-wrap: anywhere; }
.tag { display: inline-block; margin-right: .45rem; padding: .1rem .45rem; border-radius: 6px; font-size: .8rem; font-weight: 700; color: #ffa657; background: #2b1d10; }
.tag.pve { color: #79c0ff; background: #10233b; }
.meta { color: #8b949e; font-size: .83rem; }
.totals { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; margin-top: .9rem; }
.totals.solo { grid-template-columns: 1fr; }
.side { padding: .7rem .8rem; background: #0d1117; border: 1px solid #21262d; border-radius: 9px; }
.side h4 { margin: 0 0 .45rem; font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; color: #8b949e; overflow-wrap: anywhere; }
.side.us h4 { color: #58a6ff; }
.side.them h4 { color: #ffa657; }
.stat-line { display: flex; justify-content: space-between; gap: .75rem; padding: .12rem 0; font-size: .88rem; }
.stat-line span { color: #8b949e; }
.stat-line b { font-variant-numeric: tabular-nums; overflow-wrap: anywhere; text-align: right; }
.stat-line b.pos { color: #3fb950; }
.stat-line b.neg { color: #ff7b72; }
.chips { display: flex; gap: .4rem; flex-wrap: wrap; margin-top: .85rem; }
.chip { font-size: .72rem; color: #8b949e; background: #21262d; border-radius: 6px; padding: .18rem .5rem; }
.expand { margin-top: .9rem; }
.expand-btn { width: 100%; padding: .55rem; color: #c9d1d9; background: #21262d; border: 1px solid #30363d; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: .85rem; }
.expand-btn:hover { background: #2a313a; }
.detail { margin-top: .9rem; display: grid; gap: 1.1rem; }
.detail h3 { font-size: .82rem; text-transform: uppercase; letter-spacing: .05em; color: #8b949e; margin-bottom: .5rem; }
.table-wrap { overflow-x: auto; border: 1px solid #21262d; border-radius: 9px; }
table { width: 100%; border-collapse: collapse; font-size: .84rem; }
th, td { padding: .5rem .6rem; border-bottom: 1px solid #21262d; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
thead th { color: #8b949e; font-weight: 600; text-transform: uppercase; font-size: .72rem; letter-spacing: .04em; }
tbody tr:last-child td { border-bottom: 0; }
.branch-ground { color: #3fb950; } .branch-ranged { color: #d2a8ff; }
.branch-mounted { color: #ffa657; } .branch-siege { color: #79c0ff; }
.gens { color: #8b949e; font-size: .78rem; white-space: normal; }
.gen-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; }
.raw { max-height: 15rem; overflow: auto; padding: .8rem; white-space: pre-wrap; word-break: break-word; background: #0d1117; border: 1px solid #21262d; border-radius: 8px; font-size: .8rem; color: #8b949e; }
.empty, .loading { padding: 3rem 1rem; text-align: center; color: #8b949e; }
@media (max-width: 620px) {
  main { padding: 1.25rem 0 3rem; }
  .totals { grid-template-columns: 1fr; }
  .gen-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<main>
<header class="top">
  <div>
    <h1>Battle Reports</h1>
    <div class="sub">Murder Bot — NeoIsTlatoani (NFG) · newest first</div>
  </div>
  <a href="/">&larr; Dashboard</a>
</header>

<div class="tabs" id="tabs">
  <button class="tab active" data-filter="all">All <span class="count" data-count="all"></span></button>
  <button class="tab" data-filter="attack">Attacks <span class="count" data-count="attack"></span></button>
  <button class="tab" data-filter="defense">Defenses <span class="count" data-count="defense"></span></button>
  <button class="tab" data-filter="loss">Losses <span class="count" data-count="loss"></span></button>
</div>

<div id="cards" class="cards"><div class="loading">Loading reports…</div></div>
</main>
<script>
const ATTACK_KINDS = new Set(["attack", "monster"]);
let REPORTS = [];
let ACTIVE = "all";
const OPEN = new Set();

function fmt(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toLocaleString("en-US");
}
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function romanToNum(tier) {
  const map = {I:1,II:2,III:3,IV:4,V:5,VI:6,VII:7,VIII:8,IX:9,X:10,XI:11,XII:12,XIII:13,XIV:14,XV:15,XVI:16,XVII:17};
  return map[tier] || tier;
}
function tierLabel(branch, tier) {
  const name = branch ? branch.charAt(0).toUpperCase() + branch.slice(1) : "?";
  const arabic = tier && tier !== "?" ? "T" + romanToNum(tier) : "T?";
  return name + " · " + arabic;
}
function matchesFilter(report, filter) {
  if (filter === "all") return true;
  if (filter === "loss") return report.outcome === "loss";
  if (filter === "attack") return ATTACK_KINDS.has(report.kind);
  if (filter === "defense") return report.kind === "defense";
  return true;
}
function oppLabel(report) {
  const opponent = report.opponent || {};
  return opponent.name || "Enemy";
}
function statLine(label, value, tone) {
  const line = el("div", "stat-line");
  line.append(el("span", null, label));
  line.append(el("b", tone ? tone : null, fmt(value)));
  return line;
}

function totalsBlock(report) {
  const wrapper = el("div", "totals");
  const usIsAttacker = report.our_role !== "defender";
  const usKey = usIsAttacker ? "attacker" : "defender";
  const themKey = usIsAttacker ? "defender" : "attacker";

  if (report.reinf) {
    for (const [key, roleClass, heading] of [[usKey, "us", "You"], [themKey, "them", oppLabel(report)]]) {
      const side = report.reinf[key] || {};
      const box = el("div", "side " + roleClass);
      box.append(el("h4", null, heading));
      box.append(statLine("Troops", side.troop_amount));
      box.append(statLine("Survived", side.survived, "pos"));
      box.append(statLine("Wounded", side.wounded));
      box.append(statLine("Lost power", side.lost_power, "neg"));
      wrapper.append(box);
    }
    return wrapper;
  }
  if (report.bd_totals) {
    for (const [key, roleClass, heading] of [[usKey, "us", "You"], [themKey, "them", oppLabel(report)]]) {
      const side = report.bd_totals[key] || {};
      const box = el("div", "side " + roleClass);
      box.append(el("h4", null, heading));
      box.append(statLine("Committed", side.committed));
      box.append(statLine("Survived", side.survived, "pos"));
      box.append(statLine("Wounded", side.wounded));
      box.append(statLine("Enemy killed", side.enemy_killed, "pos"));
      wrapper.append(box);
    }
    return wrapper;
  }
  wrapper.classList.add("solo");
  const summary = report.summary || {};
  const box = el("div", "side us");
  box.append(el("h4", null, "Your result"));
  box.append(statLine("Killed", summary.killed, "neg"));
  box.append(statLine("Wounded", summary.wounded));
  box.append(statLine("Lost power", summary.lost_power, "neg"));
  box.append(statLine("Holy Palace souls", summary.holy_palace, "pos"));
  wrapper.append(box);
  return wrapper;
}

function card(report) {
  const root = el("div", "card " + report.outcome);
  root.dataset.rid = report.rid;

  const head = el("div", "card-head");
  const badges = el("div", "badges");
  const outcomeText = report.outcome === "win" ? "Victory" : report.outcome === "loss" ? "Defeat" : "Unknown";
  badges.append(el("span", "badge " + report.outcome, outcomeText));
  badges.append(el("span", "badge kind", report.kind_label));
  head.append(badges);
  head.append(el("span", "meta", report.ts || ""));
  root.append(head);

  const opponent = report.opponent || {};
  const opp = el("div", "opp");
  if (opponent.tag) {
    opp.append(el("span", "tag" + (opponent.tag === "PvE" ? " pve" : ""), opponent.tag));
  }
  opp.append(document.createTextNode(opponent.name || "Unknown target"));
  root.append(opp);

  const metaBits = [];
  if (report.title) metaBits.push(report.title);
  if (report.coords) metaBits.push(report.coords.replace(/\\s+/g, " "));
  root.append(el("div", "meta", metaBits.join("  ·  ")));

  root.append(totalsBlock(report));

  const flags = report.flags || {};
  const chips = el("div", "chips");
  if (flags.battle_details) chips.append(el("span", "chip", "Per-tier battle details"));
  if (flags.buffs) chips.append(el("span", "chip", "Troop buffs"));
  if (flags.generals) chips.append(el("span", "chip", "Generals"));
  if (chips.children.length) root.append(chips);

  if (flags.battle_details || flags.buffs || flags.generals) {
    const wrap = el("div", "expand");
    const isOpen = OPEN.has(report.rid);
    const button = el("button", "expand-btn", isOpen ? "Hide details" : "Show battle details");
    const panel = el("div", "detail");
    panel.hidden = !isOpen;
    button.addEventListener("click", async () => {
      if (panel.hidden) {
        OPEN.add(report.rid);
        button.textContent = "Hide details";
        panel.hidden = false;
        if (!panel.dataset.loaded) {
          panel.textContent = "Loading…";
          await fillDetail(panel, report.rid);
          panel.dataset.loaded = "1";
        }
      } else {
        OPEN.delete(report.rid);
        button.textContent = "Show battle details";
        panel.hidden = true;
      }
    });
    wrap.append(button, panel);
    root.append(wrap);
    if (isOpen) {
      panel.textContent = "Loading…";
      fillDetail(panel, report.rid).then(() => (panel.dataset.loaded = "1"));
    }
  }
  return root;
}

async function fillDetail(panel, rid) {
  let data;
  try {
    const response = await fetch("/api/reports/" + encodeURIComponent(rid));
    if (!response.ok) throw new Error("failed");
    data = await response.json();
  } catch (error) {
    panel.textContent = "Could not load details.";
    return;
  }
  panel.textContent = "";

  const buffs = data.buffs || {};
  if (Object.keys(buffs).length) panel.append(buffTable(buffs));

  for (const [side, heading] of [["attacker", "Attacker — per-tier"], ["defender", "Defender — per-tier"]]) {
    const rows = (data.battle_details || {})[side] || [];
    if (rows.length) panel.append(tierTable(heading, rows));
  }

  const gens = generalsSection(data.main_general, data.assistant_general);
  if (gens) panel.append(gens);

  if (data.raw_text) {
    const section = el("div");
    section.append(el("h3", null, "Raw report text"));
    section.append(el("pre", "raw", data.raw_text));
    panel.append(section);
  }
}

function buffTable(buffs) {
  const section = el("div");
  section.append(el("h3", null, "Troop buffs (%)"));
  const wrap = el("div", "table-wrap");
  const table = el("table");
  const thead = el("thead");
  const head = el("tr");
  ["Type", "Atk (you)", "Def (you)", "HP (you)", "Atk (enemy)", "Def (enemy)", "HP (enemy)"].forEach(text => head.append(el("th", null, text)));
  thead.append(head); table.append(thead);
  const body = el("tbody");
  for (const branch of ["ground", "ranged", "mounted", "siege"]) {
    const entry = buffs[branch];
    if (!entry) continue;
    const row = el("tr");
    row.append(el("td", "branch-" + branch, branch.charAt(0).toUpperCase() + branch.slice(1)));
    const us = entry.attacker || {};
    const them = entry.defender || {};
    for (const value of [us.attack, us.defense, us.hp, them.attack, them.defense, them.hp]) {
      row.append(el("td", null, fmt(value)));
    }
    body.append(row);
  }
  table.append(body); wrap.append(table); section.append(wrap);
  return section;
}

function tierTable(heading, rows) {
  const section = el("div");
  section.append(el("h3", null, heading));
  const wrap = el("div", "table-wrap");
  const table = el("table");
  const thead = el("thead");
  const head = el("tr");
  ["Unit", "Killing", "Survived", "Wounded", "Killed", "Deserter"].forEach(text => head.append(el("th", null, text)));
  thead.append(head); table.append(thead);
  const body = el("tbody");
  for (const row of rows) {
    const line = el("tr");
    const unit = el("td");
    unit.append(el("span", "branch-" + row.branch, tierLabel(row.branch, row.tier)));
    if (row.generals && row.generals.length) unit.append(el("div", "gens", row.generals.join(", ")));
    line.append(unit);
    line.append(el("td", null, fmt(row.killing)));
    line.append(el("td", null, fmt(row.survived)));
    line.append(el("td", null, fmt(row.wounded)));
    line.append(el("td", null, fmt(row.killed)));
    line.append(el("td", null, fmt(row.deserter)));
    body.append(line);
  }
  table.append(body); wrap.append(table); section.append(wrap);
  return section;
}

function sideNamed(side) { return side && side.name; }
function generalLine(role, side) {
  const wrapper = el("div");
  const line = el("div", "stat-line");
  line.append(el("span", null, role));
  const parts = [side.name];
  if (side.star_level) parts.push(side.star_level);
  line.append(el("b", null, parts.join(" ")));
  wrapper.append(line);
  const meta = [];
  if (side.level) meta.push("L" + side.level);
  if (side.power) meta.push(fmt(side.power) + " power");
  if (side.status) meta.push(side.status);
  if (meta.length) wrapper.append(el("div", "gens", meta.join(" · ")));
  return wrapper;
}
function generalsSection(main, assistant) {
  main = main || {}; assistant = assistant || {};
  const hasMain = sideNamed(main.attacker) || sideNamed(main.defender);
  const hasAssist = sideNamed(assistant.attacker) || sideNamed(assistant.defender);
  if (!hasMain && !hasAssist) return null;
  const section = el("div");
  section.append(el("h3", null, "Generals"));
  const grid = el("div", "gen-grid");
  for (const [label, side] of [["Attacker", "attacker"], ["Defender", "defender"]]) {
    const box = el("div", "side");
    box.append(el("h4", null, label));
    const mainSide = main[side];
    const assistSide = assistant[side];
    if (sideNamed(mainSide)) box.append(generalLine("Main", mainSide));
    if (sideNamed(assistSide)) box.append(generalLine("Assistant", assistSide));
    if (box.children.length > 1) grid.append(box);
  }
  if (!grid.children.length) return null;
  section.append(grid);
  return section;
}

function updateCounts() {
  for (const filter of ["all", "attack", "defense", "loss"]) {
    const count = REPORTS.filter(report => matchesFilter(report, filter)).length;
    const node = document.querySelector('[data-count="' + filter + '"]');
    if (node) node.textContent = count;
  }
}
function render() {
  const container = document.getElementById("cards");
  container.textContent = "";
  const visible = REPORTS.filter(report => matchesFilter(report, ACTIVE));
  if (!visible.length) {
    container.append(el("div", "empty", "No reports in this view yet."));
    return;
  }
  for (const report of visible) container.append(card(report));
}

document.getElementById("tabs").addEventListener("click", event => {
  const tab = event.target.closest(".tab");
  if (!tab) return;
  ACTIVE = tab.dataset.filter;
  document.querySelectorAll(".tab").forEach(node => node.classList.toggle("active", node === tab));
  render();
});

async function load() {
  const container = document.getElementById("cards");
  try {
    const response = await fetch("/api/reports");
    if (!response.ok) throw new Error("failed");
    REPORTS = await response.json();
  } catch (error) {
    container.textContent = "";
    container.append(el("div", "empty", "Could not load reports."));
    return;
  }
  updateCounts();
  render();
}
load();
</script>
</body>
</html>
"""


@router.get("/reports", response_class=HTMLResponse)
def reports_page(_user_id: int = Depends(current_user)):
    return REPORTS_PAGE
