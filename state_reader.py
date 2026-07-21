"""state_reader — cheap per-tick perception snapshots for Evony.

REGIONS use 1080x1920 device coordinates and are sensible placeholders only.
[LIVE-CAPTURE] tune to real screen before relying on their values.
"""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import Optional


@dataclass
class GameState:
    screen: Optional[str] = None
    ts: Optional[float] = None
    phash: Optional[int] = None
    resources: Optional[dict] = None
    gems: Optional[int] = None
    troops: Optional[int] = None
    power: Optional[int] = None
    idle_marches: Optional[int] = None
    marches_out: Optional[int] = None
    timers: Optional[dict] = None
    under_attack: Optional[bool] = None
    red_dots: Optional[dict] = None
    disconnect: Optional[bool] = None
    raw: Optional[dict] = None


REGIONS = {
    "resources": (0, 0, 820, 140),
    "food": (0, 0, 164, 140),
    "wood": (164, 0, 328, 140),
    "stone": (328, 0, 492, 140),
    "ore": (492, 0, 656, 140),
    "gold": (656, 0, 820, 140),
    "gems": (820, 0, 1080, 140),
    "troops": (360, 300, 720, 430),
    "power": (40, 140, 430, 230),
    "idle_marches": (760, 1440, 1060, 1530),
    "marches_out": (760, 1530, 1060, 1620),
    "rally_timer": (350, 410, 730, 510),
    "mail_dot": (940, 1740, 1080, 1880),
}

SCREEN_FIELDS = {
    "city": ["resources", "gems", "mail_dot"],
    "resources": ["resources", "gems"],
    "training_barracks": ["troops"],
    "world_map": ["gems", "idle_marches", "marches_out"],
    "rally_list": ["rally_timer"],
    "watchtower": [],
    "disconnect": [],
}

RESOURCE_NAMES = ("food", "wood", "stone", "ore", "gold")


class StateReader:
    def __init__(self, screencap, classify=None, read_number_fast=None,
                 red_dot=None, db=None, clock=None, phash=None):
        if classify is None:
            from screen_id import classify as classify_screen
            classify = classify_screen
        if read_number_fast is None:
            from ocr_read import read_number_fast as fast_number
            read_number_fast = fast_number
        if red_dot is None:
            from perception import red_dot as detect_red_dot
            red_dot = detect_red_dot
        if clock is None:
            from time import time
            clock = time
        if phash is None:
            from vision_db import VisionDB
            phash = VisionDB.phash

        self._screencap = screencap
        self._classify = classify
        self._read_number_fast = read_number_fast
        self._red_dot = red_dot
        self._db = db
        self._clock = clock
        self._phash = phash
        self._last_phash = None
        self._cache = {}

    def _number(self, img, region):
        try:
            return self._read_number_fast(img, REGIONS[region])
        except Exception:
            return None

    def _badge(self, img, region):
        try:
            return self._red_dot(img, REGIONS[region])
        except Exception:
            return None

    def read(self):
        img = self._screencap()
        ph = self._phash(img)
        if ph == self._last_phash and ph in self._cache:
            return self._cache[ph]

        try:
            screen, description, score = self._classify(img)
            classify_error = None
        except Exception as error:
            screen, description, score = "unknown", "", 0
            classify_error = str(error)

        values = {
            "resources": None,
            "gems": None,
            "troops": None,
            "power": None,
            "idle_marches": None,
            "marches_out": None,
            "timers": None,
            "red_dots": None,
        }
        ocr_values = {}
        elements = []
        for region in SCREEN_FIELDS.get(screen, []):
            if region == "resources":
                values["resources"] = {}
                for name in RESOURCE_NAMES:
                    value = self._number(img, name)
                    values["resources"][name] = value
                    if value is not None:
                        ocr_values[name] = value
                    elements.append({"name": name, "value": value})
            elif region.endswith("_dot"):
                name = region.removesuffix("_dot")
                values["red_dots"] = values["red_dots"] or {}
                values["red_dots"][name] = self._badge(img, region)
                elements.append({"name": region, "value": values["red_dots"][name]})
            elif region.endswith("_timer"):
                value = self._number(img, region)
                values["timers"] = values["timers"] or {}
                values["timers"][region.removesuffix("_timer")] = value
                if value is not None:
                    ocr_values[region] = value
                elements.append({"name": region, "value": value})
            else:
                value = self._number(img, region)
                values[region] = value
                if value is not None:
                    ocr_values[region] = value
                elements.append({"name": region, "value": value})

        raw = {"description": description, "score": score}
        if classify_error is not None:
            raw["classify_error"] = classify_error
        state = GameState(
            screen=screen,
            ts=self._clock(),
            phash=ph,
            under_attack=screen == "watchtower",
            disconnect=screen == "disconnect",
            raw=raw,
            **values,
        )
        if self._db is not None:
            image_path = img if isinstance(img, (str, PathLike)) else None
            ocr_text = " ".join(f"{name}={value}" for name, value in ocr_values.items())
            self._db.record_capture(image_path, phash=ph, screen_label=screen,
                                    ocr_text=ocr_text, elements=elements)
        self._last_phash = ph
        self._cache = {ph: state}
        return state


if __name__ == "__main__":
    ok = True
    frames = iter(("FRAME_A", "FRAME_A", "FRAME_B"))
    ocr_calls = []

    def screencap():
        return next(frames)

    def fake_phash(frame):
        return {"FRAME_A": 1, "FRAME_B": 2}[frame]

    def fake_classify(_frame):
        return "city", "city view with resources", 3

    def fake_read_number(_frame, box):
        ocr_calls.append(box)
        return 1234

    def fake_red_dot(_frame, _box):
        return True

    class FakeDB:
        def __init__(self):
            self.calls = []

        def record_capture(self, image_path=None, **kwargs):
            self.calls.append((image_path, kwargs))

    fake_db = FakeDB()
    reader = StateReader(screencap, classify=fake_classify,
                         read_number_fast=fake_read_number,
                         red_dot=fake_red_dot, db=fake_db,
                         clock=lambda: 1000.0, phash=fake_phash)

    first = reader.read()
    try:
        assert first.screen == "city"
        assert first.resources["food"] == 1234
        assert first.gems == 1234
        assert len(fake_db.calls) == 1
        print(f"1 first frame: PASS screen={first.screen} food={first.resources['food']} gems={first.gems} ocr_calls={len(ocr_calls)} db_calls={len(fake_db.calls)}")
    except AssertionError:
        ok = False
        print("1 first frame: FAIL")

    first_ocr_count = len(ocr_calls)
    second = reader.read()
    try:
        assert second is first
        assert len(ocr_calls) == first_ocr_count
        assert len(fake_db.calls) == 1
        print(f"2 repeated frame: PASS cached={second is first} ocr_calls={len(ocr_calls)} db_calls={len(fake_db.calls)}")
    except AssertionError:
        ok = False
        print("2 repeated frame: FAIL")

    third = reader.read()
    try:
        assert third.phash == 2
        assert len(ocr_calls) > first_ocr_count
        assert len(fake_db.calls) == 2
        print(f"3 changed frame: PASS phash={third.phash} ocr_calls={len(ocr_calls)} db_calls={len(fake_db.calls)}")
    except AssertionError:
        ok = False
        print("3 changed frame: FAIL")

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
