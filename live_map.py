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


def clear_popups(max_iters=6):
    """Dismiss stacked sale/event popups with Android Back (safe — never buys; the
    close-X moves per popup). Stops at the city; cancels an exit-game dialog with
    Cancel (never Quit); leaves a disconnect for the caller. Returns True if city."""
    for _ in range(max_iters):
        img = shared_capture.grab_wait(DEV, timeout=6)
        if img is None or screen_fsm.is_disconnect(img):
            return False
        if nav.is_city(ocr_read.read_all(img, box=nav.CITY_BOX)):
            return True
        if screen_fsm.identify(img) == "exit_dialog":
            subprocess.run(["adb", "-s", DEV, "shell", "input", "tap",
                            str(nav.EXIT_CANCEL[0]), str(nav.EXIT_CANCEL[1])])
        else:
            subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"])
        time.sleep(1.6)
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

def tap(x, y, d=1.9):
    subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", str(int(x)), str(int(y))]); time.sleep(d)

def adb_back():
    subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"]); time.sleep(1.5)


def radial_name(texts):
    low = " ".join(str(t).lower() for t, *_ in texts)
    for b in sorted(BUILDINGS, key=len, reverse=True):
        if b in low:
            return b.replace(" ", "_")
    for t, (cx, cy), cf in texts:
        w = str(t).strip()
        if cf > 0.6 and 200 < cy < 1300 and re.fullmatch(r"[A-Z][A-Za-z]{3,15}", w) and w.lower() not in GENERIC:
            return w.lower()
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
        _maybe_write_hud(pre)  # pre-tap city frame -> refresh the dashboard HUD (throttled)
        tap(x, y)
        img = cap()
        if img is None:
            return None
        if screen_fsm.is_disconnect(img):
            return "DISCONNECT"
        # Fast OCR first: the radial menu (Detail/Upgrade) pops up around the tapped
        # building, never the whole screen. Scope OCR to a box around the tap point
        # instead of the full 1080x1920 frame — ~3x less pixels to detect, plus cache.
        tapbox = (max(0, x - 360), max(0, y - 430), min(1080, x + 360), min(1920, y + 230))
        texts = ocr_read.read_all(img, box=tapbox, cache=True)
        low = " ".join(str(t).lower() for t, *_ in texts)
        if "detail" not in low and "upgrade" not in low:
            return None
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
        n.ensure_city(tries=3)
        return name

    if not ensure_game():
        print("Evony not in foreground and relaunch failed — aborting pass", flush=True)
        return
    print("ensure city:", n.ensure_city(), flush=True)
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
