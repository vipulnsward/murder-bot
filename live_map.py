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
import nav
import ocr_read
import orchestrator
import screen_fsm
import shared_capture
import vision_db

DEV = "127.0.0.1:5555"
ROOT = os.path.dirname(os.path.abspath(__file__))

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
    return shared_capture.grab(DEV)          # SHARED frame (no second adb capture)

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
    ctx.screencap = lambda: shared_capture.grab(DEV)     # nav reads the shared frame
    n = nav.Nav(ctx)
    os.makedirs(f"{ROOT}/templates/buildings", exist_ok=True)
    os.makedirs(f"{ROOT}/game_brain/screens", exist_ok=True)
    found = {}

    def probe(x, y):
        pre = cap()
        tap(x, y)
        img = cap()
        if img is None:
            return None
        if screen_fsm.is_disconnect(img):
            return "DISCONNECT"
        texts = ocr_read.read_all(img)
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

    print("ensure city:", n.ensure_city(), flush=True)
    grid = [(x, y) for y in range(340, 1300, 140) for x in range(180, 950, 140)]
    blocks = [("center", None), ("north", (540, 700, 540, 1280)), ("south", (540, 1280, 540, 700)),
              ("west", (300, 900, 880, 900)), ("east", (880, 900, 300, 900)),
              ("nw", (760, 700, 320, 1250)), ("se", (320, 1250, 760, 700))]
    for bname, mv in blocks:
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
