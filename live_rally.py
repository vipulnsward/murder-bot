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


if __name__ == "__main__":
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    img = _cap()
    rallies = read_rallies(img)
    print("rallies on screen:", rallies)
    joined = join_all(max_marches=n)
    print(f"joined {joined} rally(ies)")
