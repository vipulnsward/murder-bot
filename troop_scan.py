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


def to_city(tries=4):
    for _ in range(tries):
        if is_city(cap()):
            return True
        back()
    live_map.clear_popups(max_iters=4)
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
        cands = live_map.find_building_candidates(img)
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
            if train is None:
                if not is_city(img2):
                    back()
                continue
            tap(*train)                      # -> training screen
            if troop_intel.is_train_screen(cap()):
                print(f"pan{i}: opened {name} train screen", flush=True)
                return name or "unknown"
            to_city()
        print(f"pan{i}: {len(cands)} cands, radials={names}", flush=True)
    return None


def scan_train_screen(building, max_batches=8):
    """On a Train screen: scroll the tier selector to the start, then step through every
    tier icon (READ-ONLY tap = just selects it), reading + recording each. Returns the
    {tier: name} map recorded."""
    for _ in range(5):                        # reveal the lowest tiers
        swipe((300, ROW_Y, 860, ROW_Y))
    seen = {}
    stale = 0
    for _ in range(max_batches):
        img = cap()
        tiers = troop_intel.selector_tiers(img)
        progressed = False
        for tier, cx in tiers:
            if tier in seen:
                continue
            tap(cx, ROW_Y)                    # select the tier (safe: never a Train button)
            info = troop_intel.read_train_screen(cap())
            if info and info.get("name"):
                troop_intel.record(building, tier, info)
                seen[tier] = info["name"]
                progressed = True
                print(f"  T{tier:<2} {info['name']:<22} own={info['own']} "
                      f"cost(w/s/o/g)={info['cost']['wood']}/{info['cost']['stone']}/"
                      f"{info['cost']['ore']}/{info['cost']['gold']} t={info['train_seconds']}s",
                      flush=True)
        swipe((860, ROW_Y, 300, ROW_Y))       # advance toward higher tiers
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
