"""vision_db — persistent visual memory for the Evony game brain (kb/31).

Stores known screens, grounded elements, and observed captures in SQLite so
screen identification and navigation knowledge can improve across runs.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


class VisionDB:
    def __init__(self, path=None, *, clock=None, dedup_dist=4):
        self.path = Path(path) if path is not None else HERE / "game_brain" / "vision.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time
        self.dedup_dist = dedup_dist
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS screens (
                label TEXT PRIMARY KEY,
                description TEXT,
                keywords TEXT,
                template_path TEXT,
                anchors_json TEXT,
                nav_json TEXT,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS captures (
                id INTEGER PRIMARY KEY,
                ts REAL,
                image_path TEXT,
                phash INTEGER,
                screen_label TEXT,
                ocr_text TEXT,
                holo_desc TEXT,
                elements_json TEXT
            );
            CREATE TABLE IF NOT EXISTS elements (
                id INTEGER PRIMARY KEY,
                screen_label TEXT,
                name TEXT,
                cx REAL,
                cy REAL,
                w REAL,
                h REAL,
                template_path TEXT,
                description TEXT,
                UNIQUE(screen_label, name)
            );
            """
        )

    @staticmethod
    def _encode(value):
        return None if value is None else json.dumps(value)

    @staticmethod
    def _decode(value, default=None):
        if value is None:
            return default
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    @staticmethod
    def _unsigned_hash(value):
        return int(value) & ((1 << 64) - 1)

    @classmethod
    def _signed_hash(cls, value):
        value = cls._unsigned_hash(value)
        return value if value < (1 << 63) else value - (1 << 64)

    @classmethod
    def _hamming(cls, left, right):
        return (cls._unsigned_hash(left) ^ cls._unsigned_hash(right)).bit_count()

    @classmethod
    def _screen_dict(cls, row):
        result = dict(row)
        result["anchors"] = cls._decode(result.pop("anchors_json", None))
        result["nav"] = cls._decode(result.pop("nav_json", None))
        return result

    @classmethod
    def _capture_dict(cls, row):
        result = dict(row)
        result["elements"] = cls._decode(result.pop("elements_json", None), [])
        try:
            if result["phash"] is not None:
                result["phash"] = cls._unsigned_hash(result["phash"])
        except (KeyError, TypeError, ValueError):
            result["phash"] = None
        return result

    def close(self):
        self._db.close()

    # Public API
    def upsert_screen(self, label, description=None, keywords=None, template_path=None,
                      anchors=None, nav=None):
        updated_at = self._clock()
        with self._db:
            self._db.execute(
                """
                INSERT INTO screens
                    (label, description, keywords, template_path, anchors_json, nav_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(label) DO UPDATE SET
                    description = excluded.description,
                    keywords = excluded.keywords,
                    template_path = excluded.template_path,
                    anchors_json = excluded.anchors_json,
                    nav_json = excluded.nav_json,
                    updated_at = excluded.updated_at
                """,
                (label, description, keywords, template_path, self._encode(anchors),
                 self._encode(nav), updated_at),
            )

    def get_screen(self, label):
        row = self._db.execute("SELECT * FROM screens WHERE label = ?", (label,)).fetchone()
        return self._screen_dict(row) if row is not None else None

    def list_screens(self):
        rows = self._db.execute("SELECT * FROM screens ORDER BY label").fetchall()
        return [self._screen_dict(row) for row in rows]

    def add_element(self, screen_label, name, cx, cy, w=0, h=0, template_path=None,
                    description=None):
        with self._db:
            self._db.execute(
                """
                INSERT INTO elements
                    (screen_label, name, cx, cy, w, h, template_path, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(screen_label, name) DO UPDATE SET
                    cx = excluded.cx,
                    cy = excluded.cy,
                    w = excluded.w,
                    h = excluded.h,
                    template_path = excluded.template_path,
                    description = excluded.description
                """,
                (screen_label, name, cx, cy, w, h, template_path, description),
            )

    def elements(self, screen_label):
        rows = self._db.execute(
            "SELECT * FROM elements WHERE screen_label = ? ORDER BY name", (screen_label,)
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def phash(image):
        if isinstance(image, (str, Path)):
            with Image.open(image) as opened:
                source = opened.copy()
        elif isinstance(image, Image.Image):
            source = image
        elif isinstance(image, np.ndarray):
            if image.ndim == 2:
                source = Image.fromarray(image)
            elif image.ndim == 3 and image.shape[2] >= 3:
                source = Image.fromarray(image[:, :, :3][:, :, ::-1])
            else:
                raise ValueError("numpy image must be grayscale or BGR")
        else:
            raise TypeError("image must be a PIL Image, numpy array, or path")
        gray = np.asarray(source.convert("L").resize((9, 8), Image.Resampling.LANCZOS))
        value = 0
        for bit in (gray[:, 1:] > gray[:, :-1]).flat:
            value = (value << 1) | int(bit)
        return value

    def record_capture(self, image_path=None, phash=None, screen_label=None, ocr_text=None,
                       holo_desc=None, elements=None, ts=None):
        ts = self._clock() if ts is None else ts
        if phash is None and image_path is not None:
            phash = self.phash(image_path)
        stored_hash = None if phash is None else self._signed_hash(phash)
        encoded_elements = self._encode(elements)
        best = None
        if phash is not None:
            rows = self._db.execute(
                """
                SELECT id, phash FROM captures
                WHERE screen_label IS ? AND phash IS NOT NULL
                ORDER BY ts DESC LIMIT 100
                """,
                (screen_label,),
            ).fetchall()
            for row in rows:
                try:
                    distance = self._hamming(phash, row["phash"])
                except (TypeError, ValueError):
                    continue
                if best is None or distance < best[0]:
                    best = distance, row["id"]
        values = (ts, image_path, stored_hash, screen_label, ocr_text, holo_desc,
                  encoded_elements)
        with self._db:
            if best is not None and best[0] <= self.dedup_dist:
                self._db.execute(
                    """
                    UPDATE captures SET
                        ts = ?, image_path = ?, phash = ?, screen_label = ?,
                        ocr_text = ?, holo_desc = ?, elements_json = ?
                    WHERE id = ?
                    """,
                    values + (best[1],),
                )
                return best[1], False
            cursor = self._db.execute(
                """
                INSERT INTO captures
                    (ts, image_path, phash, screen_label, ocr_text, holo_desc, elements_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return cursor.lastrowid, True

    def search(self, text):
        pattern = f"%{str(text).lower()}%"
        captures = self._db.execute(
            """
            SELECT * FROM captures
            WHERE lower(coalesce(ocr_text, '')) LIKE ?
               OR lower(coalesce(holo_desc, '')) LIKE ?
            ORDER BY ts DESC
            """,
            (pattern, pattern),
        ).fetchall()
        screens = self._db.execute(
            """
            SELECT * FROM screens
            WHERE lower(coalesce(description, '')) LIKE ?
               OR lower(coalesce(keywords, '')) LIKE ?
            ORDER BY label
            """,
            (pattern, pattern),
        ).fetchall()
        results = []
        for row in captures:
            result = self._capture_dict(row)
            result["type"] = "capture"
            results.append(result)
        for row in screens:
            result = self._screen_dict(row)
            result["type"] = "screen"
            results.append(result)
        return results

    def catalog(self):
        return {
            screen["label"]: {
                "description": screen["description"],
                "keywords": screen["keywords"],
                "anchors": screen["anchors"],
                "nav": screen["nav"],
                "elements": self.elements(screen["label"]),
            }
            for screen in self.list_screens()
        }

    def stats(self):
        return {
            table: self._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("screens", "captures", "elements")
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
        db = VisionDB(Path(temporary) / "vision.db", clock=lambda: now[0])

        def case_1_screen_upsert():
            db.upsert_screen("city", "Old city", "buildings", "old.png",
                             {"keep": [1, 2]}, {"world_map": "map"})
            now[0] = 2_000.0
            db.upsert_screen("city", "Inside the walls", "Royal Keep Walls", "city.png",
                             {"keep": [30, 40]}, {"world_map": "exit"})
            screens = db.list_screens()
            assert len(screens) == 1
            assert screens[0]["description"] == "Inside the walls"
            assert screens[0]["keywords"] == "Royal Keep Walls"
            assert screens[0]["anchors"] == {"keep": [30, 40]}
            assert screens[0]["nav"] == {"world_map": "exit"}
            assert screens[0]["updated_at"] == 2_000.0

        ok &= run_case("1 screen upsert", case_1_screen_upsert)

        def case_2_element_upsert():
            db.add_element("city", "Keep", 10, 20, 30, 40, "old.png", "old")
            db.add_element("city", "Keep", 50, 60, 70, 80, "keep.png", "castle")
            found = db.elements("city")
            assert len(found) == 1
            assert found[0]["name"] == "Keep"
            assert (found[0]["cx"], found[0]["cy"], found[0]["w"], found[0]["h"]) == (50, 60, 70, 80)
            assert found[0]["template_path"] == "keep.png"
            assert found[0]["description"] == "castle"

        ok &= run_case("2 element upsert", case_2_element_upsert)

        def case_3_phash():
            global first_hash, different_hash
            ramp = np.tile(np.arange(16, dtype=np.uint8) * 16, (16, 1))
            first = Image.fromarray(ramp)
            identical = Image.fromarray(ramp.copy())
            different = Image.fromarray(np.fliplr(ramp))
            first_hash = db.phash(first)
            same_hash = db.phash(identical)
            different_hash = db.phash(different)
            assert db._hamming(first_hash, same_hash) == 0
            assert db._hamming(first_hash, different_hash) > 4

        ok &= run_case("3 perceptual hash", case_3_phash)

        def case_4_capture_dedup():
            now[0] = 3_000.0
            first_id, is_new = db.record_capture("first.png", first_hash, "city",
                                                 "Royal Army", "city view", [{"name": "Keep"}])
            assert is_new
            assert db.stats()["captures"] == 1
            now[0] = 3_001.0
            duplicate_id, is_new = db.record_capture("second.png", first_hash ^ 3, "city",
                                                     "Royal Army report", "same city", [])
            assert not is_new
            assert duplicate_id == first_id
            assert db.stats()["captures"] == 1
            now[0] = 3_002.0
            _, is_new = db.record_capture("different.png", different_hash, "city",
                                          "Different view", "other", [])
            assert is_new
            assert db.stats()["captures"] == 2

        ok &= run_case("4 capture dedup", case_4_capture_dedup)

        def case_5_search():
            capture_results = db.search("army")
            screen_results = db.search("keep")
            assert any(result["type"] == "capture" for result in capture_results)
            assert any(result["type"] == "screen" for result in screen_results)

        ok &= run_case("5 search", case_5_search)

        def case_6_catalog_stats():
            catalog = db.catalog()
            assert "city" in catalog
            assert len(catalog["city"]["elements"]) == 1
            assert catalog["city"]["elements"][0]["name"] == "Keep"
            assert db.stats() == {"screens": 1, "captures": 2, "elements": 1}

        ok &= run_case("6 catalog and stats", case_6_catalog_stats)
        db.close()

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
