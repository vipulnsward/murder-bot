"""troop_scan — live driver: find a troop-training building, read every tier's count and
training cost, record to the db + brain. READ-ONLY (never taps Train / Instant Train).

Reuses live_map's proven building finding. Meant to run one building per call (between
rally checks) so coverage of all four (barracks/stable/archer_camp/workshop) builds up.
"""

from __future__ import annotations

import random
import subprocess
import sys
import time

sys.path.insert(0, "/Users/sward/work/scratch/evony-bot")
import cv2  # noqa: E402

import live_map  # noqa: E402
import nav  # noqa: E402
import ocr_read  # noqa: E402
import orchestrator  # noqa: E402
import screen_fsm  # noqa: E402
import shared_capture  # noqa: E402
import troop_intel  # noqa: E402

DEV = "127.0.0.1:5555"
ROW_Y = 1278
_ctx = orchestrator.Ctx(DEV, logger=lambda m: None)
_ctx.screencap = lambda: shared_capture.grab_wait(DEV)
_nav = nav.Nav(_ctx)

EAST = (860, 900, 320, 900)
WEST = (320, 900, 860, 900)
SOUTH = (540, 1340, 540, 640)
NW = (300, 620, 840, 1360)


import glob  # noqa: E402
import os  # noqa: E402

_TMPLS = None
TRAIN_BUILDINGS = ("barracks", "stable", "archer_camp", "workshop")


def _templates():
    global _TMPLS
    if _TMPLS is None:
        _TMPLS = {}
        for f in glob.glob("/Users/sward/work/scratch/evony-bot/templates/buildings/*.png"):
            n = os.path.basename(f)[:-4]
            if n in TRAIN_BUILDINGS:
                t = cv2.imread(f)
                if t is not None:
                    _TMPLS[n] = t
    return _TMPLS


def template_hits(img, thresh=0.50):
    """Tap points where a training-building template matches. Weak signal (used ON TOP of
    blob candidates), so a miss just wastes one harmless tap. Returns [(cx, cy, name)]."""
    if img is None:
        return []
    hits = []
    for name, t in _templates().items():
        res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        _mn, mx, _ml, loc = cv2.minMaxLoc(res)
        if mx >= thresh:
            hits.append((loc[0] + t.shape[1] // 2, loc[1] + t.shape[0] // 2, name, mx))
    return [(cx, cy, n) for cx, cy, n, _s in sorted(hits, key=lambda h: -h[3])]


def cap():
    return shared_capture.grab_wait(DEV, timeout=6)


def tap(x, y, d=1.4):
    subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", str(int(x)), str(int(y))]); time.sleep(d)


def swipe(m, ms=500):
    subprocess.run(["adb", "-s", DEV, "shell", "input", "swipe", *map(str, m), str(ms)]); time.sleep(1.2)


def back():
    subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"]); time.sleep(1.1)


def is_city(img):
    return img is not None and nav.is_city(ocr_read.read_all(img, box=nav.CITY_BOX, cache=True))


def to_city(tries=5):
    """Return to the city using the in-game back-arrow (via clear_popups) rather than raw
    Android Back, which on a bare city opens the exit dialog and can quit Evony."""
    for _ in range(tries):
        if is_city(cap()):
            return True
        if not live_map.game_foreground():
            live_map.ensure_game()
            continue
        live_map.clear_popups(max_iters=3)
        if is_city(cap()):
            return True
        back()   # for a Train screen etc. that clear_popups didn't close
    return is_city(cap())


def radial_train(img, x, y):
    """If tapping (x,y) opened a building radial with a 'Train' option, return (name, train_xy)."""
    box = (max(0, x - 380), max(0, y - 450), min(1080, x + 380), min(1920, y + 250))
    texts = ocr_read.read_all(img, box=box, cache=True)
    low = " ".join(str(t).lower() for t, *_ in texts)
    if "detail" not in low and "upgrade" not in low:
        return None, None
    train = None
    for t, (cx, cy), cf in texts:
        if str(t).strip().lower() == "train" and cf > 0.4:
            train = (cx, cy)
    return live_map.radial_name(texts), train


def find_training_building():
    """Bounded sweep: open the first building whose radial offers 'Train'. Returns its
    name with us left ON the train screen, or None (back on the city)."""
    live_map.ensure_game()
    to_city()
    live_map.exit_ideal_land()
    for _ in range(4):
        live_map.clear_popups(); swipe(NW)
    pans = [None, EAST, EAST, EAST]
    for row in range(1, 4):
        pans.append(SOUTH)
        pans.extend([EAST, EAST, EAST] if row % 2 == 0 else [WEST, WEST, WEST])
    # second, tighter inner pass where the military buildings cluster
    pans += [SOUTH, (700, 900, 400, 900), (400, 900, 700, 900), SOUTH,
             (700, 900, 400, 900), (400, 900, 700, 900)]
    for i, mv in enumerate(pans):
        live_map.clear_popups(); live_map.exit_ideal_land()
        if mv:
            swipe(mv); live_map.clear_popups()
        img = cap()
        if img is None or live_map.has_popup(img):
            continue
        # template hits (training buildings, incl. those on pavement) first, then blobs
        cands = [(cx, cy) for cx, cy, _n in template_hits(img)] + live_map.find_building_candidates(img)
        names = []
        for cx, cy in cands:
            pre = cap()
            if not is_city(pre):
                continue
            tap(cx, cy)
            img2 = cap()
            if img2 is None or screen_fsm.is_disconnect(img2):
                continue
            name, train = radial_train(img2, cx, cy)
            if name:
                names.append(name + ("+train" if train else ""))
            if train is not None:
                tap(*train)                  # -> training screen
                if troop_intel.is_train_screen(cap()):
                    print(f"pan{i}: opened {name} train screen", flush=True)
                    return name or "unknown"
                to_city()
                continue
            # Only back out when a menu/radial actually opened (name found, or not city).
            # NEVER blind-back a clean city -- that opens the exit dialog and, repeated,
            # quits Evony to the launcher. clear_popups then cancels any exit/confirm dialog.
            if name is not None or not is_city(img2):
                back()
                if not is_city(cap()) or live_map.has_popup(cap()):
                    live_map.clear_popups(max_iters=4)
        print(f"pan{i}: {len(cands)} cands, radials={names}", flush=True)
    return None


def scan_train_screen(building, max_batches=8):
    """On a Train screen: scroll the tier selector to the start, then step through every
    tier icon (READ-ONLY tap = just selects it), reading + recording each. Returns the
    {tier: name} map recorded."""
    seen = {}   # keyed by troop NAME (each tier is a unique troop) -> dedupes + tolerates
    #             bad tier reads; record() upserts by (building, name) so this matches the db.

    def take(tier):
        info = troop_intel.read_train_screen(cap())
        nm = info.get("name") if info else None
        if nm and nm not in seen:
            troop_intel.record(building, tier, info)
            seen[nm] = tier
            print(f"  T{tier} {nm:<22} own={info['own']} "
                  f"cost(w/s/o/g)={info['cost']['wood']}/{info['cost']['stone']}/"
                  f"{info['cost']['ore']}/{info['cost']['gold']}", flush=True)
            return True
        return False

    take(None)                                # the currently-shown tier (works even if the
    #                                           selector OCR fails this frame)
    for _ in range(6):                        # scroll the selector to the lowest tiers
        swipe((300, ROW_Y, 880, ROW_Y))
    # Tap FIXED x-positions along the row rather than OCR-locating each icon (the selector
    # OCR is flaky); read whatever tier each tap selects. Tier numbers are best-effort from
    # selector_tiers when it reads, but records are keyed by troop name regardless.
    xs = [140, 300, 460, 620, 780, 940]
    stale = 0
    for _ in range(max_batches):
        tmap = {cx: t for t, cx in troop_intel.selector_tiers(cap())}
        progressed = False
        for x in xs:
            tap(x, ROW_Y)                     # select whatever icon is here (safe)
            tier = None
            if tmap:
                nx = min(tmap, key=lambda c: abs(c - x))
                if abs(nx - x) < 90:
                    tier = tmap[nx]
            if take(tier):
                progressed = True
        swipe((880, ROW_Y, 300, ROW_Y))       # advance toward higher tiers
        stale = 0 if progressed else stale + 1
        if stale >= 2:
            break
    return seen


def gather_once():
    """Find one training building, scan all its tiers, record, return to city. Returns
    (building, tiers_recorded)."""
    building = find_training_building()
    if not building:
        print("no training building reached this pass", flush=True)
        to_city()
        return None, 0
    print(f"scanning {building}", flush=True)
    seen = scan_train_screen(building)
    to_city()
    return building, len(seen)


def watch_and_scan(poll_s=3.0, rounds=200):
    """Reliable guided capture: poll the screen; whenever a Train screen is on-screen,
    scan all its tiers and record. Lets a human open each training building's Train
    screen (Barracks / Stable / Archer Camp / Workshop) while this records automatically.
    Building name is inferred from the top-left back emblem area, else 'train'."""
    done = set()
    for _ in range(rounds):
        img = cap()
        if troop_intel.is_train_screen(img):
            # infer which building via the small icon row won't help; use a rotating label
            key = tuple(sorted(t for t, _x in troop_intel.selector_tiers(img)))
            if key and key not in done:
                seen = scan_train_screen("train")
                print(f"recorded {len(seen)} tiers: {seen}", flush=True)
                done.add(key)
        else:
            time.sleep(poll_s)
    return done


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        watch_and_scan()
    else:
        b, n = gather_once()
        print(f"DONE gather_once -> building={b} tiers_recorded={n}")
