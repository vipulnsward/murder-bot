"""troop_intel — read troop counts and training costs from the training screens.

Each troop-training building (Barracks=ground, Stable=mounted, Archer Camp=ranged,
Workshop=siege) has a Train screen showing, for the selected tier: the troop name,
"Own: N" (how many you have), the per-batch resource cost (food/wood/stone/ore/gold),
the batch quantity, the train time, and an Instant-Train gem price. A horizontal tier
selector switches tiers; each tier is a unique named troop.

READ-ONLY + GEM/RESOURCE-SAFE: this NEVER taps "Train" or "Instant Train" (which would
actually spend resources/gems to train). It only reads numbers and taps tier icons / the
quantity slider / Back. Results go to vision.db (troops table) and game_brain/troops.jsonl.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time

import game_hud
import ocr_read

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "game_brain", "vision.db")
JSONL = os.path.join(ROOT, "game_brain", "troops.jsonl")

# Regions on the 1080x1920 Train screen (mapped from the live client).
BADGE_BOX = (300, 980, 800, 1070)     # troop name ("Steel Helepolis"); the tier emblem is unreadable
OWN_BOX = (330, 1085, 760, 1170)      # "Own: 20,280,000"
FOOD_BOX = (60, 1365, 270, 1445)
WOOD_BOX = (300, 1365, 520, 1445)
STONE_BOX = (555, 1365, 770, 1445)
ORE_BOX = (800, 1365, 1035, 1445)
GOLD_BOX = (360, 1450, 700, 1545)     # gold coins value below the resource row
QTY_BOX = (780, 1615, 1050, 1715)     # batch quantity (right of the +/- slider)
TIME_BOX = (700, 1830, 1055, 1918)    # green Train button: train time
GEM_BOX = (110, 1830, 540, 1918)      # gold Instant-Train button: gem price
SELECTOR_BOX = (0, 1180, 1080, 1330)  # horizontal tier-icon row (roman numerals)

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s):
    """'XVI' -> 16; None for anything that isn't purely a roman numeral."""
    s = re.sub(r"\s", "", str(s).strip().upper())
    if not s or any(ch not in _ROMAN for ch in s):
        return None
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN[ch]
        total += -v if v < prev else v
        prev = v
    return total


def parse_time(text):
    """'169d 17:38' -> seconds; '17:38' / '1:02:03' also handled; None if no time."""
    s = str(text).lower()
    dm = re.search(r"(\d+)\s*d", s)
    days = int(dm.group(1)) if dm else 0
    hms = re.findall(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if not hms and not dm:
        return None
    secs = days * 86400
    if hms:
        a, b, c = hms[0]
        secs += int(a) * 3600 + int(b) * 60 + (int(c) if c else 0)
    return secs


def _amount(img, box):
    """The most confident parse_amount in a tight region, or None."""
    best = None
    for t, _c, cf in ocr_read.read_all(img, box=box, cache=True):
        v = game_hud.parse_amount(t)
        if v is not None and (best is None or cf > best[1]):
            best = (v, cf)
    return best[0] if best else None


def is_train_screen(img):
    """True if this looks like a Train screen. The bottom-button LABELS are unreadable
    (only their numbers OCR), so anchor on the reliable 'Own:' line plus a tier selector."""
    if img is None:
        return False
    own = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img, box=OWN_BOX, cache=True))
    return "own" in own and bool(selector_tiers(img))


def selector_tiers(img):
    """Readable tier icons in the selector row as [(tier_int, cx)], left-to-right, with
    single-icon gaps interpolated (OCR misreads e.g. XVI as 'XVT')."""
    got = []
    for t, (cx, _cy), cf in ocr_read.read_all(img, box=SELECTOR_BOX, cache=True):
        r = roman_to_int(t)
        if r is not None:
            got.append((r, cx))
    got.sort(key=lambda p: p[1])
    if len(got) >= 2:
        # fill a single missing icon between two readable, evenly-spaced ones
        filled = []
        for i in range(len(got) - 1):
            filled.append(got[i])
            (t0, x0), (t1, x1) = got[i], got[i + 1]
            if t1 - t0 == 2 and x1 - x0 > 0:
                filled.append((t0 + 1, (x0 + x1) // 2))
        filled.append(got[-1])
        got = filled
    return got


def read_train_screen(img):
    """Parse the currently-selected tier of a Train screen. Returns a dict with
    name/own/cost{food,wood,stone,ore,gold}/qty/train_seconds/instant_gems, or None if
    this isn't a Train screen. `tier` is best-effort (None here; the gather loop assigns
    it by stepping the selector)."""
    if not is_train_screen(img):
        return None
    name_parts = [str(t).strip() for t, _c, _cf in ocr_read.read_all(img, box=BADGE_BOX, cache=True)
                  if str(t).strip() and roman_to_int(t) is None]
    name = " ".join(name_parts).strip() or None

    own_txt = " ".join(str(t) for t, *_ in ocr_read.read_all(img, box=OWN_BOX, cache=True))
    own = game_hud.parse_amount(re.sub(r"(?i)own[:\s]*", "", own_txt))

    cost = {
        "food": _amount(img, FOOD_BOX), "wood": _amount(img, WOOD_BOX),
        "stone": _amount(img, STONE_BOX), "ore": _amount(img, ORE_BOX),
        "gold": _amount(img, GOLD_BOX),
    }
    time_txt = " ".join(str(t) for t, *_ in ocr_read.read_all(img, box=TIME_BOX, cache=True))
    if name is None and own is None:
        return None
    return {
        "tier": None, "name": name, "own": own, "cost": cost,
        "qty": _amount(img, QTY_BOX), "train_seconds": parse_time(time_txt),
        "instant_gems": _amount(img, GEM_BOX),
    }


def _ensure_table(conn):
    conn.execute(
        "create table if not exists troops("
        "building text, tier integer, name text, own integer,"
        "cost_food integer, cost_wood integer, cost_stone integer, cost_ore integer, cost_gold integer,"
        "train_seconds integer, instant_gems integer, qty integer, updated_at real,"
        "primary key(building, name))")


def record(building, tier, info, db=DB, jsonl=JSONL, ts=None):
    """Persist one tier's reading to vision.db (troops, upserted by building+name) and
    append the full record to the brain jsonl. Skips rows with no name (bad read)."""
    name = (info or {}).get("name")
    if not name:
        return False
    ts = time.time() if ts is None else ts
    c = info.get("cost", {}) or {}
    conn = sqlite3.connect(db)
    try:
        _ensure_table(conn)
        conn.execute(
            "insert into troops values(?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "on conflict(building,name) do update set tier=excluded.tier, own=excluded.own, "
            "cost_food=excluded.cost_food, cost_wood=excluded.cost_wood, cost_stone=excluded.cost_stone, "
            "cost_ore=excluded.cost_ore, cost_gold=excluded.cost_gold, train_seconds=excluded.train_seconds, "
            "instant_gems=excluded.instant_gems, qty=excluded.qty, updated_at=excluded.updated_at",
            (building, tier, name, info.get("own"),
             c.get("food"), c.get("wood"), c.get("stone"), c.get("ore"), c.get("gold"),
             info.get("train_seconds"), info.get("instant_gems"), info.get("qty"), ts))
        conn.commit()
    finally:
        conn.close()
    if jsonl:
        with open(jsonl, "a") as fh:
            fh.write(json.dumps({"building": building, "tier": tier, **info, "ts": ts}) + "\n")
    return True


def _selftest():
    import tempfile
    ok = True
    romans = [("XVI", 16), ("XIV", 14), ("XV", 15), ("XVII", 17), ("IX", 9),
              ("I", 1), ("XL", 40), ("abc", None), ("XVT", None), ("", None)]
    for r, want in romans:
        got = roman_to_int(r)
        if got != want:
            print(f"FAIL roman_to_int({r!r}) -> {got} (want {want})"); ok = False
    times = [("169d 17:38", 169 * 86400 + 17 * 3600 + 38 * 60),
             ("17:38", 17 * 3600 + 38 * 60), ("1:02:03", 3723),
             ("instant", None), ("", None)]
    for txt, want in times:
        got = parse_time(txt)
        if got != want:
            print(f"FAIL parse_time({txt!r}) -> {got} (want {want})"); ok = False
    # selector gap-fill: XIV, XV, [XVI missing], XVII -> fills 16
    class _Fake:
        pass
    import ocr_read as _o
    orig = _o.read_all
    try:
        _o.read_all = lambda img, *a, **k: [("XIV", (251, 1278), 0.7), ("XV", (489, 1278), 0.6),
                                            ("XVII", (961, 1278), 0.6)]
        tiers = [t for t, _x in selector_tiers(_Fake())]
        if tiers != [14, 15, 16, 17]:
            print(f"FAIL selector_tiers gap-fill -> {tiers}"); ok = False
    finally:
        _o.read_all = orig

    # record round-trip: upsert into a temp db, then re-read the row
    with tempfile.TemporaryDirectory() as d:
        tdb = os.path.join(d, "v.db")
        tjs = os.path.join(d, "t.jsonl")
        info = {"tier": None, "name": "Steel Helepolis", "own": 20280000,
                "cost": {"food": None, "wood": 3300000000, "stone": 9800000000, "ore": 3300000000, "gold": 343000000},
                "qty": None, "train_seconds": 14665080, "instant_gems": 228825}
        record("workshop", 16, info, db=tdb, jsonl=tjs, ts=1.0)
        info["own"] = 20290000
        record("workshop", 16, info, db=tdb, jsonl=tjs, ts=2.0)   # upsert same troop
        conn = sqlite3.connect(tdb)
        rows = conn.execute("select building,tier,name,own,cost_wood from troops").fetchall()
        conn.close()
        if rows != [("workshop", 16, "Steel Helepolis", 20290000, 3300000000)]:
            print(f"FAIL record upsert -> {rows}"); ok = False
        if record("x", 1, {"name": None}, db=tdb, jsonl=tjs) is not False:
            print("FAIL record(no name) not False"); ok = False
        if sum(1 for _ in open(tjs)) != 2:
            print("FAIL jsonl line count"); ok = False

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] != "--selftest":
        import cv2
        import json
        img = cv2.imread(sys.argv[1])
        print("tiers:", selector_tiers(img))
        print(json.dumps(read_train_screen(img), indent=2))
    else:
        raise SystemExit(0 if _selftest() else 1)
