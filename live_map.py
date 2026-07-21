"""Live city building mapper that shares the stream's single adb capture.

Reads frames via shared_capture.grab (the JPEG the HLS ffmpeg writes) instead of
a second adb screencap, so it runs IN PARALLEL with the 60fps live stream. Taps go
over a separate adb-input channel (never conflicts with capture). Uses nav for safe
navigation (returns to city after every probe; never taps Quit/gem/craft controls).

  python live_map.py            # sweep the city, mapping building radials -> vision_db
"""

import os
import re
import subprocess
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_hud
import nav
import ocr_read
import orchestrator
import screen_fsm
import shared_capture
import vision_db

DEV = "127.0.0.1:5555"
_last_hud = [0.0]


def _maybe_write_hud(img, min_interval=8.0):
    """When we're on a clean city frame between probes, refresh the dashboard HUD
    file (throttled). Read-only; keeps the control app's stats live while mapping."""
    now = time.time()
    if img is None or now - _last_hud[0] < min_interval:
        return
    try:
        hud = game_hud.read_hud(img)
        if hud.get("ok") and game_hud.write_hud(hud):
            _last_hud[0] = now
    except Exception:
        pass


IDEAL_BOX = (0, 1120, 240, 1760)   # left column of the Ideal Land decoration UI
IDEAL_TOKENS = ("ornament", "construct", "inventory", "top", "charts", "gallery")
CITY_TOGGLE = (994, 1790)          # bottom-right castle button: Ideal Land <-> main city
# The buildings that actually matter for the bot (military + economy + core).
PRIORITY = ["keep", "academy", "barracks", "stable", "archer_camp", "archer_range",
            "workshop", "hospital", "forge", "embassy", "rally_spot", "war_hall",
            "watchtower", "market", "wall", "warehouse", "hall_of_war"]


def is_ideal_land(img):
    """True in Ideal Land (the decorative sub-city), not the main city. Both show Mail
    bottom-right, but only Ideal Land has the Ornament/Construct/Top Charts column."""
    if img is None:
        return False
    low = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img, box=IDEAL_BOX, cache=True))
    return sum(w in low for w in IDEAL_TOKENS) >= 2


def exit_ideal_land(tries=3):
    """Return from Ideal Land to the main city via the bottom-right castle button."""
    for _ in range(tries):
        img = shared_capture.grab_wait(DEV, timeout=6)
        if img is None or not is_ideal_land(img):
            return
        subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", *map(str, CITY_TOGGLE)])
        time.sleep(2.0)


# Strong purchase-popup signals. "chf" (the price) is the reliable one — every purchase
# modal shows a CHF price and the bare city never does. Avoid generic words like "deal"
# or "for sale" (the Alliance button carries a FOR SALE badge -> false positive).
SALE_WORDS = ("chf", "purchase", "%return", "unlock privileges", "flash sale",
              "tech leap", "super value", "running of the bulls", "bounty cave",
              "daily gems for", "right of mining")


def has_popup(img):
    """True if a purchase modal is over the city. These are CENTERED and leave the
    bottom-right Mail button visible, so is_city can't see them — detect by price/title."""
    low = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img))
    return any(w in low for w in SALE_WORDS)


def clear_popups(max_iters=8):
    """Dismiss purchase/event popups with Android Back (safe — never buys; the close-X
    moves per popup). Checks for a popup BEFORE is_city, because a centered modal leaves
    Mail visible and would otherwise read as 'city'. Cancels an exit-game dialog with
    Cancel (never Quit). Returns True only when the clean city (no popup) is reached."""
    for _ in range(max_iters):
        img = shared_capture.grab_wait(DEV, timeout=6)
        if img is None or screen_fsm.is_disconnect(img):
            return False
        if screen_fsm.identify(img) == "exit_dialog":
            subprocess.run(["adb", "-s", DEV, "shell", "input", "tap",
                            str(nav.EXIT_CANCEL[0]), str(nav.EXIT_CANCEL[1])])
            time.sleep(1.3)
            continue
        if has_popup(img):
            subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"])  # Back closes it
            time.sleep(1.3)
            continue
        if nav.is_city(ocr_read.read_all(img, box=nav.CITY_BOX)):
            return True
        return False   # unknown non-popup screen — don't blind-Back into the exit dialog
    return False
ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = "com.topgamesinc.evony.flexion"


def game_foreground():
    """True if Evony is the focused app (guards against a stray tap opening a browser)."""
    try:
        out = subprocess.run(["adb", "-s", DEV, "shell", "dumpsys", "window"],
                             capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return False
    for line in out.splitlines():
        if "mCurrentFocus" in line:
            return PKG in line
    return PKG in out


def ensure_game():
    """Bring Evony to the foreground if it isn't (e.g. a browser/home took over)."""
    if game_foreground():
        return True
    subprocess.run(["adb", "-s", DEV, "shell", "monkey", "-p", PKG,
                    "-c", "android.intent.category.LAUNCHER", "1"], capture_output=True)
    time.sleep(10)
    return game_foreground()

BUILDINGS = ["research factory","forge","academy","barracks","stable","archer camp","archer range","range",
 "workshop","hospital","embassy","rally spot","war hall","watchtower","keep","wall","warehouse","market",
 "trap factory","farm","sawmill","quarry","mine","prison","shrine","hall of war","victory column","holy palace",
 "relief station","tavern","gym","altar","monument","garrison","command center","arsenal","gold mine","cottage",
 "trading post","order","hospital","beast cage","dragon lair"]
GENERIC = {"detail","upgrade","cancel","help","info","move","store","recall","boost","train","speed","up",
 "produce","research","stones","materials","craft","medal","duty","confirm","start","instant","finish","free",
 "select","all","list","quantity","own","use","minimum","battle","event","alliance","mail","quests","gifts",
 "world","map","lucky","raffle","mysterious","realm","valuable","login","follow","center"}


def cap():
    return shared_capture.grab_wait(DEV)          # SHARED frame (no second adb capture)

def tap(x, y, d=1.4):
    # The building radial menu needs ~1.4s to animate in; 0.8s misses it (menu not up
    # yet -> no Detail/Upgrade -> nothing recorded). Measured: 0.8s fails, 1.4s reliable.
    subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", str(int(x)), str(int(y))]); time.sleep(d)

def adb_back():
    subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"]); time.sleep(0.9)


def find_building_candidates(img):
    """Return [(x, y)] tap points at building structures. Buildings are grey/brown
    structures; grass is green and decorations are pink — mask both out and the
    remaining blobs are buildings. ~5 targeted taps per view vs 63 blind grid taps."""
    import numpy as np

    if img is None:
        return []
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array([32, 35, 35]), np.array([98, 255, 255]))
    pink = cv2.inRange(hsv, np.array([125, 25, 70]), np.array([178, 255, 255]))
    struct = cv2.bitwise_not(cv2.bitwise_or(grass, pink))
    play = np.zeros((h, w), np.uint8)
    play[240:1240, 150:900] = 255   # exclude top HUD, bottom decorations, side UI columns
    struct = cv2.bitwise_and(struct, play)
    struct = cv2.morphologyEx(struct, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    struct = cv2.morphologyEx(struct, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(struct, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pts = []
    for c in cnts:
        if cv2.contourArea(c) > 5000:
            x, y, bw, bh = cv2.boundingRect(c)
            pts.append((x + bw // 2, y + int(bh * 0.55)))   # tap toward the building base
    return pts


_KEEP_TMPL = [None]


def find_keep(img, thresh=0.72):
    """Template-match the Keep (the city's anchor). Returns its center (x, y) if it's
    in view above the confidence threshold, else None. Match ~0.96 when present, ~0.58
    when absent, so 0.72 separates cleanly."""
    if _KEEP_TMPL[0] is None:
        _KEEP_TMPL[0] = cv2.imread(f"{ROOT}/templates/buildings/keep.png")
    t = _KEEP_TMPL[0]
    if img is None or t is None:
        return None
    th, tw = t.shape[:2]
    res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    _, mx, _, ml = cv2.minMaxLoc(res)
    if mx >= thresh:
        return (ml[0] + tw // 2, ml[1] + th // 2)
    return None


def radial_name(texts):
    # Only name a building when a KNOWN building label appears in the panel text.
    # The old "any capitalized word" fallback recorded OCR noise and button labels
    # (Detail/Demolish/Follow Us/USS Constitution) as fake buildings.
    low = " ".join(str(t).lower() for t, *_ in texts)
    for b in sorted(BUILDINGS, key=len, reverse=True):
        if b in low:
            return b.replace(" ", "_")
    return None


def main():
    db = vision_db.VisionDB(f"{ROOT}/game_brain/vision.db")
    ctx = orchestrator.Ctx(DEV, logger=lambda m: None)
    ctx.screencap = lambda: shared_capture.grab_wait(DEV)     # nav reads the shared frame
    n = nav.Nav(ctx)
    os.makedirs(f"{ROOT}/templates/buildings", exist_ok=True)
    os.makedirs(f"{ROOT}/game_brain/screens", exist_ok=True)
    found = {}

    def probe(x, y):
        pre = cap()
        if pre is None:
            clear_popups()
            return None
        # Never map Ideal Land (the decorative sub-city) — go back to the main city.
        if is_ideal_land(pre):
            exit_ideal_land()
            return None
        # A centered purchase modal leaves Mail visible (is_city would say True), so check
        # for it explicitly and clear it — never blind-tap popup UI (could hit Buy).
        if has_popup(pre):
            clear_popups()
            return None
        if not nav.is_city(ocr_read.read_all(pre, box=nav.CITY_BOX, cache=True)):
            clear_popups()
            return None
        _maybe_write_hud(pre)  # pre-tap city frame -> refresh the dashboard HUD (throttled)
        tap(x, y)
        img = cap()
        if img is None:
            return None
        if screen_fsm.is_disconnect(img):
            return "DISCONNECT"
        # Check the radial menu around the tap FIRST — a building shows Detail/Upgrade
        # there. Do NOT gate on is_city here: a building's radial menu often leaves the
        # bottom-right Mail button visible, so is_city can still read True and we'd miss
        # the building entirely.
        tapbox = (max(0, x - 360), max(0, y - 430), min(1080, x + 360), min(1920, y + 230))
        texts = ocr_read.read_all(img, box=tapbox, cache=True)
        low = " ".join(str(t).lower() for t, *_ in texts)
        if "detail" in low or "upgrade" in low:
            name = radial_name(texts)
            if name and name not in found:
                found[name] = (x, y)
                if pre is not None:
                    cv2.imwrite(f"{ROOT}/templates/buildings/{name}.png",
                                pre[max(0, y - 230):y + 40, max(0, x - 130):min(1080, x + 130)])
                cv2.imwrite(f"{ROOT}/game_brain/screens/bldg_{name}.png", img)
                db.upsert_screen(f"bldg_{name}", description=f"city building {name}",
                                 template_path=f"templates/buildings/{name}.png")
                for t, (cx, cy), cf in texts:
                    if cf > 0.5 and str(t).strip():
                        db.add_element(f"bldg_{name}", str(t)[:40], cx, cy)
                db.add_element(f"bldg_{name}", f"loc:{name}", x, y,
                               template_path=f"templates/buildings/{name}.png", description="building location")
                db.record_capture(image_path=f"{ROOT}/game_brain/screens/bldg_{name}.png", phash=db.phash(img),
                                  screen_label=f"bldg_{name}", ocr_text=" | ".join(str(t) for t, *_ in texts))
                print(f"  FOUND {name} @({x},{y}) [total {len(found)}]", flush=True)
            adb_back()
            n.ensure_city(tries=2)
            return name
        # No building menu. If some OTHER panel opened (not the city), close it with Back
        # (safe while a panel is up). If we're still in the bare city, the tap hit empty
        # ground — do NOT Back (that opens the exit dialog).
        if not nav.is_city(ocr_read.read_all(img, box=nav.CITY_BOX, cache=True)):
            adb_back()
            n.ensure_city(tries=1)
        return None

    if not ensure_game():
        print("Evony not in foreground and relaunch failed — aborting pass", flush=True)
        return
    print("ensure city:", n.ensure_city(), flush=True)
    exit_ideal_land()   # if a prior probe drilled into Ideal Land, return to the main city
    # Cover the whole city with camera pans; at each stop tap ONLY detected building
    # structures (targeted). Reset toward the NW corner first so every sweep starts from
    # the same place, then snake-raster a 4x4 grid -> deterministic full coverage.
    def swipe(mv):
        subprocess.run(["adb", "-s", DEV, "shell", "input", "swipe", *map(str, mv), "500"])
        time.sleep(1.3)

    NW = (300, 620, 840, 1360)      # drag content down-right -> camera moves NW (corner)
    EAST = (860, 900, 320, 900)     # camera east
    WEST = (320, 900, 860, 900)     # camera west
    SOUTH = (540, 1340, 540, 640)   # camera south
    for _ in range(4):
        if not ensure_game():
            return
        clear_popups(); swipe(NW)
    PANS = [("r0c0", None), ("r0c1", EAST), ("r0c2", EAST), ("r0c3", EAST)]
    for row in range(1, 4):          # snake down the rows
        across = [EAST, EAST, EAST] if row % 2 == 0 else [WEST, WEST, WEST]
        PANS.append((f"r{row}c0", SOUTH))
        for col, mv in enumerate(across):
            PANS.append((f"r{row}c{col + 1}", mv))

    for label, mv in PANS:
        if not ensure_game():                    # guard: don't tap a browser/home screen
            print("Evony left foreground mid-sweep — aborting pass", flush=True); return
        clear_popups(); exit_ideal_land()
        if mv:
            swipe(mv)
            clear_popups(); exit_ideal_land()
        img = cap()
        # Only detect buildings on a clean city frame — a centered popup would otherwise
        # be picked up as a "structure" and tapped.
        if img is None or has_popup(img):
            print(f"== pan {label}: skipped (popup) ==", flush=True)
            continue
        cands = find_building_candidates(img)
        print(f"== pan {label}: {len(cands)} building candidates ==", flush=True)
        for cx, cy in cands:
            if probe(cx, cy) == "DISCONNECT":
                print("DISCONNECT - stopping", flush=True); return

    # Phase 2: anchor on the Keep (fixed reference) and tightly map the inner city where
    # the military buildings cluster — the drift-prone blind raster can't reliably reach it.
    def center_on_keep(max_iter=18):
        for _ in range(max_iter):
            if not ensure_game():
                return False
            clear_popups(); exit_ideal_land()
            img = cap()
            if img is None or has_popup(img):
                continue
            k = find_keep(img)
            if k is None:
                swipe(EAST)   # scan for it
                continue
            kx, ky = k
            if abs(kx - 540) < 150 and abs(ky - 950) < 150:
                return True   # Keep is centered
            swipe((kx, ky, 540, 950))   # drag the Keep toward screen center
        return False

    if center_on_keep():
        print("== centered on Keep — mapping inner city ==", flush=True)
        inner = [None, (700, 900, 400, 900), (400, 900, 700, 900),
                 (540, 1080, 540, 720), (540, 720, 540, 1080),
                 (680, 1050, 420, 760), (420, 760, 680, 1050)]
        for mv in inner:
            if not ensure_game():
                break
            clear_popups(); exit_ideal_land()
            if mv:
                swipe(mv); clear_popups(); exit_ideal_land()
            img = cap()
            if img is None or has_popup(img):
                continue
            for cx, cy in find_building_candidates(img):
                if probe(cx, cy) == "DISCONNECT":
                    return
            center_on_keep(max_iter=6)   # re-anchor after each small pan

    have = {s["label"].replace("bldg_", "") for s in db.list_screens()
            if str(s.get("label", "")).startswith("bldg_")}
    missing = [b for b in PRIORITY if b not in have]
    print(f"\n=== sweep done: {len(found)} buildings this sweep {sorted(found)}", flush=True)
    print(f"priority missing ({len(missing)}/{len(PRIORITY)}): {missing}", flush=True)
    print("stats:", db.stats(), flush=True)


if __name__ == "__main__":
    main()
