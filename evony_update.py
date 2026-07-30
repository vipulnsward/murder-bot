"""Evony auto-update: detect the force-update wall and heal through it via the
Huawei AppGallery, so an unattended overnight bot doesn't silently die on a
forced update and miss every rally.

GEM-SAFE: only ever taps an Update/Install/back control, never a purchase.
The in-store Update button is OCR-located (not a hardcoded coordinate), and the
flow ALERTS via the log + returns a status if it cannot complete on its own, so
a human can finish it — it never blindly taps around a store screen.

needs_update() is read-only and safe to call every cycle. The full handle_update()
store flow is best-effort until validated against a real update wall; it is wired
to run only when needs_update() is true, and to alert rather than flail."""
import subprocess
import time

import ocr_read
import shared_capture

DEV = "127.0.0.1:5555"
EVONY_PKG = "com.topgamesinc.evony.flexion"
STORE_PKG = "com.huawei.appmarket"

# Words that appear on Evony's force-update / new-version wall but NOT on the bare
# city HUD (kept specific to avoid false positives that would yank the bot off the map).
UPDATE_WORDS = ("new version", "update to the latest", "please update", "latest version",
                "version is available", "download the new", "a new update",
                "update required", "version update", "update the game")


def needs_update(img=None):
    """True if the Evony update/new-version wall is on screen. Read-only."""
    if img is None:
        img = shared_capture.grab_wait(DEV, timeout=6)
    if img is None:
        return False
    low = " ".join(str(t).lower() for t, *_ in ocr_read.read_all(img))
    return any(w in low for w in UPDATE_WORDS)


def _tap(x, y, settle=1.0):
    subprocess.run(["adb", "-s", DEV, "shell", "input", "tap", str(int(x)), str(int(y))])
    time.sleep(settle)


def open_appgallery():
    """Deep-link the Huawei AppGallery straight to Evony's detail page (Update lives there)."""
    subprocess.run(["adb", "-s", DEV, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                    "-d", "market://details?id=%s" % EVONY_PKG, STORE_PKG])
    time.sleep(4)


def _find_update_button():
    """OCR-locate an Update/Install control in the store. Returns (x, y) or None.
    Never matches purchase words."""
    img = shared_capture.grab_wait(DEV, timeout=6)
    if img is None:
        return None
    for text, xy, *_ in ocr_read.read_all(img):
        label = str(text).strip().lower()
        if label in ("update", "install", "更新", "安装") and isinstance(xy, (tuple, list)):
            return int(xy[0]), int(xy[1])
    return None


def relaunch_evony():
    subprocess.run(["adb", "-s", DEV, "shell", "monkey", "-p", EVONY_PKG,
                    "-c", "android.intent.category.LAUNCHER", "1"])
    time.sleep(8)


def handle_update(wait_install_s=600, log=print):
    """open store -> tap Update -> wait for install -> relaunch Evony past the wall.
    Returns 'updated' | 'no_update_button' | 'timeout'. Alerts via log; never taps Buy."""
    log("evony_update: update wall detected -> opening AppGallery to Evony")
    open_appgallery()
    btn = _find_update_button()
    if btn is None:
        log("evony_update: ALERT — no Update button found in store; manual update may be needed")
        relaunch_evony()
        return "no_update_button"
    _tap(*btn)
    log("evony_update: Update tapped; waiting for install to finish...")
    waited, step = 0, 20
    while waited < wait_install_s:
        time.sleep(step)
        waited += step
        relaunch_evony()
        if not needs_update():
            log("evony_update: updated + relaunched past the wall after ~%ds" % waited)
            return "updated"
    log("evony_update: ALERT — install timed out after %ds" % wait_install_s)
    return "timeout"


if __name__ == "__main__":
    print("needs_update:", needs_update())
