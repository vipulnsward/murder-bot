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


SALE_WORDS = ("deal", "purchase", "chf", "%return", "great value", "brand new",
              "flash sale", "tech leap", "unlock privileges", "super value",
              "limited time", "running of the bulls", "for sale", "buy now")


def clear_popups(max_iters=6):
    """Dismiss CONFIRMED sale/event popups with Android Back (safe — never buys; the
    close-X moves per popup). Cancels an exit-game dialog with Cancel (never Quit).
    Crucially, if the screen is neither the city, an exit dialog, nor a recognized sale
    popup, it does NOTHING — a blind Back in the city opens the exit dialog, and looping
    that trips the humanization guard. Returns True only when the city is reached."""
    for _ in range(max_iters):
        img = shared_capture.grab_wait(DEV, timeout=6)
        if img is None or screen_fsm.is_disconnect(img):
            return False
        if nav.is_city(ocr_read.read_all(img, box=nav.CITY_BOX)):
            return True
        if screen_fsm.identify(img) == "exit_dialog":
            subprocess.run(["adb", "-s", DEV, "shell", "input", "tap",
                            str(nav.EXIT_CANCEL[0]), str(nav.EXIT_CANCEL[1])])
            time.sleep(1.4)
            continue
        low = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img))
        if any(w in low for w in SALE_WORDS):
            subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"])  # Back closes sale popups
            time.sleep(1.4)
        else:
            return False   # unknown screen — don't blind-Back into the exit dialog
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
        # Safety + productivity: only tap while actually in the city. If a sale/event
        # popup is up, clear it (Back, never Buy) and skip this probe — never blind-tap
        # popup UI, which could land on a Buy button.
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
    import random
    jx, jy = random.randint(-65, 65), random.randint(-65, 65)   # jitter so repeated sweeps hit new points
    grid = [(x + jx, y + jy) for y in range(300, 1320, 120) for x in range(160, 960, 120)]
    blocks = [("center", None), ("north", (540, 700, 540, 1280)), ("south", (540, 1280, 540, 700)),
              ("west", (300, 900, 880, 900)), ("east", (880, 900, 300, 900)),
              ("nw", (760, 700, 320, 1250)), ("se", (320, 1250, 760, 700))]
    for bname, mv in blocks:
        if not ensure_game():                    # guard: don't tap a browser/home screen
            print("Evony left foreground mid-sweep — aborting pass", flush=True); return
        clear_popups()                           # a sale/event popup may have appeared mid-sweep
        exit_ideal_land()                        # a probe may have drilled into Ideal Land
        if mv:
            subprocess.run(["adb", "-s", DEV, "shell", "input", "swipe", *map(str, mv), "500"]); time.sleep(1.5)
            n.ensure_city(tries=2)
        print(f"== block {bname}: {len(grid)} probes ==", flush=True)
        for x, y in grid:
            if probe(x, y) == "DISCONNECT":
                print("DISCONNECT - stopping", flush=True)
                print("\nBUILDINGS:", sorted(found), flush=True); return

    print("\n=== ALL BUILDINGS FOUND ===", flush=True)
    for name, loc in sorted(found.items()):
        print(f"  {name}: {loc}")
    print("count:", len(found), "| stats:", db.stats(), flush=True)


if __name__ == "__main__":
    main()
