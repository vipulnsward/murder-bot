"""live_rally — wire rally_join to the Alliance War -> Monster War screen (learned live).

Flow (verified on the real client):
  Alliance War (Monster War tab) lists boss-monster rallies. Each card has a green
  "Join" button (already-joined shows "Joined"). Tapping Join opens the march-setup
  screen where the saved PRESET auto-fills the generals + troop count; tapping "March"
  sends the reinforcement. GEM-SAFE: this only taps Join/March (marches), never a
  gem/purchase control; the preset caps the troop count (1 T1 ground here).
"""

from __future__ import annotations

import subprocess
import time

import live_map
import nav
import ocr_read
import shared_capture

DEV = "127.0.0.1:5555"
MARCH_XY = (810, 1830)      # gold "March" on the setup screen
AUTO_JOIN_XY = (780, 1825)  # green "Auto-Join" on the war list


def _cap():
    return shared_capture.grab_wait(DEV, timeout=6)


def _tap(x, y, d=1.8):
    subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", str(int(x)), str(int(y))])
    time.sleep(d)


def _find(img, needle, min_conf=0.5, xmin=0, ymin=0):
    """Center (x,y) of the first OCR token containing `needle`, or None. Buttons are
    located by text so this survives layout shifts, not fixed coordinates."""
    if img is None:
        return None
    for txt, (cx, cy), conf in ocr_read.read_all(img):
        if conf >= min_conf and cx >= xmin and cy >= ymin and needle in str(txt).lower():
            return (cx, cy)
    return None


def _is_city(img):
    return img is not None and nav.is_city(ocr_read.read_all(img, box=nav.CITY_BOX))


def ensure_city(tries=6):
    for _ in range(tries):
        img = _cap()
        if _is_city(img) and not live_map.has_popup(img):
            return True
        if live_map.has_popup(img):
            subprocess.run(["adb", "-s", DEV, "shell", "input", "keyevent", "4"]); time.sleep(1.2)
        else:
            _tap(80, 72)
    return _is_city(_cap())


def on_war_screen(img):
    low = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img))
    return "alliance war" in low and ("monster war" in low or "rallying" in low or "pvp war" in low)


def open_monster_war(tries=3):
    """Navigate from anywhere to the Alliance War (Monster War) rally list, verifying each
    step. City -> Alliance button -> 'Alliance War' menu item -> war screen. Returns True
    only when the war screen is confirmed on-screen."""
    for _ in range(tries):
        img = _cap()
        if on_war_screen(img):
            return True
        if not ensure_city():
            continue
        img = _cap()
        a = _find(img, "alliance", xmin=820, ymin=1400)   # bottom-right Alliance button
        if not a:
            continue
        _tap(a[0], a[1] - 10)
        img = _cap()
        w = _find(img, "alliance war")                    # menu item in the alliance panel
        if not w:
            continue
        _tap(*w)
        if on_war_screen(_cap()):
            return True
    return False


def read_rallies(img):
    """Parse the Monster War list. Returns [{status, join_xy}] top-to-bottom. A card is
    joinable when its right-side button reads 'Join'; 'Joined' means already in."""
    if img is None:
        return []
    out = []
    for txt, (cx, cy), conf in ocr_read.read_all(img):
        t = str(txt).strip().lower()
        if conf < 0.5 or cx < 780:          # right-side buttons only
            continue
        if t == "join":
            out.append({"status": "joinable", "join_xy": (cx, cy)})
        elif "joined" in t:
            out.append({"status": "joined", "join_xy": None})
    out.sort(key=lambda r: r["join_xy"][1] if r["join_xy"] else 0)
    return out


def join_one(join_xy):
    """Tap a rally's Join, then March on the setup screen (preset fills generals+troops)."""
    _tap(*join_xy)                     # -> march-setup screen
    img = _cap()
    low = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img))
    if "march" not in low and "preset" not in low:
        return False                  # setup didn't open (rally may have marched)
    march = ocr_read.find_button(img, "march") or MARCH_XY
    _tap(*march)                      # -> send
    time.sleep(0.5)
    return True


def join_all(max_marches=6):
    """Join up to max_marches joinable monster rallies. Re-reads the list after each join
    (a joined rally flips Join->Joined). Returns the number joined."""
    joined = 0
    for _ in range(max_marches):
        img = _cap()
        joinable = [r for r in read_rallies(img) if r["status"] == "joinable"]
        if not joinable:
            break
        if join_one(joinable[0]["join_xy"]):
            joined += 1
        time.sleep(1.0)
    return joined


def auto_join():
    """Tap the game's built-in Auto-Join (joins with the saved preset automatically)."""
    _tap(*AUTO_JOIN_XY)


def run(max_marches=6):
    """Full hands-free cycle: navigate to the Monster War list, join up to max_marches
    joinable monster rallies (preset fills generals + 1 T1 ground), return to the city.
    Returns the number joined. Gem-safe; leaves the game on a clean city."""
    if not open_monster_war():
        return 0
    joined = join_all(max_marches=max_marches)
    ensure_city()
    return joined


if __name__ == "__main__":
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    joined = run(max_marches=n)
    print(f"run() joined {joined} monster rally(ies), returned to city")
