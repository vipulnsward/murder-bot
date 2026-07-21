"""Reliable in-game navigation primitives for the Evony bot (learned live).

Grounded in live observation of the real client:
  - CITY is detected by OCR, not a single building template: the fixed bottom-bar
    "Alliance" + "Mail" buttons are present and there are no world-map "X:/Y:"
    coordinates. This survives camera panning (the old barracks_bldg template did
    not — panned city read "unknown").
  - the top-left BACK ARROW at ~(80,72) reliably exits a screen one level.
  - the bottom-right GLOBE at ~(994,1790) toggles city <-> world map.
  - on the account-disconnect screen the RESTART button is found by OCR text; we
    NEVER tap Quit.

GEM-SAFE + disconnect-safe: these primitives only tap navigation controls
(back/cancel/globe/restart). They never tap Quit, Instant Finish, Confirm, Start,
or any gem/craft control. Radials are closed by backing out, never by tapping a
radial option (which would drill into a feature).
"""

import time

BACK_ARROW = (80, 72)
CITY_GLOBE = (994, 1790)
EXIT_CANCEL = (362, 1133)
# The city's Alliance + Mail buttons live in this bottom-right box (Alliance ~988,1516;
# Mail ~987,1685). Scoping the city check here is ~4x faster than a full-frame OCR and
# runs on every ensure_city — the world-map "X:/Y:" coords sit up top, outside this box,
# so a scoped miss correctly falls through to the full-frame world-map check.
CITY_BOX = (760, 1400, 1080, 1920)


def is_city(texts):
    """True if the OCR text set looks like the city view (fixed menus, no map coords)."""
    low = " ".join(str(t).lower() for t, *_ in texts)
    flat = low.replace(" ", "")
    return ("alliance" in low and "mail" in low) and ("x:0" not in flat and "y:0" not in flat)


def is_worldmap(texts):
    low = " ".join(str(t).lower() for t, *_ in texts)
    flat = low.replace(" ", "")
    return "x:0" in flat or "y:0" in flat


class Nav:
    def __init__(self, ctx, read_all=None, screen_fsm=None, find_button=None, sleep=time.sleep):
        self.ctx = ctx
        self.sleep = sleep
        if read_all is None or find_button is None:
            import ocr_read
            read_all = read_all or ocr_read.read_all
            find_button = find_button or ocr_read.find_button
        if screen_fsm is None:
            import screen_fsm
        self.read_all = read_all
        self.find_button = find_button
        self.screen_fsm = screen_fsm

    def _frame(self):
        return self.ctx.screencap()

    def _read(self, img, box=None):
        """read_all with an optional scope box, tolerant of injected doubles that
        only accept (img)."""
        if box is None:
            return self.read_all(img)
        try:
            return self.read_all(img, box=box)
        except TypeError:
            return self.read_all(img)

    def state(self, img=None):
        """Return 'disconnect' | 'exit_dialog' | 'city' | 'world_map' | 'other'."""
        img = self._frame() if img is None else img
        if self.screen_fsm.is_disconnect(img):
            return "disconnect"
        if self.screen_fsm.identify(img) == "exit_dialog":
            return "exit_dialog"
        # Fast path: scope the city check to the Alliance/Mail corner (~4x cheaper).
        if is_city(self._read(img, CITY_BOX)):
            return "city"
        # Not clearly city — read the full frame for the world-map / other decision.
        texts = self._read(img)
        if is_worldmap(texts):
            return "world_map"
        return "other"

    def back(self):
        """Exit one screen level via the top-left back arrow (never a bottom button)."""
        self.ctx.tap(*BACK_ARROW, label="nav.back")
        self.sleep(2.0)

    def cancel_exit(self):
        """Dismiss the exit-game dialog with Cancel (never Quit)."""
        img = self._frame()
        c = self.find_button(img, "cancel") or EXIT_CANCEL
        self.ctx.tap(c[0], c[1], label="nav.cancel_exit")
        self.sleep(2.0)

    def to_city_toggle(self):
        """Toggle world map -> city via the globe button."""
        self.ctx.tap(*CITY_GLOBE, label="nav.globe")
        self.sleep(2.5)

    def ensure_city(self, tries=8):
        """Drive the UI back to the city view. Returns 'city' | 'disconnect' | 'unknown'.
        NEVER auto-reclaims a disconnect (that needs explicit consent via reclaim())."""
        for _ in range(max(1, tries)):
            s = self.state()
            if s == "disconnect":
                return "disconnect"
            if s == "city":
                return "city"
            if s == "exit_dialog":
                self.cancel_exit()
                continue
            if s == "world_map":
                self.to_city_toggle()
                continue
            self.back()
        return "city" if self.state() == "city" else "unknown"

    def close_radial(self):
        """Dismiss an open building radial by backing out (never taps a radial option)."""
        return self.ensure_city(tries=3)

    def reclaim(self, confirm=False, wait_steps=10, step_s=5.0):
        """On the disconnect screen, tap RESTART (never Quit) to reclaim the session.
        Requires confirm=True — reclaiming taps into a shared account and must be an
        explicit, consented action, never automatic. Returns a status string."""
        if not confirm:
            return "needs_consent"
        img = self._frame()
        if not self.screen_fsm.is_disconnect(img):
            return "not_disconnected"
        r = self.find_button(img, "restart")
        if not r:
            return "no_restart_button"
        self.ctx.tap(r[0], r[1], label="nav.restart")   # Restart, never Quit
        for _ in range(wait_steps):
            self.sleep(step_s)
            if not self.screen_fsm.is_disconnect(self._frame()):
                return "reclaimed"
        return "still_disconnected"


if __name__ == "__main__":
    ok = True

    CITY = [("115.2B", (270, 90), 0.9), ("Alliance", (988, 1515), 0.9), ("Mail", (987, 1685), 0.9),
            ("Lucky Raffle", (98, 1712), 0.8)]
    WORLD = [("X:0628", (486, 1700), 0.9), ("Y:0575", (640, 1700), 0.9), ("World Map", (98, 1720), 0.9)]
    BLAZON = [("Blazon", (216, 27), 0.9), ("Ground Troop", (95, 78), 0.8)]
    DISC = [("Restart", (718, 1136), 0.85), ("Quit", (363, 1134), 0.8)]

    class FakeCtx:
        def __init__(self, frames):
            self.frames = frames
            self.i = 0
            self.taps = []
        def screencap(self):
            f = self.frames[min(self.i, len(self.frames) - 1)]
            return f
        def tap(self, x, y, d=0.3, label="", radius=10):
            self.taps.append((x, y, label))
            self.i += 1   # advance to the next scripted frame after a tap

    def texts_of(frame):
        return frame  # frames ARE text lists in this test

    class FSM:
        def __init__(self, disc_frames=(), exit_frames=()):
            self.disc = set(id(f) for f in disc_frames)
            self.exitf = set(id(f) for f in exit_frames)
        def is_disconnect(self, img, min_score=0.85):
            return id(img) in self.disc
        def identify(self, img):
            return "exit_dialog" if id(img) in self.exitf else "unknown"

    def find_btn(img, label):
        for t, c, cf in img:
            if t.lower() == label.lower():
                return c
        return None

    # 1) is_city / is_worldmap classification
    print(f"1 is_city(CITY)={is_city(CITY)} is_city(WORLD)={is_city(WORLD)} is_worldmap(WORLD)={is_worldmap(WORLD)}")
    ok &= is_city(CITY) and not is_city(WORLD) and is_worldmap(WORLD)

    # 2) ensure_city: blazon -> back -> city (back arrow used, reaches city)
    ctx = FakeCtx([BLAZON, CITY])
    nav = Nav(ctx, read_all=texts_of, screen_fsm=FSM(), find_button=find_btn, sleep=lambda s: None)
    r = nav.ensure_city()
    print(f"2 ensure_city(blazon->city)={r} taps={ctx.taps}")
    ok &= r == "city" and ctx.taps == [(80, 72, "nav.back")]

    # 3) ensure_city: world_map -> globe toggle -> city
    ctx = FakeCtx([WORLD, CITY])
    nav = Nav(ctx, read_all=texts_of, screen_fsm=FSM(), find_button=find_btn, sleep=lambda s: None)
    r = nav.ensure_city()
    print(f"3 ensure_city(world->city)={r} taps={ctx.taps}")
    ok &= r == "city" and ctx.taps == [(994, 1790, "nav.globe")]

    # 4) ensure_city: exit_dialog -> Cancel (never Quit)
    ctx = FakeCtx([BLAZON, CITY])   # frame0 will be flagged exit_dialog
    fsm = FSM(exit_frames=[BLAZON])
    nav = Nav(ctx, read_all=texts_of, screen_fsm=fsm, find_button=find_btn, sleep=lambda s: None)
    r = nav.ensure_city()
    print(f"4 ensure_city(exit_dialog->cancel)={r} taps={ctx.taps}")
    ok &= r == "city" and ctx.taps and ctx.taps[0][2] == "nav.cancel_exit"

    # 5) disconnect: ensure_city returns 'disconnect' WITHOUT tapping
    ctx = FakeCtx([DISC])
    nav = Nav(ctx, read_all=texts_of, screen_fsm=FSM(disc_frames=[DISC]), find_button=find_btn, sleep=lambda s: None)
    r = nav.ensure_city()
    print(f"5 ensure_city(disconnect)={r} taps={ctx.taps} (must be no taps)")
    ok &= r == "disconnect" and ctx.taps == []

    # 6) reclaim needs consent; with consent taps RESTART (not Quit)
    ctx = FakeCtx([DISC, CITY])
    nav = Nav(ctx, read_all=texts_of, screen_fsm=FSM(disc_frames=[DISC]), find_button=find_btn, sleep=lambda s: None)
    print(f"6a reclaim(no consent)={nav.reclaim()}")
    ok &= nav.reclaim() == "needs_consent" and ctx.taps == []
    r = nav.reclaim(confirm=True)
    print(f"6b reclaim(confirm)={r} taps={ctx.taps} (must tap Restart 718,1136 not Quit)")
    ok &= r == "reclaimed" and ctx.taps == [(718, 1136, "nav.restart")]

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
