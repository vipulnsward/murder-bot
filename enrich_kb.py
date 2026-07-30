"""Enrich the Evony knowledge base with debuff flags and general effects."""

from __future__ import annotations

import json
import re
from pathlib import Path

from game_kb import GameKB


DB_PATH = Path(__file__).resolve().parent / "game_brain" / "game_kb.db"
EFFECT_KEYS = {"effect", "effects", "skill", "skills", "specialty", "specialties"}
NEGATIVE = r"(?<![\d+])-\s*\d+(?:\.\d+)?\s*%"
ENEMY_NEGATIVE = re.compile(
    rf"(?:\benemy\b[^,;\]\}}\n]{{0,120}}{NEGATIVE}|"
    rf"{NEGATIVE}[^,;\[\{{\n]{{0,120}}\benemy\b)",
    re.IGNORECASE,
)
NEGATIVE_RE = re.compile(NEGATIVE)
ENEMY_RE = re.compile(r"\benemy\b", re.IGNORECASE)
DEBUFF_RE = re.compile(r"\bdebuff\b", re.IGNORECASE)


def extract_effects(value, accept_strings=True):
    if isinstance(value, str):
        if accept_strings and value.strip():
            yield value.strip()
    elif isinstance(value, list):
        for item in value:
            yield from extract_effects(item, accept_strings)
    elif isinstance(value, dict):
        for key, item in value.items():
            is_effect = str(key).casefold() in EFFECT_KEYS
            if is_effect or isinstance(item, (list, dict)):
                yield from extract_effects(item, is_effect)


def decode(raw):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw


def has_enemy_debuff(values):
    text = " ".join(str(value) for value in values if value)
    return bool(
        (ENEMY_RE.search(text) and DEBUFF_RE.search(text))
        or ENEMY_NEGATIVE.search(text)
    )


def main():
    assert has_enemy_debuff(["Enemy Troop HP -10%"])
    assert not has_enemy_debuff(["Mounted Attack +10-36%"])

    kb = GameKB(DB_PATH)
    try:
        db = kb._db
        before_debuff = db.execute(
            "SELECT COUNT(*) FROM generals WHERE is_debuff = 1"
        ).fetchone()[0]
        rows = db.execute(
            """
            SELECT name, is_debuff, specialties_json, ascending_json, skill, notes
            FROM generals
            """
        ).fetchall()
        newly_flagged = [
            row["name"]
            for row in rows
            if row["is_debuff"] != 1 and has_enemy_debuff(row[2:])
        ]
        with db:
            db.executemany(
                "UPDATE generals SET is_debuff = 1 WHERE name = ?",
                ((name,) for name in newly_flagged),
            )

        before_skills = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        effects = {
            effect
            for row in rows
            for raw in (row["specialties_json"], row["ascending_json"])
            for effect in extract_effects(decode(raw))
        }
        for effect in sorted(effects):
            kind = "debuff" if ENEMY_RE.search(effect) or NEGATIVE_RE.search(effect) else "buff"
            kb.add_skill(effect, effect, kind)

        after_debuff = db.execute(
            "SELECT COUNT(*) FROM generals WHERE is_debuff = 1"
        ).fetchone()[0]
        after_skills = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        print(f"is_debuff before: {before_debuff}")
        print(f"is_debuff newly flagged: {len(newly_flagged)}")
        print(f"is_debuff after: {after_debuff}")
        print(f"skills before: {before_skills}")
        print(f"skills inserted: {after_skills - before_skills}")
        print(f"skills after: {after_skills}")
    finally:
        kb.close()


if __name__ == "__main__":
    main()
