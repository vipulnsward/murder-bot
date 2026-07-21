"""SQLite knowledge base for Evony generals, ratings, skills, and guides."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent


class GameKB:
    def __init__(self, path=None, *, clock=None):
        self.path = Path(path) if path is not None else HERE / "game_brain" / "game_kb.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS generals (
                name TEXT PRIMARY KEY,
                quality TEXT,
                gtype TEXT,
                is_debuff INTEGER,
                specialties_json TEXT,
                skill TEXT,
                ascending_json TEXT,
                best_use TEXT,
                notes TEXT,
                source_url TEXT,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY,
                general TEXT,
                role TEXT,
                tier TEXT,
                rank INTEGER,
                context TEXT NOT NULL DEFAULT '',
                UNIQUE(general, role, context)
            );
            CREATE TABLE IF NOT EXISTS skills (
                name TEXT PRIMARY KEY,
                effect TEXT,
                kind TEXT
            );
            CREATE TABLE IF NOT EXISTS guides (
                id INTEGER PRIMARY KEY,
                title TEXT,
                url TEXT UNIQUE,
                category TEXT,
                summary TEXT,
                content TEXT,
                updated_at REAL
            );
            """
        )

    @staticmethod
    def _encode(value):
        if value is None:
            return None
        try:
            return json.dumps(value)
        except (TypeError, ValueError, RecursionError):
            return None

    @staticmethod
    def _decode(value, default=None):
        if value is None:
            return default
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    @classmethod
    def _general_dict(cls, row):
        result = dict(row)
        result["specialties"] = cls._decode(result.pop("specialties_json", None))
        result["ascending"] = cls._decode(result.pop("ascending_json", None))
        return result

    @staticmethod
    def _rating_dict(row):
        result = dict(row)
        if result.get("context") == "":
            result["context"] = None
        return result

    def close(self):
        self._db.close()

    def upsert_general(self, name, quality=None, gtype=None, is_debuff=None,
                       specialties=None, skill=None, ascending=None, best_use=None,
                       notes=None, source_url=None):
        with self._db:
            self._db.execute(
                """
                INSERT INTO generals
                    (name, quality, gtype, is_debuff, specialties_json, skill,
                     ascending_json, best_use, notes, source_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    quality = excluded.quality,
                    gtype = excluded.gtype,
                    is_debuff = excluded.is_debuff,
                    specialties_json = excluded.specialties_json,
                    skill = excluded.skill,
                    ascending_json = excluded.ascending_json,
                    best_use = excluded.best_use,
                    notes = excluded.notes,
                    source_url = excluded.source_url,
                    updated_at = excluded.updated_at
                """,
                (name, quality, gtype, None if is_debuff is None else int(bool(is_debuff)),
                 self._encode(specialties), skill, self._encode(ascending), best_use,
                 notes, source_url, self._clock()),
            )

    def get_general(self, name):
        row = self._db.execute("SELECT * FROM generals WHERE name = ?", (name,)).fetchone()
        return self._general_dict(row) if row is not None else None

    def list_generals(self, gtype=None):
        if gtype is None:
            rows = self._db.execute("SELECT * FROM generals ORDER BY name").fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM generals WHERE gtype = ? ORDER BY name", (gtype,)
            ).fetchall()
        return [self._general_dict(row) for row in rows]

    def add_rating(self, general, role, tier=None, rank=None, context=None):
        with self._db:
            self._db.execute(
                """
                INSERT INTO ratings (general, role, tier, rank, context)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(general, role, context) DO UPDATE SET
                    tier = excluded.tier,
                    rank = excluded.rank
                """,
                (general, role, tier, rank, "" if context is None else context),
            )

    def ratings(self, general=None, role=None):
        clauses = []
        values = []
        if general is not None:
            clauses.append("general = ?")
            values.append(general)
        if role is not None:
            clauses.append("role = ?")
            values.append(role)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM ratings{where} ORDER BY general, role, context, id", values
        ).fetchall()
        return [self._rating_dict(row) for row in rows]

    def add_skill(self, name, effect=None, kind=None):
        with self._db:
            self._db.execute(
                """
                INSERT INTO skills (name, effect, kind) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    effect = excluded.effect,
                    kind = excluded.kind
                """,
                (name, effect, kind),
            )

    def get_skill(self, name):
        row = self._db.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
        return dict(row) if row is not None else None

    def add_guide(self, title, url, category=None, summary=None, content=None):
        with self._db:
            self._db.execute(
                """
                INSERT INTO guides
                    (title, url, category, summary, content, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    category = excluded.category,
                    summary = excluded.summary,
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                (title, url, category, summary, content, self._clock()),
            )

    def guides(self, category=None):
        if category is None:
            rows = self._db.execute("SELECT * FROM guides ORDER BY title, url").fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM guides WHERE category = ? ORDER BY title, url", (category,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_guide(self, url):
        row = self._db.execute("SELECT * FROM guides WHERE url = ?", (url,)).fetchone()
        return dict(row) if row is not None else None

    def search(self, text):
        pattern = f"%{str(text).lower()}%"
        general_rows = self._db.execute(
            """
            SELECT * FROM generals
            WHERE lower(coalesce(name, '')) LIKE ?
               OR lower(coalesce(best_use, '')) LIKE ?
               OR lower(coalesce(notes, '')) LIKE ?
               OR lower(coalesce(skill, '')) LIKE ?
            ORDER BY name
            """,
            (pattern,) * 4,
        ).fetchall()
        guide_rows = self._db.execute(
            """
            SELECT * FROM guides
            WHERE lower(coalesce(title, '')) LIKE ?
               OR lower(coalesce(summary, '')) LIKE ?
               OR lower(coalesce(content, '')) LIKE ?
            ORDER BY title, url
            """,
            (pattern,) * 3,
        ).fetchall()
        return {
            "generals": [self._general_dict(row) for row in general_rows],
            "guides": [dict(row) for row in guide_rows],
        }

    def load_generals_jsonl(self, path):
        loaded = 0
        with Path(path).open(encoding="utf-8") as source:
            for line in source:
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict) or not record.get("name"):
                        continue
                    self.upsert_general(
                        name=record["name"],
                        quality=record.get("quality"),
                        gtype=record.get("gtype"),
                        specialties=record.get("specialties"),
                        skill=record.get("skill"),
                        ascending=record.get("ascending"),
                        best_use=record.get("best_use"),
                        source_url=record.get("source_url"),
                    )
                    for rating in record.get("ratings", []):
                        if isinstance(rating, dict) and rating.get("role"):
                            self.add_rating(
                                general=record["name"],
                                role=rating["role"],
                                tier=rating.get("tier"),
                                rank=rating.get("rank"),
                                context=rating.get("context"),
                            )
                    loaded += 1
                except (json.JSONDecodeError, TypeError, ValueError, sqlite3.Error):
                    continue
        return loaded

    def stats(self):
        return {
            table: self._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("generals", "ratings", "skills", "guides")
        }


# Deterministic self-test
if __name__ == "__main__":
    ok = True

    def run_case(name, case):
        try:
            case()
            print(f"{name}: PASS")
            return True
        except Exception as error:
            print(f"{name}: FAIL ({error})")
            return False

    with tempfile.TemporaryDirectory() as temporary:
        now = [1_000.0]
        db = GameKB(Path(temporary) / "game_kb.db", clock=lambda: now[0])

        def case_1_general_upsert():
            db.upsert_general("Hannibal", quality="epic", gtype="mounted",
                              specialties=["Mounted Troop Assault"], best_use="old use")
            now[0] = 2_000.0
            db.upsert_general("Hannibal", quality="historic", gtype="mounted",
                              specialties=["War God", "Mounted Troop Assault"],
                              skill="Master of Strategy", best_use="mounted troop attack")
            assert len(db.list_generals()) == 1
            found = db.get_general("Hannibal")
            assert found["quality"] == "historic"
            assert found["specialties"] == ["War God", "Mounted Troop Assault"]
            assert found["updated_at"] == 2_000.0

        ok &= run_case("1 general upsert", case_1_general_upsert)

        def case_2_rating_upsert_filters():
            db.add_rating("Hannibal", "monarch_attack", "A", 5)
            db.add_rating("Hannibal", "monarch_attack", "S", 2)
            assert len(db.ratings()) == 1
            assert db.ratings(general="Hannibal")[0]["tier"] == "S"
            assert db.ratings(role="monarch_attack")[0]["rank"] == 2

        ok &= run_case("2 rating upsert and filters", case_2_rating_upsert_filters)

        def case_3_skill():
            db.add_skill("Mounted Troop Attack", "+20% attack", "skill_book")
            assert db.get_skill("Mounted Troop Attack")["effect"] == "+20% attack"

        ok &= run_case("3 skill", case_3_skill)

        def case_4_guide_upsert():
            db.add_guide("Alliance War Guide", "https://example.test/war", "pvp", "Old")
            now[0] = 3_000.0
            db.add_guide("Alliance War Guide", "https://example.test/war", "pvp",
                         "Updated", "Coordinate rallies.")
            assert len(db.guides()) == 1
            found = db.get_guide("https://example.test/war")
            assert found["summary"] == "Updated"
            assert found["updated_at"] == 3_000.0

        ok &= run_case("4 guide upsert", case_4_guide_upsert)

        def case_5_jsonl_load():
            jsonl = Path(temporary) / "generals.jsonl"
            records = [
                {"name": "Elise", "quality": "epic", "gtype": "ground",
                 "specialties": ["Ground Troop Assault"], "skill": "Blood of the King",
                 "ascending": {"stars": 5}, "best_use": "ground attack",
                 "ratings": [{"role": "ground_attack", "tier": "S", "rank": 1,
                              "context": "fully ascended"}],
                 "source_url": "https://example.test/elise"},
                {"name": "Martinus", "quality": "epic", "gtype": "mounted",
                 "specialties": [], "skill": "The Dragon Wakes", "ascending": {},
                 "best_use": "monster hunting", "ratings": [],
                 "source_url": "https://example.test/martinus"},
            ]
            jsonl.write_text("\n".join(json.dumps(record) for record in records) +
                             "\n{malformed\n", encoding="utf-8")
            assert db.load_generals_jsonl(jsonl) == 2
            assert db.get_general("Elise")["ascending"] == {"stars": 5}
            assert db.ratings(general="Elise")[0]["role"] == "ground_attack"

        ok &= run_case("5 JSONL load", case_5_jsonl_load)

        def case_6_search_stats():
            assert db.search("troop attack")["generals"][0]["name"] == "Hannibal"
            assert db.search("alliance")["guides"][0]["title"] == "Alliance War Guide"
            assert db.stats() == {"generals": 3, "ratings": 2, "skills": 1, "guides": 1}

        ok &= run_case("6 search and stats", case_6_search_stats)
        db.close()

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
