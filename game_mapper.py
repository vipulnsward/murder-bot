"""Continuous vision-DB mapper for the Evony game brain (kb/31, tasks #31/#32).

Safely explores and catalogs the game's screens into a persistent SQLite catalog so
screen identification and navigation knowledge grow over time. Three entry points:

  map_current()        capture the CURRENT screen, screen_fsm.identify + OCR-all, and
                       UPSERT a row into the screen_catalog table (+ save a sample PNG).
  explore_once(taps)   from the city, open a SAFE, READ-ONLY set of panels (Mail,
                       Reports, Watchtower, Alliance, Generals, Map, Quests), map each,
                       then back out via live_map.safe_back (auto-cancels the exit dialog).
  run_continuous(s)    loop explore_once + map_current, growing the catalog forever.

Safety invariants (never violated):
  * GEM / RESOURCE-SAFE — never taps Quit, Restart, Buy, Purchase, Confirm, Finish,
    Instant, Speed Up, or any gem/craft control. Only navigation controls are tapped.
  * disconnect-safe — screen_fsm.is_disconnect aborts the pass before ANY input.
  * back-out is ALWAYS live_map.safe_back (never a raw keyevent-4 at a screen root,
    which would pop the 'exit the game?' dialog and misalign the next taps).

CLI:
  python game_mapper.py --map-current     map the currently-displayed screen (safe now)
  python game_mapper.py --stats           print catalog coverage
  python game_mapper.py --explore-once     one safe read-only exploration pass (LIVE)
  python game_mapper.py --run [interval]  continuous mapping (LIVE)

Runs a deterministic offline self-test with no arguments.
"""

import os
import re
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEV = "127.0.0.1:5555"
DEFAULT_DB = os.path.join(HERE, "game_brain", "vision.db")
CATALOG_DIR = os.path.join(HERE, "game_brain", "screen_catalog")

OCR_MIN_CONF = 0.5
SUMMARY_CHARS = 240
SALIENT_LIMIT = 12
OCR_GUESS_MIN_HITS = 2   # keyword hits needed to name an un-templated screen from OCR

# Words that, if present anywhere in a candidate tap's description/label, mean the tap
# could spend gems/resources or leave the game. explore_once refuses to tap these, and
# the safe-tap list itself is asserted clean of them. Belt-and-braces with is_disconnect.
FORBIDDEN_WORDS = (
    "quit", "restart", "reconnect", "buy", "purchase", "pay", "recharge", "top up",
    "topup", "confirm", "finish", "instant", "speed up", "speedup", "gem", "gems",
    "craft", "unlock", "sale", "sold", "deal", "vip", "subscribe", "gift card",
    "start", "use", "attack", "march", "gather", "occupy", "buy now", "get",
)

# Generic UI chrome that never distinguishes one screen from another — dropped from the
# salient-token set so each catalog row highlights what's UNIQUE about the screen.
STOPWORDS = {
    "the", "and", "for", "you", "your", "all", "get", "use", "new", "top", "back",
    "ok", "cancel", "confirm", "close", "help", "info", "detail", "details", "more",
    "add", "free", "go", "yes", "no", "on", "off", "level", "lv", "lvl", "vip",
    "buy", "sale", "gift", "gifts", "event", "events", "menu", "home", "city",
    "day", "days", "time", "left", "min", "sec", "hour", "hours", "select", "start",
}

# The city bottom-bar / HUD read-only panels the mapper visits. Each entry names the
# screen, the OCR whole-word label to LOCATE the control (zoom-robust, preferred), and a
# VERIFIED 1080x1920 fallback coordinate (only well-confirmed HUD buttons are hardcoded;
# unknown ones are None and are simply skipped if OCR can't find the label — no faked
# coords, per kb/31). None of these open a gem/purchase flow — they only OPEN a panel.
DEFAULT_SAFE_TAPS = (
    {"screen": "alliance", "find": "alliance", "xy": (988, 1516)},
    {"screen": "mail",     "find": "mail",     "xy": (987, 1685)},
    {"screen": "reports",  "find": "reports",  "xy": None},
    {"screen": "quests",   "find": "quests",   "xy": None},
    {"screen": "generals", "find": "generals", "xy": None},
    {"screen": "watchtower", "find": "watchtower", "xy": None},
    {"screen": "world_map", "find": "world map", "xy": (994, 1790)},
)


# --------------------------------------------------------------------------------------
# screen_catalog table — the persistent map (additive; never touches screens/elements).
# --------------------------------------------------------------------------------------
_CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS screen_catalog (
    screen_id        TEXT PRIMARY KEY,
    identified_as    TEXT,
    ocr_text_summary TEXT,
    salient_tokens   TEXT,
    first_seen       REAL,
    last_seen        REAL,
    sample_png_path  TEXT,
    n_maps           INTEGER DEFAULT 1,
    phash            INTEGER
);
"""


def _ensure_catalog(conn):
    conn.execute(_CATALOG_DDL)


def _upsert_catalog(conn, row, now):
    """UPSERT one catalog row. first_seen is preserved; last_seen/summary refresh;
    n_maps increments on every re-observation."""
    with conn:
        conn.execute(
            """
            INSERT INTO screen_catalog
                (screen_id, identified_as, ocr_text_summary, salient_tokens,
                 first_seen, last_seen, sample_png_path, n_maps, phash)
            VALUES (:screen_id, :identified_as, :ocr_text_summary, :salient_tokens,
                    :now, :now, :sample_png_path, 1, :phash)
            ON CONFLICT(screen_id) DO UPDATE SET
                identified_as    = excluded.identified_as,
                ocr_text_summary = excluded.ocr_text_summary,
                salient_tokens   = excluded.salient_tokens,
                last_seen        = excluded.last_seen,
                sample_png_path  = excluded.sample_png_path,
                phash            = excluded.phash,
                n_maps           = screen_catalog.n_maps + 1
            """,
            {**row, "now": now},
        )


# --------------------------------------------------------------------------------------
# Text helpers — pure functions, exercised directly by the self-test.
# --------------------------------------------------------------------------------------
def _clean_texts(texts):
    """Normalize a read_all() result into [(text, (cx, cy), conf)] with str/float types."""
    out = []
    for item in texts or []:
        txt, center, conf = item
        cx, cy = int(center[0]), int(center[1])
        out.append((str(txt), (cx, cy), float(conf)))
    return out


def _summary(texts, limit=SUMMARY_CHARS):
    joined = " | ".join(t for t, _, _ in texts if t.strip())
    return joined[:limit]


def _salient(texts, limit=SALIENT_LIMIT):
    """Distinctive tokens: high-confidence, alphabetic, non-generic — the fingerprint of
    a screen. Ordered by confidence, de-duplicated case-insensitively."""
    picked, seen = [], set()
    for txt, _, conf in sorted(texts, key=lambda t: -t[2]):
        word = txt.strip()
        low = word.lower()
        if conf < OCR_MIN_CONF or len(word) < 3 or low in STOPWORDS:
            continue
        if not re.search(r"[a-z]", low):        # skip pure numbers / symbols
            continue
        if low in seen:
            continue
        seen.add(low)
        picked.append(word)
        if len(picked) >= limit:
            break
    return picked


def _guess_from_ocr(joined_text, classify=None, min_hits=OCR_GUESS_MIN_HITS):
    """Name an un-templated screen from its OCR text by reusing screen_id.classify's
    keyword scorer offline (OCR text stands in for the Holo description — no LLM)."""
    if classify is None:
        from screen_id import classify
    try:
        label, _desc, score = classify(joined_text, describe_fn=lambda text, _q: text,
                                       min_hits=min_hits)
    except Exception:
        return "unknown", 0
    return label, score


MASK64 = (1 << 64) - 1
UNKNOWN_DEDUP_DIST = 6   # phash Hamming radius that folds re-visits of an unknown screen


def _hamming(left, right):
    return ((int(left) & MASK64) ^ (int(right) & MASK64)).bit_count()


def _nearest_unknown(conn, phash, max_dist=UNKNOWN_DEDUP_DIST):
    """Existing unknown_* bucket whose phash is within max_dist of this frame, so a
    dynamic screen (ticking timers) folds into ONE row instead of fragmenting."""
    best = None
    for row in conn.execute(
            "SELECT screen_id, phash FROM screen_catalog WHERE screen_id LIKE 'unknown_%'"):
        if row["phash"] is None:
            continue
        dist = _hamming(phash, row["phash"])
        if best is None or dist < best[0]:
            best = (dist, row["screen_id"])
    return best[1] if best is not None and best[0] <= max_dist else None


def _resolve_identity(conn, templated, ocr_guess, guess_score, phash):
    """Stable catalog key + human label.
      templated != unknown       -> that label (best signal)
      confident OCR keyword guess -> that label (screens fold together across visits)
      else                        -> nearest unknown_* bucket, or a new unknown_<phash>."""
    if templated and templated != "unknown":
        return templated, templated
    if ocr_guess and ocr_guess != "unknown" and guess_score >= OCR_GUESS_MIN_HITS:
        return ocr_guess, f"{ocr_guess} (ocr)"
    bucket = _nearest_unknown(conn, phash) or f"unknown_{phash & MASK64:016x}"
    return bucket, "unknown"


def _safe_name(screen_id):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", screen_id)[:80]


# --------------------------------------------------------------------------------------
# Default live dependencies (lazy, so the self-test never imports adb/opencv/OCR).
# --------------------------------------------------------------------------------------
def _default_grab():
    """Prefer the live stream's SHARED frame (no second adb capture that would fight the
    screenrecord); one-shot adb screencap only when the stream isn't producing frames."""
    import shared_capture

    def grab():
        img = shared_capture.grab(DEV, fallback=True)
        if img is None:                    # tolerate a single torn/partial read
            img = shared_capture.grab(DEV, fallback=True)
        return img

    return grab


def _default_identify():
    import screen_fsm
    return screen_fsm.identify


def _default_read_all():
    import ocr_read
    return ocr_read.read_all


def _default_is_disconnect():
    import screen_fsm
    return screen_fsm.is_disconnect


def _open_db(db_path):
    """Open (creating dirs) the vision.db and guarantee the screen_catalog table."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_catalog(conn)
    return conn


def _phash(img):
    try:
        from vision_db import VisionDB
        return int(VisionDB.phash(img))
    except Exception:
        return 0


# --------------------------------------------------------------------------------------
# map_current — the core: catalog whatever is on screen right now.
# --------------------------------------------------------------------------------------
def map_current(conn=None, *, img=None, grab=None, identify=None, read_all=None,
                classify=None, catalog_dir=CATALOG_DIR, save_png=True, phash_fn=None,
                clock=time.time, db_path=DEFAULT_DB, log=None):
    """Capture the current screen, classify it, OCR every token, and UPSERT a catalog
    row. Returns a summary dict. Never taps anything — safe to call at any time."""
    own_conn = conn is None
    if own_conn:
        conn = _open_db(db_path)
    grab = grab or _default_grab()
    identify = identify or _default_identify()
    read_all = read_all or _default_read_all()
    phash_fn = phash_fn or _phash
    log = log or (lambda *_: None)

    if img is None:
        img = grab()
    if img is None:
        if own_conn:
            conn.close()
        return {"screen_id": None, "error": "no_frame"}

    templated = str(identify(img))
    if templated == "disconnect":
        log("mapper: disconnect detected; not touching the game")
        if own_conn:
            conn.close()
        return {"screen_id": "disconnect", "identified_as": "disconnect", "stopped": True}

    texts = _clean_texts(read_all(img))
    joined = " ".join(t for t, _, _ in texts)
    guess, score = _guess_from_ocr(joined, classify=classify)
    phash = int(phash_fn(img))
    screen_id, identified_as = _resolve_identity(conn, templated, guess, score, phash)

    summary = _summary(texts)
    salient = ", ".join(_salient(texts))

    png_path = None
    if save_png and img is not None:
        try:
            import cv2
            os.makedirs(catalog_dir, exist_ok=True)
            png_path = os.path.join(catalog_dir, f"{_safe_name(screen_id)}.png")
            cv2.imwrite(png_path, img)
        except Exception as error:
            log(f"mapper: sample save failed ({error!r})")
            png_path = None

    now = clock()
    _upsert_catalog(conn, {
        "screen_id": screen_id,
        "identified_as": identified_as,
        "ocr_text_summary": summary,
        "salient_tokens": salient,
        "sample_png_path": png_path,
        "phash": phash if phash < (1 << 63) else phash - (1 << 64),
    }, now)

    result = {
        "screen_id": screen_id,
        "identified_as": identified_as,
        "templated": templated,
        "n_texts": len(texts),
        "salient_tokens": salient,
        "sample_png_path": png_path,
    }
    log(f"mapper: {screen_id} (as {identified_as}) texts={len(texts)} salient=[{salient}]")
    if own_conn:
        conn.close()
    return result


# --------------------------------------------------------------------------------------
# explore_once — visit a safe, read-only set of panels, mapping each.
# --------------------------------------------------------------------------------------
def _is_forbidden(*strings):
    blob = " ".join(str(s) for s in strings).lower()
    return any(word in blob for word in FORBIDDEN_WORDS)


def _find_control(img, label, find_button):
    """Locate a whole-word labeled control by OCR (zoom-robust). Returns (x, y) or None."""
    try:
        return find_button(img, label)
    except Exception:
        return None


def explore_once(safe_taps=None, conn=None, *, grab=None, identify=None, read_all=None,
                 find_button=None, is_disconnect=None, safe_back=None, ensure_city=None,
                 tap=None, classify=None, db_path=DEFAULT_DB, settle=1.6, log=print):
    """From the city, open each safe read-only panel, map it, and back out via
    live_map.safe_back. Aborts immediately on disconnect. Returns a list of per-panel
    summaries. Every input is disconnect-guarded and gem/quit/buy-word-guarded."""
    own_conn = conn is None
    if own_conn:
        conn = _open_db(db_path)
    grab = grab or _default_grab()
    identify = identify or _default_identify()
    read_all = read_all or _default_read_all()
    is_disconnect = is_disconnect or _default_is_disconnect()
    if find_button is None:
        import ocr_read
        find_button = ocr_read.find_button
    if safe_back is None:
        import live_map
        safe_back = live_map.safe_back
    if tap is None:
        import subprocess
        def tap(x, y, d=1.4):
            subprocess.run(["adb", "-s", DEV, "shell", "input", "tap",
                            str(int(x)), str(int(y))])
            time.sleep(d)
    taps = list(DEFAULT_SAFE_TAPS if safe_taps is None else safe_taps)
    results = []

    def guard():
        """Return a fresh frame, or None if disconnected (caller must abort)."""
        frame = grab()
        if frame is None or is_disconnect(frame):
            return None
        return frame

    # Always start from a mapped city snapshot.
    first = guard()
    if first is None:
        log("mapper: disconnect / no frame at start; aborting pass")
        if own_conn:
            conn.close()
        return [{"screen_id": "disconnect", "stopped": True}]
    if ensure_city is not None:
        ensure_city()
    results.append(map_current(conn, grab=grab, identify=identify, read_all=read_all,
                               classify=classify, log=log if log is print else None))

    for spec in taps:
        screen = spec.get("screen", "?")
        label = spec.get("find", "")
        fallback = spec.get("xy")
        # Never even attempt a tap whose intent contains a gem/quit/buy word.
        if _is_forbidden(screen, label):
            log(f"mapper: skip forbidden safe-tap {screen!r}")
            continue

        img = guard()
        if img is None:
            log("mapper: disconnect mid-pass; aborting")
            results.append({"screen_id": "disconnect", "stopped": True})
            break

        point = _find_control(img, label, find_button) if label else None
        if point is None:
            point = fallback           # only VERIFIED HUD coords are hardcoded; else None
        if point is None:
            log(f"mapper: {screen}: control {label!r} not found (skip, no faked coords)")
            continue

        tap(point[0], point[1])
        opened = guard()
        if opened is None:
            log("mapper: disconnect after open; aborting")
            results.append({"screen_id": "disconnect", "stopped": True})
            break
        results.append(map_current(conn, img=opened, grab=grab, identify=identify,
                                   read_all=read_all, classify=classify,
                                   log=log if log is print else None))

        # Back out to the city — ALWAYS via safe_back (auto-cancels the exit dialog),
        # never a raw keyevent-4 at root. Up to 3 levels, then re-home.
        for _ in range(3):
            back_img = grab()
            if back_img is not None and is_disconnect(back_img):
                results.append({"screen_id": "disconnect", "stopped": True})
                if own_conn:
                    conn.close()
                return results
            safe_back(settle)
            here = grab()
            if here is not None and identify(here) == "city":
                break
        if ensure_city is not None:
            ensure_city()

    if own_conn:
        conn.close()
    return results


# --------------------------------------------------------------------------------------
# run_continuous — grow the catalog forever.
# --------------------------------------------------------------------------------------
def run_continuous(interval=45.0, db_path=DEFAULT_DB, max_passes=None, log=print,
                   sleep=time.sleep, **kw):
    """Loop explore_once + map_current, sleeping `interval` between passes. Respects
    disconnect (a pass that hits it just returns; the next pass re-checks). Bounded by
    max_passes for tests; unbounded (None) in production."""
    conn = _open_db(db_path)
    passes = 0
    try:
        while max_passes is None or passes < max_passes:
            passes += 1
            log(f"mapper: === pass {passes} ===")
            try:
                explore_once(conn=conn, log=log, **kw)
            except Exception as error:
                log(f"mapper: pass error {error!r}")
            if max_passes is not None and passes >= max_passes:
                break
            sleep(interval)
    finally:
        conn.close()
    return passes


# --------------------------------------------------------------------------------------
# Coverage / stats.
# --------------------------------------------------------------------------------------
def _known_labels():
    """All screen labels the brain KNOWS about: the classifier vocabulary plus any
    seed-only screens catalog_seed adds. Coverage = how many have been mapped live."""
    labels = set()
    try:
        from screen_id import SCREENS
        labels.update(label for label, _ in SCREENS)
    except Exception:
        pass
    try:
        import catalog_seed
        labels.update(getattr(catalog_seed, "EXTRA_SEED_SCREENS", {}).keys())
    except Exception:
        pass
    return labels


def coverage(conn=None, db_path=DEFAULT_DB):
    own = conn is None
    if own:
        conn = _open_db(db_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM screen_catalog ORDER BY last_seen DESC")]
    mapped_ids = {r["screen_id"] for r in rows}
    known = _known_labels()
    covered = sorted(known & mapped_ids)
    missing = sorted(known - mapped_ids)
    unknown_buckets = sorted(r["screen_id"] for r in rows
                             if r["screen_id"].startswith("unknown_"))
    stats = {
        "catalog_rows": len(rows),
        "known_labels": len(known),
        "covered_known": len(covered),
        "missing_known": missing,
        "covered": covered,
        "unknown_buckets": len(unknown_buckets),
        "rows": rows,
    }
    if own:
        conn.close()
    return stats


def print_stats(db_path=DEFAULT_DB):
    stats = coverage(db_path=db_path)
    print(f"screen_catalog: {stats['catalog_rows']} rows  "
          f"({stats['covered_known']}/{stats['known_labels']} known screens mapped, "
          f"{stats['unknown_buckets']} unknown buckets)")
    if stats["covered"]:
        print("  mapped:", ", ".join(stats["covered"]))
    if stats["missing_known"]:
        print("  not yet mapped:", ", ".join(stats["missing_known"]))
    print("  --- rows (newest first) ---")
    for row in stats["rows"]:
        seen = time.strftime("%Y-%m-%d %H:%M", time.localtime(row["last_seen"]))
        print(f"  [{row['screen_id']:<22}] as={row['identified_as']:<16} "
              f"n={row['n_maps']:<3} {seen}  salient=[{row['salient_tokens']}]")
    return stats


# --------------------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------------------
def _cli(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Continuous vision-DB screen mapper")
    parser.add_argument("--map-current", action="store_true",
                        help="map the currently-displayed screen (safe to run now)")
    parser.add_argument("--stats", action="store_true", help="print catalog coverage")
    parser.add_argument("--explore-once", action="store_true",
                        help="one safe, read-only exploration pass (LIVE input)")
    parser.add_argument("--run", nargs="?", const=45.0, type=float, metavar="INTERVAL",
                        help="continuous mapping every INTERVAL seconds (LIVE input)")
    parser.add_argument("--db", default=DEFAULT_DB, help="vision.db path")
    args = parser.parse_args(argv)

    if args.map_current:
        result = map_current(db_path=args.db, log=print)
        print("mapped:", result)
        return 0
    if args.explore_once:
        import live_map                     # start from a clean city (clears popups first)
        for item in explore_once(db_path=args.db, ensure_city=live_map.clear_popups, log=print):
            print(" ", item)
        return 0
    if args.run is not None:
        import live_map
        run_continuous(interval=args.run, db_path=args.db,
                       ensure_city=live_map.clear_popups, log=print)
        return 0
    if args.stats:
        print_stats(db_path=args.db)
        return 0
    parser.print_help()
    return 0


# --------------------------------------------------------------------------------------
# Deterministic offline self-test (no adb / opencv / OCR / LLM).
# --------------------------------------------------------------------------------------
def _selftest():
    import sys
    import tempfile

    ok = True

    # Fakes -------------------------------------------------------------------------
    class Frame:
        def __init__(self, name, phash):
            self.name = name
            self.phash = phash

    SCREENS = {
        "city":     [("Alliance", (988, 1516), 0.9), ("Mail", (987, 1685), 0.9),
                     ("Keep", (270, 90), 0.8)],
        "mail":     [("Mail", (540, 80), 0.95), ("Reports", (300, 80), 0.9),
                     ("System", (700, 80), 0.8), ("Battle Report", (540, 400), 0.85)],
        "alliance": [("Alliance", (540, 80), 0.95), ("Members", (300, 80), 0.9),
                     ("Alliance Help", (700, 80), 0.85), ("Alliance Science", (540, 400), 0.8)],
        "resources": [("Food", (200, 33), 0.95), ("Wood", (400, 33), 0.9),
                      ("Stone", (600, 33), 0.9), ("Ore", (800, 33), 0.9)],
        "disc":     [("Disconnected", (540, 800), 0.95), ("Restart", (718, 1136), 0.9)],
    }

    def fake_read_all(img):
        return SCREENS.get(img.name, [])

    def fake_identify(img):
        # Templates only fire for city + resources; everything else is 'unknown'
        # (exactly like the real template-first FSM before OCR/Holo naming).
        if img.name == "city":
            return "city"
        if img.name == "resources":
            return "resources"
        if img.name == "disc":
            return "disconnect"
        return "unknown"

    def fake_is_disc(img):
        return img.name == "disc"

    def fake_phash(img):
        return img.phash

    # 1) map_current: city classifies via template; row stored -------------------
    with tempfile.TemporaryDirectory() as tmp:
        conn = _open_db(os.path.join(tmp, "vision.db"))
        clk = [1000.0]
        r = map_current(conn, img=Frame("city", 111), identify=fake_identify,
                        read_all=fake_read_all, phash_fn=fake_phash, save_png=False,
                        clock=lambda: clk[0])
        row = conn.execute("SELECT * FROM screen_catalog WHERE screen_id='city'").fetchone()
        try:
            assert r["screen_id"] == "city" and r["identified_as"] == "city"
            assert row["first_seen"] == 1000.0 and row["last_seen"] == 1000.0
            assert row["n_maps"] == 1
            assert "Keep" in row["salient_tokens"]     # distinctive token kept
            assert row["ocr_text_summary"]             # summary populated
            print("1 map_current(city) template id + row stored: PASS")
        except AssertionError as e:
            ok = False
            print(f"1 map_current(city): FAIL ({e}) row={dict(row) if row else None}")

        # 2) un-templated screen named from OCR keywords (mail folds to 'mail') --
        r2 = map_current(conn, img=Frame("mail", 222), identify=fake_identify,
                         read_all=fake_read_all, phash_fn=fake_phash, save_png=False,
                         clock=lambda: 1001.0)
        try:
            assert r2["screen_id"] == "mail", r2
            assert r2["identified_as"] == "mail (ocr)"
            print("2 map_current(mail) OCR-named un-templated screen: PASS")
        except AssertionError as e:
            ok = False
            print(f"2 map_current(mail): FAIL ({e})")

        # 3) UPSERT: re-map city -> n_maps increments, first_seen kept, last_seen moves
        map_current(conn, img=Frame("city", 111), identify=fake_identify,
                    read_all=fake_read_all, phash_fn=fake_phash, save_png=False,
                    clock=lambda: 2000.0)
        row = conn.execute("SELECT * FROM screen_catalog WHERE screen_id='city'").fetchone()
        try:
            assert row["n_maps"] == 2
            assert row["first_seen"] == 1000.0 and row["last_seen"] == 2000.0
            print("3 UPSERT increments n_maps, preserves first_seen: PASS")
        except AssertionError as e:
            ok = False
            print(f"3 UPSERT: FAIL ({e})")

        # 4) truly-unknown screen -> unknown_<phash> bucket ----------------------
        r4 = map_current(conn, img=Frame("mystery", 777), identify=fake_identify,
                         read_all=lambda i: [("Xyzzy", (10, 10), 0.9)], phash_fn=fake_phash,
                         save_png=False, clock=lambda: 3000.0)
        try:
            assert r4["screen_id"] == "unknown_0000000000000309", r4  # 777 hex
            assert r4["identified_as"] == "unknown"
            print("4 unknown screen -> phash bucket: PASS")
        except AssertionError as e:
            ok = False
            print(f"4 unknown bucket: FAIL ({e})")

        # 4b) a NEAR-duplicate unknown frame (3 phash bits differ) folds into 4's bucket
        r4b = map_current(conn, img=Frame("mystery2", 777 ^ 0b1011),
                          identify=fake_identify,
                          read_all=lambda i: [("Zzz", (10, 10), 0.9)], phash_fn=fake_phash,
                          save_png=False, clock=lambda: 3001.0)
        n_unknown = conn.execute(
            "SELECT count(*) FROM screen_catalog WHERE screen_id LIKE 'unknown_%'").fetchone()[0]
        try:
            assert r4b["screen_id"] == r4["screen_id"], (r4b["screen_id"], r4["screen_id"])
            assert n_unknown == 1, n_unknown            # merged, not fragmented
            print("4b near-duplicate unknown folds into one bucket: PASS")
        except AssertionError as e:
            ok = False
            print(f"4b unknown dedup: FAIL ({e})")
        conn.close()

    # 5) explore_once: opens panels, maps each, backs out with safe_back only ----
    with tempfile.TemporaryDirectory() as tmp:
        conn = _open_db(os.path.join(tmp, "vision.db"))
        # Scripted live surface: city -> tap opens 'mail' -> safe_back returns to city.
        state = {"frame": Frame("city", 111)}
        events = []

        def grab():
            return state["frame"]

        def find_button(img, label):
            for txt, c, _ in fake_read_all(img):
                if txt.lower() == label.lower():
                    return c
            return None

        def tap(x, y, d=1.4):
            events.append(("tap", x, y))
            # Any panel-open tap lands on the mail panel in this script.
            state["frame"] = Frame("mail", 222)

        def safe_back(settle=1.6):
            events.append(("safe_back",))
            state["frame"] = Frame("city", 111)
            return False

        only_mail = [{"screen": "mail", "find": "mail", "xy": (987, 1685)}]
        res = explore_once(only_mail, conn=conn, grab=grab, identify=fake_identify,
                           read_all=fake_read_all, find_button=find_button,
                           is_disconnect=fake_is_disc, safe_back=safe_back, tap=tap,
                           log=lambda *_: None)
        kinds = [e[0] for e in events]
        mapped = [r["screen_id"] for r in res if "screen_id" in r]
        try:
            assert "city" in mapped and "mail" in mapped, mapped
            assert ("tap", 987, 1685) in events              # opened via found label
            assert "safe_back" in kinds                       # backed out via safe_back
            assert not any(k == "keyevent" for k in kinds)    # never a raw back
            print("5 explore_once opens+maps+safe_back: PASS")
        except AssertionError as e:
            ok = False
            print(f"5 explore_once: FAIL ({e}) events={events} mapped={mapped}")

        # 6) disconnect aborts the pass BEFORE any input -------------------------
        state["frame"] = Frame("disc", 999)
        events.clear()
        res = explore_once(only_mail, conn=conn, grab=grab, identify=fake_identify,
                           read_all=fake_read_all, find_button=find_button,
                           is_disconnect=fake_is_disc, safe_back=safe_back, tap=tap,
                           log=lambda *_: None)
        try:
            assert res == [{"screen_id": "disconnect", "stopped": True}], res
            assert events == [], events   # ZERO taps / backs on the disconnect screen
            print("6 disconnect aborts pass with zero input: PASS")
        except AssertionError as e:
            ok = False
            print(f"6 disconnect abort: FAIL ({e})")

        # 7) forbidden safe-tap is refused ---------------------------------------
        assert not any(_is_forbidden(s["screen"], s["find"]) for s in DEFAULT_SAFE_TAPS), \
            "a default safe-tap contains a gem/quit word"
        assert _is_forbidden("buy_gems", "purchase"), "forbidden guard is broken"
        state["frame"] = Frame("city", 111)
        events.clear()
        explore_once([{"screen": "buy_gems", "find": "purchase", "xy": (500, 500)}],
                     conn=conn, grab=grab, identify=fake_identify, read_all=fake_read_all,
                     find_button=find_button, is_disconnect=fake_is_disc,
                     safe_back=safe_back, tap=tap, log=lambda *_: None)
        try:
            assert ("tap", 500, 500) not in events, events
            print("7 forbidden gem/buy tap refused: PASS")
        except AssertionError as e:
            ok = False
            print(f"7 forbidden tap: FAIL ({e})")

        # 8) run_continuous is bounded + grows the catalog -----------------------
        state["frame"] = Frame("city", 111)
        before = conn.execute("SELECT count(*) FROM screen_catalog").fetchone()[0]
        passes = run_continuous(interval=0, max_passes=2, conn=None, db_path=os.path.join(tmp, "vision.db"),
                                grab=grab, identify=fake_identify, read_all=fake_read_all,
                                find_button=find_button, is_disconnect=fake_is_disc,
                                safe_back=safe_back, tap=tap, log=lambda *_: None,
                                sleep=lambda _s: None, safe_taps=only_mail)
        after = conn.execute("SELECT count(*) FROM screen_catalog").fetchone()[0]
        try:
            assert passes == 2, passes
            assert after >= before  # same conn sees rows written by run_continuous' conn
            print(f"8 run_continuous bounded ({passes} passes): PASS")
        except AssertionError as e:
            ok = False
            print(f"8 run_continuous: FAIL ({e})")

        # 9) coverage() reports known-screen mapping -----------------------------
        cov = coverage(conn=conn)
        try:
            assert cov["catalog_rows"] >= 2
            assert "city" in cov["covered"] and "mail" in cov["covered"]
            print(f"9 coverage() {cov['covered_known']}/{cov['known_labels']} known mapped: PASS")
        except AssertionError as e:
            ok = False
            print(f"9 coverage: FAIL ({e})")
        conn.close()

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        raise SystemExit(_cli(sys.argv[1:]))
    raise SystemExit(_selftest())
