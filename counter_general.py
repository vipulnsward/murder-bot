import json
import os
import re
import sys

from game_kb import GameKB

TROOP_TYPES = ("GROUND", "MOUNTED", "RANGED", "SIEGE")

GOOD_AGAINST = {
    "MOUNTED": {"GROUND", "SIEGE"},
    "RANGED": {"MOUNTED"},
    "SIEGE": {"RANGED"},
    "GROUND": {"RANGED", "SIEGE"},
}

TIER_SCORE = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}

_ALIASES = {
    "ARCHER": "RANGED", "ARCHERS": "RANGED", "RANGE": "RANGED",
    "CAVALRY": "MOUNTED", "HORSE": "MOUNTED", "CAV": "MOUNTED",
    "INFANTRY": "GROUND", "INF": "GROUND", "FOOT": "GROUND",
    "SIEGE MACHINE": "SIEGE", "SIEGES": "SIEGE", "MACHINE": "SIEGE",
}

DEFAULT_DB = os.environ.get(
    "GAME_KB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_brain", "game_kb.db"),
)


def normalize_type(value):
    if not value:
        return None
    key = str(value).strip().upper()
    if key in TROOP_TYPES:
        return key
    return _ALIASES.get(key)


def counter_types(enemy_type):
    enemy = normalize_type(enemy_type)
    if not enemy:
        return []
    return [t for t in TROOP_TYPES if enemy in GOOD_AGAINST.get(t, set())]


def resolve_enemy(kb, enemy):
    direct = normalize_type(enemy)
    if direct:
        return direct, None
    general = kb.get_general(enemy)
    if general and normalize_type(general.get("gtype")):
        return normalize_type(general.get("gtype")), general
    return None, None


def _top_attack_buff(general, counter_type):
    if not general:
        return None
    needle = counter_type.title()
    best_text, best_pct = None, -1
    for spec in general.get("specialties") or []:
        if not isinstance(spec, str):
            continue
        if needle not in spec or "Attack" not in spec or "Enemy" in spec:
            continue
        match = re.search(r"\+(\d+)%", spec)
        pct = int(match.group(1)) if match else 0
        if pct > best_pct:
            best_pct, best_text = pct, spec.split(":")[-1].strip()
    return best_text


def _reason(kb, pick, enemy_type):
    counter = pick["counter_type"]
    tier_part = f"Tier {pick['tier']}" if pick.get("tier") else "rated"
    rank_part = f" (rank {pick['rank']})" if pick.get("rank") else ""
    text = (f"{tier_part} {counter.lower()} attacker{rank_part} — "
            f"{counter.title()} is strong against {enemy_type.title()}")
    buff = _top_attack_buff(kb.get_general(pick["general"]), counter)
    if buff:
        text += f"; key buff: {buff}"
    return text + "."


def recommend_counters(enemy, role="attack", top=5, db_path=None, kb=None):
    own = kb or GameKB(db_path or DEFAULT_DB)
    try:
        enemy_type, _ = resolve_enemy(own, enemy)
        if not enemy_type:
            return {"enemy": enemy, "error": f"unknown troop type or general: {enemy!r}"}
        ctypes = counter_types(enemy_type)
        picks = {}
        for counter in ctypes:
            role_key = f"{counter.lower()}_{role}"
            for rating in own.ratings(role=role_key):
                tier = (rating.get("tier") or "").upper()
                rank = rating.get("rank")
                score = TIER_SCORE.get(tier, 0) * 100 - int(rank if rank is not None else 99)
                existing = picks.get(rating["general"])
                if existing is None or score > existing["_score"]:
                    picks[rating["general"]] = {
                        "general": rating["general"],
                        "counter_type": counter,
                        "role": role_key,
                        "tier": tier or None,
                        "rank": rank,
                        "_score": score,
                    }
        ranked = sorted(picks.values(), key=lambda p: (-p["_score"], p["general"]))[:top]
        for pick in ranked:
            pick["why"] = _reason(own, pick, enemy_type)
            pick.pop("_score", None)
        return {
            "enemy": enemy,
            "enemy_type": enemy_type,
            "counter_types": ctypes,
            "role": role,
            "recommendations": ranked,
        }
    finally:
        if kb is None:
            own.close()


def format_counters(result):
    if result.get("error"):
        return result["error"]
    lines = [f"Enemy lead: {result['enemy_type']}  →  counter with "
             f"{', '.join(result['counter_types']) or '(none)'}"]
    if not result["recommendations"]:
        lines.append("  no rated counter generals found")
    for i, pick in enumerate(result["recommendations"], 1):
        tier = pick["tier"] or "?"
        rank = pick["rank"] if pick["rank"] is not None else "?"
        lines.append(f"{i}. {pick['general']}  [{pick['counter_type']} · Tier {tier} · rank {rank}]")
        lines.append(f"     {pick['why']}")
    return "\n".join(lines)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if not argv:
        print("usage: python counter_general.py <enemy_type_or_general> [attack|defense] [top] [--json]")
        return
    enemy = argv[0]
    role = argv[1] if len(argv) > 1 else "attack"
    top = int(argv[2]) if len(argv) > 2 else 5
    result = recommend_counters(enemy, role=role, top=top)
    print(json.dumps(result, indent=2) if as_json else format_counters(result))


if __name__ == "__main__":
    main()
