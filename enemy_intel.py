"""enemy_intel — LIVE ENEMY RECON: learn about everyone.

Feeds the "replicate and learn everything about everyone" pillar. Populates the
Postgres `enemies` table (name, alliance, battles, my_wins, my_losses, max_troops,
coords, buffs, generals, threat, last_seen) from three sources:

  scan_reports()          re-mine report_extracts for opponents (offline, no emulator)
  scout_keep_on_screen()  OCR an already-open keep / player-info panel (live, read-only)
  read_alliance_roster()  page my alliance (NFG) Members panel (live, read-only)

SAFETY GUARANTEES (non-negotiable, same discipline as nav/live_map):
  * READ-ONLY + GEM/RESOURCE-SAFE. Never taps Attack / Scout-with-troops / Buy /
    Confirm / Start / Quit / Instant-Finish or any gem/craft/spend control. The
    only taps issued are navigation: the in-game BACK ARROW (nav.Nav.back, 80,72),
    the city globe, Cancel-on-exit, and opening/paging read-only panels
    (Alliance -> Members). Backing out NEVER uses raw `adb keyevent 4` — it always
    goes through nav.Nav (back arrow / ensure_city), so a bare-city Back can't pop
    the exit dialog.
  * DISCONNECT-SAFE. The moment screen_fsm.is_disconnect() is seen, live functions
    ABORT and return. They never reclaim (that needs explicit human consent).
  * LOOP-SAFE. Live commands PAUSE the autonomous loop (SIGSTOP on the pid in
    /tmp/video_report_loop.pid) before touching the emulator and CONT it after,
    so we never fight the loop for adb. --scan-reports / --stats touch only Postgres
    and never pause anything.

CLI:
  python enemy_intel.py --scan-reports   # offline: mine report_extracts -> enemies
  python enemy_intel.py --stats          # offline: how many players known, by alliance/threat
  python enemy_intel.py --alliance       # LIVE: read my NFG roster (pauses the loop)
  python enemy_intel.py --scout-screen   # LIVE: OCR a keep panel if one is open
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DB = os.environ.get("MURDERBOT_DB", "murderbot")
DEV = os.environ.get("EVONY_DEVICE", "127.0.0.1:5555")
LOOP_PID_FILE = "/tmp/video_report_loop.pid"

MY_NAME = "NeolsTlatoani"
MY_ALLIANCE = "NFG"

TROOP_TYPES = ("ground", "ranged", "mounted", "siege")

MONSTER_SUBSTRINGS = (
    "lost power", "holy palace", "killed rate", "chest", "clue", "bag",
    "speedup", "compendium", "troop", "material", "subordinate", "reinforcement",
    "of speedup", "tremendous", "tactical", "silk road", "imperial sphinx",
    "supreme warlord", "senior", "junior", "epic ", "legendary ", "elite ",
)
MONSTER_NAMES = {
    "leviathan", "sphinx", "cerberus", "kraken", "phoenix", "stymphalian bird",
    "azazel", "warlord", "hydra", "minotaur", "gryphon", "griffin", "gorgon",
    "medusa", "behemoth", "spartacus", "redcoat", "hannibal", "kingdom",
    "goliath", "typhon", "manticore", "yamata", "orochi", "fenrir", "jormungand",
    "necromancer", "aresburg", "viking", "dragon", "wildkin", "bird",
}


def _conn():
    return psycopg2.connect(dbname=DB)


def clean_name(raw):
    """Normalize a player name: drop (Awakened)/rank decorations, trailing +/*/star,
    and collapse whitespace. Returns '' for junk."""
    if not raw:
        return ""
    s = str(raw)
    s = re.sub(r"\(awakened\)", "", s, flags=re.I)
    s = re.sub(r"[★☆*]+", "", s)
    s = s.strip().strip("+").strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_name_alliance(raw):
    """Parse '[TAG]Name' / '(TAG) Name' / bare 'Name' into (name, alliance|None).
    OCR-tolerant of a dropped opening bracket ('TAG]Name'). alliance uppercased."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    m = re.match(r"^\s*[\[\(【]?\s*([A-Za-z0-9]{2,5})\s*[\]\)】]\s*(.+)$", s)
    if m:
        alliance = m.group(1).strip()
        name = clean_name(m.group(2))
    else:
        alliance = None
        name = clean_name(s)
    if not name:
        return None, None
    return name, alliance


def is_junk_name(name):
    """True if `name` is a monster / event chest / OCR fragment, not a real player.
    Player names are single tokens up to ~15 letters; monster/event/reward labels are
    multi-word ('Subordinate City Clue') and OCR gibberish is over-long, so word-count
    and length caps catch the mangled cases substring matching misses."""
    if not name:
        return True
    low = name.lower().strip()
    letters = re.sub(r"[^a-z]", "", low)
    if len(letters) < 2:
        return True
    if len(letters) > 15:
        return True
    if len(low.split()) >= 3:
        return True
    if re.search(r"x\s*:?\s*\d|y\s*:?\s*\d", low):
        return True
    if low in MONSTER_NAMES:
        return True
    if any(sub in low for sub in MONSTER_SUBSTRINGS):
        return True
    if any(m in low for m in MONSTER_NAMES):
        return True
    return False


def _stat(stats, key, side):
    """Per-side scalar from the rich report stats shape; None for the simple shape."""
    if not isinstance(stats, dict):
        return None
    v = stats.get(key)
    if isinstance(v, dict):
        return v.get(side)
    return None


def _side_buffs(buffs, side):
    """Compact {troop_type: {hp,attack,defense}} for one side, or None."""
    if not isinstance(buffs, dict):
        return None
    out = {}
    for t in TROOP_TYPES:
        v = buffs.get(t)
        if isinstance(v, dict) and isinstance(v.get(side), dict):
            sd = {k: v[side][k] for k in ("hp", "attack", "defense")
                  if v[side].get(k) is not None}
            if sd:
                out[t] = sd
    return out or None


def _side_general(gen, side):
    """General name for one side from a main/assistant_general jsonb, or None."""
    if not isinstance(gen, dict):
        return None
    v = gen.get(side)
    if isinstance(v, dict):
        n = v.get("name")
        if n and isinstance(n, str) and n.strip():
            return clean_name(n) or n.strip()
    return None


def _to_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def scan_reports(conn=None, verbose=True, dry_run=False):
    """Re-mine report_extracts for opponents and UPSERT into enemies.

    Extends the already-seeded rows with troop counts (max_troops) and combat buffs
    (per-troop-type hp/attack/defense) + general names pulled from the stats/buffs/
    main_general/assistant_general jsonb columns. Idempotent: numeric intel merges via
    GREATEST, text/jsonb via COALESCE, so re-running never corrupts curated data.

    my_wins/my_losses are NOT inferred here (the report outcome/title perspective is
    ambiguous) — they stay curated. This only grows battle counts and enemy intel.
    Returns a summary dict.
    """
    own = conn is None
    conn = conn or _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT rid, title, outcome, coords, defender, attacker,
               stats, buffs, main_general, assistant_general, updated_at
        FROM report_extracts
    """)
    rows = cur.fetchall()

    name_to_alliance = {}
    for r in rows:
        for raw in (r["attacker"], r["defender"]):
            name, alliance = parse_name_alliance(raw)
            if name and alliance and not is_junk_name(name):
                name_to_alliance.setdefault(name, alliance)

    agg = {}
    skipped = 0
    for r in rows:
        for side, raw in (("attacker", r["attacker"]), ("defender", r["defender"])):
            name, alliance = parse_name_alliance(raw)
            if not name or is_junk_name(name):
                continue
            if alliance is None:
                alliance = name_to_alliance.get(name)
            if name == MY_NAME or (alliance and alliance.upper() == MY_ALLIANCE):
                continue
            key = (alliance or "?", name)
            a = agg.setdefault(key, {
                "name": name, "alliance": alliance or "?", "rids": set(),
                "max_troops": None, "buffs": None, "buffs_ts": None,
                "generals": None, "gen_ts": None, "coords": None,
                "level": None, "power": None, "last_seen": None,
            })
            a["rids"].add(r["rid"])
            ts = r["updated_at"]
            if ts and (a["last_seen"] is None or ts > a["last_seen"]):
                a["last_seen"] = ts

            troops = _to_int(_stat(r["stats"], "total_troops", side))
            if troops and (a["max_troops"] is None or troops > a["max_troops"]):
                a["max_troops"] = troops

            sb = _side_buffs(r["buffs"], side)
            if sb and (a["buffs_ts"] is None or (ts and ts >= a["buffs_ts"])):
                a["buffs"], a["buffs_ts"] = sb, ts

            main = _side_general(r["main_general"], side)
            asst = _side_general(r["assistant_general"], side)
            if (main or asst) and (a["gen_ts"] is None or (ts and ts >= a["gen_ts"])):
                a["generals"] = {k: v for k, v in (("main", main), ("assistant", asst)) if v}
                a["gen_ts"] = ts

            lvl = _to_int(_stat(r["stats"], "level", side))
            if lvl:
                a["level"] = lvl
            pwr = _to_int(_stat(r["stats"], "power", side))
            if pwr and (a["power"] is None or pwr > a["power"]):
                a["power"] = pwr

            if side == "defender" and r["coords"] and not a["coords"]:
                a["coords"] = r["coords"].strip()

    if dry_run:
        cur.execute("SELECT alliance, name FROM enemies")
        existing = {(r["alliance"], r["name"]) for r in cur.fetchall()}
        if verbose:
            print(f"scan_reports [DRY-RUN]: {len(rows)} reports scanned, "
                  f"{len(agg)} opponents derived (NO writes)")
            for (alliance, name), a in sorted(agg.items()):
                tag = "upd" if (alliance, name) in existing else "NEW"
                t = f"{a['max_troops']:,}" if a["max_troops"] else "-"
                nb = "buffs" if a["buffs"] else "-"
                print(f"  [{tag}] {alliance:>4} / {name:<18} battles={len(a['rids']):<2} "
                      f"max_troops={t:<16} {nb}")
        if own:
            conn.close()
        return {"reports": len(rows), "opponents": len(agg),
                "inserted": 0, "updated": 0, "dry_run": True,
                "opponent_keys": sorted(agg.keys())}

    wcur = conn.cursor()
    inserted = updated = 0
    results = []
    for (alliance, name), a in sorted(agg.items()):
        buffs_json = dict(a["buffs"] or {})
        if a["level"] is not None:
            buffs_json["_level"] = a["level"]
        if a["power"] is not None:
            buffs_json["_power"] = a["power"]
        wcur.execute("""
            INSERT INTO enemies (name, alliance, battles, my_wins, my_losses,
                                 max_troops, coords, buffs, generals, threat, last_seen)
            VALUES (%s, %s, %s, 0, 0, %s, %s, %s, %s, NULL, %s)
            ON CONFLICT (alliance, name) DO UPDATE SET
                battles    = GREATEST(enemies.battles, EXCLUDED.battles),
                max_troops = NULLIF(GREATEST(COALESCE(enemies.max_troops, 0),
                                             COALESCE(EXCLUDED.max_troops, 0)), 0),
                coords     = COALESCE(enemies.coords, EXCLUDED.coords),
                buffs      = COALESCE(EXCLUDED.buffs, enemies.buffs),
                generals   = COALESCE(EXCLUDED.generals, enemies.generals),
                threat     = COALESCE(enemies.threat, EXCLUDED.threat),
                last_seen  = GREATEST(COALESCE(enemies.last_seen, EXCLUDED.last_seen),
                                      COALESCE(EXCLUDED.last_seen, enemies.last_seen))
            RETURNING (xmax = 0) AS inserted
        """, (
            name, alliance, len(a["rids"]), a["max_troops"], a["coords"],
            psycopg2.extras.Json(buffs_json) if buffs_json else None,
            psycopg2.extras.Json(a["generals"]) if a["generals"] else None,
            a["last_seen"],
        ))
        was_insert = wcur.fetchone()[0]
        inserted += int(was_insert)
        updated += int(not was_insert)
        results.append((alliance, name, len(a["rids"]), a["max_troops"], was_insert))
    conn.commit()

    if verbose:
        print(f"scan_reports: {len(rows)} reports scanned, {skipped} skipped, "
              f"{len(agg)} opponents -> {inserted} inserted, {updated} updated")
        for alliance, name, battles, troops, ins in results:
            tag = "NEW" if ins else "upd"
            t = f"{troops:,}" if troops else "-"
            print(f"  [{tag}] {alliance:>4} / {name:<18} battles={battles:<2} max_troops={t}")

    if own:
        conn.close()
    return {"reports": len(rows), "opponents": len(agg),
            "inserted": inserted, "updated": updated, "results": results}


def upsert_player(conn, *, name, alliance, max_troops=None, coords=None,
                  buffs=None, generals=None, threat=None):
    """Idempotent upsert of one observed player (used by the live scouts).
    Fills intel via COALESCE/GREATEST; never clobbers curated W/L."""
    name = clean_name(name)
    if not name or is_junk_name(name):
        return False
    alliance = (alliance or "?").strip() or "?"
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO enemies (name, alliance, battles, my_wins, my_losses,
                             max_troops, coords, buffs, generals, threat, last_seen)
        VALUES (%s, %s, 0, 0, 0, %s, %s, %s, %s, %s, now())
        ON CONFLICT (alliance, name) DO UPDATE SET
            max_troops = NULLIF(GREATEST(COALESCE(enemies.max_troops, 0),
                                         COALESCE(EXCLUDED.max_troops, 0)), 0),
            coords    = COALESCE(EXCLUDED.coords, enemies.coords),
            buffs     = COALESCE(EXCLUDED.buffs, enemies.buffs),
            generals  = COALESCE(EXCLUDED.generals, enemies.generals),
            threat    = COALESCE(enemies.threat, EXCLUDED.threat),
            last_seen = now()
    """, (
        name, alliance, max_troops, coords,
        psycopg2.extras.Json(buffs) if buffs else None,
        psycopg2.extras.Json(generals) if generals else None,
        threat,
    ))
    return True


# --------------------------------------------------------------------------- #
# Live helpers (emulator). All backing-out routes through nav.Nav (never keyevent-4).
# --------------------------------------------------------------------------- #

class _ScoutCtx:
    """Minimal Ctx for nav.Nav: shared-frame capture + adb-input taps/swipes only.
    Deliberately NOT orchestrator.Ctx (whose .back() uses keyevent-4)."""

    def __init__(self, device=DEV):
        self.device = device

    def screencap(self):
        import shared_capture
        return shared_capture.grab_wait(self.device)

    def tap(self, x, y, d=0.3, label="", radius=10):
        subprocess.run(["adb", "-s", self.device, "shell", "input", "tap",
                        str(int(x)), str(int(y))])
        time.sleep(max(0.2, d))

    def swipe(self, x1, y1, x2, y2, ms=600, d=0.3):
        subprocess.run(["adb", "-s", self.device, "shell", "input", "swipe",
                        str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(ms))])
        time.sleep(max(0.3, d))


def _make_nav(device=DEV):
    import nav
    return nav.Nav(_ScoutCtx(device))


def safe_back(nav_obj):
    """The safe back primitive: tap the in-game BACK ARROW (80,72) via nav.Nav.back().
    Never a bare-city Android Back (which would open the exit dialog)."""
    nav_obj.back()


ALLIANCE_BTN = (988, 1516)
COORD_RE = re.compile(r"X\s*:?\s*0*\d+\s*[, ]\s*Y\s*:?\s*0*\d+", re.I)


def _grab(device=DEV):
    import shared_capture
    return shared_capture.grab_wait(device)


def _is_disconnected(img):
    import screen_fsm
    return img is not None and screen_fsm.is_disconnect(img)


def scout_keep_on_screen(conn=None, device=DEV, close_after=True):
    """If a keep / player-info panel is currently open, OCR name/alliance/power/
    keep-level/coords and UPSERT into enemies. READ-ONLY: reads whatever is on
    screen, never opens the panel by tapping a castle and never taps Attack/Scout.
    Backs out (safe_back) only when close_after and a panel was found.

    Returns a dict describing what was scouted (or why nothing was)."""
    import ocr_read
    own = conn is None
    img = _grab(device)
    if img is None:
        return {"ok": False, "reason": "no_frame"}
    if _is_disconnected(img):
        return {"ok": False, "reason": "disconnect", "abort": True}

    texts = ocr_read.read_all(img)
    low = " ".join(str(t).lower() for t, *_ in texts)
    is_panel = ("power" in low
                and any(w in low for w in ("attack", "scout", "reinforce", "gather info"))
                and bool(COORD_RE.search(low)))
    if not is_panel:
        return {"ok": False, "reason": "no_keep_panel",
                "hint": "open a player's keep/info panel first (read-only scout)"}

    name = alliance = coords = None
    power = keep_level = None
    for txt, _c, _cf in texts:
        s = str(txt).strip()
        n, a = parse_name_alliance(s)
        if a and n and not is_junk_name(n) and name is None:
            name, alliance = n, a
        m = COORD_RE.search(s)
        if m and coords is None:
            coords = m.group(0)
        km = re.search(r"(?:keep|k)\s*(?:lv\.?|level)?\s*[:\s]\s*(\d{1,2})", s, re.I) \
            or re.search(r"\blv\.?\s*(\d{1,2})\b", s, re.I)
        if km and keep_level is None:
            keep_level = _to_int(km.group(1))
        pm = re.search(r"power[:\s]+([\d,]{4,})", s, re.I)
        if pm and power is None:
            power = _to_int(pm.group(1))
    if name is None:
        for txt, _c, _cf in texts:
            n, a = parse_name_alliance(str(txt))
            if n and not is_junk_name(n):
                name, alliance = n, a
                break

    result = {"ok": False, "reason": "no_name_parsed", "coords": coords,
              "power": power, "keep_level": keep_level}
    if name:
        buffs = {}
        if power is not None:
            buffs["_power"] = power
        if keep_level is not None:
            buffs["_keep_level"] = keep_level
        conn2 = conn or _conn()
        upsert_player(conn2, name=name, alliance=alliance, coords=coords,
                      buffs=buffs or None)
        conn2.commit()
        if own:
            conn2.close()
        result = {"ok": True, "name": name, "alliance": alliance or "?",
                  "coords": coords, "power": power, "keep_level": keep_level}

    if close_after:
        try:
            safe_back(_make_nav(device))
        except Exception:
            pass
    return result


def read_alliance_roster(conn=None, device=DEV, max_pages=8):
    """LIVE: open Alliance -> Members, page through, OCR member name/power, and upsert
    each as a known player of my alliance (NFG, threat='ally'). READ-ONLY navigation
    only. Aborts on disconnect. If the Members panel isn't reachable, returns
    {'ok': False, 'reason': ...} honestly (no fabricated rows).

    NOTE: caller must have PAUSED the autonomous loop (see paused_loop)."""
    import ocr_read
    own = conn is None

    pre = _grab(device)
    if pre is None:
        return {"ok": False, "reason": "no_stream",
                "hint": "shared stream down (grab_wait None) — start the live stream "
                        "before --alliance; refusing to blind-tap without frames"}
    if _is_disconnected(pre):
        return {"ok": False, "reason": "disconnect", "abort": True}

    conn = conn or _conn()
    nav_obj = _make_nav(device)

    state = nav_obj.ensure_city(tries=8)
    if state == "disconnect":
        if own:
            conn.close()
        return {"ok": False, "reason": "disconnect", "abort": True}
    if state != "city":
        if own:
            conn.close()
        return {"ok": False, "reason": "not_in_city", "state": state}

    ctx = nav_obj.ctx
    ctx.tap(*ALLIANCE_BTN, d=2.5, label="alliance")
    img = _grab(device)
    if img is None or _is_disconnected(img):
        nav_obj.ensure_city(tries=6)
        if own:
            conn.close()
        return {"ok": False, "reason": "disconnect_or_no_frame", "abort": _is_disconnected(img)}
    low = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img))
    if "alliance" not in low and "member" not in low and "help" not in low:
        nav_obj.ensure_city(tries=6)
        if own:
            conn.close()
        return {"ok": False, "reason": "alliance_panel_not_reachable",
                "saw": low[:200]}

    members_xy = ocr_read.find_button(img, "members") or ocr_read.find_button(img, "member")
    if members_xy:
        ctx.tap(*members_xy, d=2.0, label="members")
        img = _grab(device)

    found = {}
    pages_ocr = []
    for _page in range(max_pages):
        if img is None:
            break
        if _is_disconnected(img):
            nav_obj.ensure_city(tries=6)
            if own:
                conn.close()
            return {"ok": False, "reason": "disconnect", "abort": True,
                    "members_found": len(found)}
        rows = ocr_read.read_all(img)
        page_txt = [str(t).strip() for t, *_ in rows]
        pages_ocr.append(page_txt)
        for txt, (cx, cy), cf in rows:
            s = str(txt).strip()
            n, a = parse_name_alliance(s)
            if not n or is_junk_name(n) or n == MY_NAME:
                continue
            if cx > 700 or cy < 300 or cy > 1750:
                continue
            if len(re.sub(r"[^A-Za-z]", "", n)) < 3:
                continue
            if n not in found:
                power = None
                for t2, (x2, y2), _cf2 in rows:
                    if abs(y2 - cy) <= 45 and x2 > cx:
                        pm = re.search(r"([\d,]{5,})", str(t2))
                        if pm:
                            power = _to_int(pm.group(1))
                            break
                found[n] = power
        ctx.swipe(540, 1450, 540, 850, ms=700, d=1.4)
        new_img = _grab(device)
        if new_img is None:
            break
        img = new_img

    upserts = 0
    for n, power in found.items():
        buffs = {"_power": power} if power else None
        if upsert_player(conn, name=n, alliance=MY_ALLIANCE, buffs=buffs, threat="ally"):
            upserts += 1
    conn.commit()

    nav_obj.ensure_city(tries=8)
    if own:
        conn.close()
    return {"ok": upserts > 0, "reason": "ok" if upserts else "no_members_parsed",
            "members_found": len(found), "upserted": upserts,
            "members": found, "pages": len(pages_ocr),
            "sample_ocr": pages_ocr[0][:20] if pages_ocr else []}


@contextmanager
def paused_loop(pid_file=LOOP_PID_FILE, verbose=True):
    """Pause the autonomous video_report loop (SIGSTOP) for the duration of live
    scouting, then resume it (SIGCONT) — so we never fight it for adb. No-op if the
    pid file is missing or the process is gone."""
    pid = None
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        pid = None
    paused = False
    if pid:
        try:
            os.kill(pid, signal.SIGSTOP)
            paused = True
            if verbose:
                print(f"[loop] paused pid {pid} (SIGSTOP)")
            time.sleep(1.0)
        except ProcessLookupError:
            pid = None
    try:
        yield pid
    finally:
        if paused and pid:
            try:
                os.kill(pid, signal.SIGCONT)
                if verbose:
                    print(f"[loop] resumed pid {pid} (SIGCONT)")
            except ProcessLookupError:
                pass


def prune_junk(conn=None, verbose=True):
    """Remove rows whose name is monster/event/OCR-fragment noise (is_junk_name),
    keeping the enemies roster to real players only. Data hygiene for the recon
    pillar — a junk 'enemy' is a fake enemy. Returns the list of pruned keys."""
    own = conn is None
    conn = conn or _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT alliance, name FROM enemies")
    doomed = [(r["alliance"], r["name"]) for r in cur.fetchall()
              if is_junk_name(r["name"])]
    if doomed:
        dcur = conn.cursor()
        dcur.executemany("DELETE FROM enemies WHERE alliance = %s AND name = %s", doomed)
        conn.commit()
    if verbose:
        print(f"prune_junk: removed {len(doomed)} junk rows")
        for a, n in doomed:
            print(f"  - {a} / {n}")
    if own:
        conn.close()
    return doomed


def print_stats(conn=None):
    """Print how many players are known, broken down by alliance and threat."""
    own = conn is None
    conn = conn or _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT count(*) AS n FROM enemies")
    total = cur.fetchone()["n"]
    print(f"KNOWN PLAYERS: {total}")

    print("\nby alliance:")
    cur.execute("""
        SELECT alliance, count(*) AS n,
               count(*) FILTER (WHERE max_troops IS NOT NULL) AS with_troops,
               count(*) FILTER (WHERE buffs IS NOT NULL) AS with_buffs,
               max(max_troops) AS top_troops
        FROM enemies GROUP BY alliance ORDER BY n DESC, alliance
    """)
    for r in cur.fetchall():
        tt = f"{r['top_troops']:,}" if r["top_troops"] else "-"
        print(f"  {r['alliance']:>5}  players={r['n']:<3} "
              f"troop_intel={r['with_troops']:<3} buff_intel={r['with_buffs']:<3} "
              f"top_troops={tt}")

    print("\nby threat:")
    cur.execute("""
        SELECT COALESCE(threat, '(unrated)') AS threat, count(*) AS n
        FROM enemies GROUP BY threat ORDER BY n DESC
    """)
    for r in cur.fetchall():
        print(f"  {r['threat']:>10}  {r['n']}")

    print("\ntop by max_troops:")
    cur.execute("""
        SELECT name, alliance, max_troops, battles, my_wins, my_losses, threat
        FROM enemies WHERE max_troops IS NOT NULL
        ORDER BY max_troops DESC LIMIT 10
    """)
    top = cur.fetchall()
    if not top:
        print("  (no troop counts recorded yet)")
    for r in top:
        print(f"  {r['alliance']:>5} / {r['name']:<18} "
              f"troops={r['max_troops']:>15,}  W/L={r['my_wins']}/{r['my_losses']}  "
              f"battles={r['battles']}  threat={r['threat'] or '-'}")

    if own:
        conn.close()
    return total


def main(argv=None):
    ap = argparse.ArgumentParser(description="Live enemy recon for the Evony bot")
    ap.add_argument("--scan-reports", action="store_true",
                    help="offline: mine report_extracts -> enemies")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --scan-reports: derive + print opponents, write nothing")
    ap.add_argument("--prune-junk", action="store_true",
                    help="offline: delete monster/OCR-noise rows from enemies")
    ap.add_argument("--stats", action="store_true",
                    help="offline: how many players known, by alliance/threat")
    ap.add_argument("--alliance", action="store_true",
                    help="LIVE: read my NFG alliance roster (pauses the loop)")
    ap.add_argument("--scout-screen", action="store_true",
                    help="LIVE: OCR an already-open keep/player panel (pauses the loop)")
    args = ap.parse_args(argv)

    if not any([args.scan_reports, args.stats, args.alliance,
                args.scout_screen, args.prune_junk]):
        ap.print_help()
        return 0

    if args.prune_junk:
        prune_junk()

    if args.scan_reports:
        scan_reports(dry_run=args.dry_run)

    if args.alliance or args.scout_screen:
        with paused_loop():
            if args.scout_screen:
                print("scout_keep_on_screen:", scout_keep_on_screen())
            if args.alliance:
                res = read_alliance_roster()
                print("read_alliance_roster:")
                for k, v in res.items():
                    print(f"  {k}: {v}")

    if args.stats:
        if args.scan_reports:
            print()
        print_stats()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
