"""Disconnect-safe, gem-safe visual mapping for the Evony game world."""

OCR_MIN_CONF = 0.5
GEM_WORDS = ("gem", "purchase", "buy", "finish all", "speed up", "speedup", "instant")

KNOWN_TEMPLATES = (
    "back_arrow", "barracks_bldg", "cap_popup", "disconnect_popup",
    "exit_dialog", "finish_all_btn", "food_1m_label", "food_1m_use_btn",
    "instant_train_btn", "modal_speedup_title", "radial_speedup",
    "radial_train", "slider_minus", "slider_plus", "speedup_btn",
    "train_btn_idle", "use_btn", "warrior_t1_icon", "warriors_title",
)

NOTIFICATION_ZONES = (
    ("bottom_1_notification", (0, 1700, 216, 1920)),
    ("bottom_2_notification", (216, 1700, 432, 1920)),
    ("bottom_3_notification", (432, 1700, 648, 1920)),
    ("bottom_4_notification", (648, 1700, 864, 1920)),
    ("bottom_5_notification", (864, 1700, 1080, 1920)),
)

DEFAULT_PLAN = [
    {"action": "map"},
    {"action": "swipe", "x1": 540, "y1": 960, "x2": 820, "y2": 960},
    {"action": "map"},
    {"action": "swipe", "x1": 820, "y1": 960, "x2": 540, "y2": 960},
    {"action": "map"},
    {"action": "swipe", "x1": 540, "y1": 960, "x2": 540, "y2": 1240},
    {"action": "map"},
    {"action": "swipe", "x1": 540, "y1": 1240, "x2": 540, "y2": 960},
    {"action": "map"},
    {"action": "find_tap", "description": "the Alliance icon in the bottom navigation bar", "label": "Alliance"},
    {"action": "map"},
    {"action": "back"},
    {"action": "find_tap", "description": "the Mail icon in the bottom navigation bar", "label": "Mail"},
    {"action": "map"},
    {"action": "back"},
    {"action": "find_tap", "description": "the Items icon in the bottom navigation bar", "label": "Items"},
    {"action": "map"},
    {"action": "back"},
    {"action": "find_tap", "description": "the Quests icon in the bottom navigation bar", "label": "Quests"},
    {"action": "map"},
    {"action": "back"},
    {"action": "find_tap", "description": "the globe button that opens the world map", "label": "World map"},
    {"action": "map"},
    {"action": "find_tap", "description": "the minus button that zooms the world map out", "label": "Map zoom out"},
    {"action": "map"},
    {"action": "swipe", "x1": 760, "y1": 960, "x2": 360, "y2": 960},
    {"action": "map"},
    {"action": "swipe", "x1": 760, "y1": 960, "x2": 360, "y2": 960},
    {"action": "map"},
    {"action": "swipe", "x1": 540, "y1": 1180, "x2": 540, "y2": 780},
    {"action": "map"},
    {"action": "swipe", "x1": 360, "y1": 960, "x2": 760, "y2": 960},
    {"action": "map"},
    {"action": "swipe", "x1": 360, "y1": 960, "x2": 760, "y2": 960},
    {"action": "map"},
    {"action": "swipe", "x1": 540, "y1": 1180, "x2": 540, "y2": 780},
    {"action": "map"},
    {"action": "swipe", "x1": 760, "y1": 960, "x2": 360, "y2": 960},
    {"action": "map"},
    {"action": "swipe", "x1": 760, "y1": 960, "x2": 360, "y2": 960},
    {"action": "map"},
    {"action": "back"},
]


def _real_defaults(classify, read_all, screen_fsm):
    if classify is None:
        from screen_id import classify
    if read_all is None:
        from ocr_read import read_all
    if screen_fsm is None:
        import screen_fsm
    return classify, read_all, screen_fsm


def _classification(result):
    if isinstance(result, str):
        return result, "", 0
    label, description, score = result
    return str(label), description, score


def _record_known_elements(ctx, db, label, img):
    perception = getattr(ctx, "perception", None)
    if perception is None:
        import perception
    count = 0
    for template in KNOWN_TEMPLATES:
        try:
            hits = perception.find_all(img, template)
        except Exception:
            hits = []
        for index, (cx, cy) in enumerate(hits, 1):
            name = f"template:{template}:{index}"
            db.add_element(label, name, cx, cy, description="template match")
            count += 1
    for name, box in NOTIFICATION_ZONES:
        try:
            found = perception.red_dot(img, box)
        except Exception:
            found = False
        if found:
            x1, y1, x2, y2 = box
            db.add_element(label, name, (x1 + x2) // 2, (y1 + y2) // 2,
                           description="red notification dot")
            count += 1
    return count


def map_current(ctx, db, classify=None, read_all=None, screen_fsm=None) -> dict:
    """Capture, classify, OCR, and persist the current screen."""
    classify, read_all, screen_fsm = _real_defaults(classify, read_all, screen_fsm)
    img = ctx.screencap()
    if screen_fsm.is_disconnect(img):
        ctx.log("mapper: disconnect detected; stopping without input")
        return {"screen": "disconnect", "stopped": True}

    label, description, _score = _classification(classify(img))
    db.upsert_screen(label, description=description)
    raw_texts = list(read_all(img))
    capture_elements = []
    stored = 0
    for text, (cx, cy), conf in raw_texts:
        text = str(text)
        confidence = float(conf)
        capture_elements.append({"text": text, "cx": cx, "cy": cy, "conf": confidence})
        if confidence > OCR_MIN_CONF:
            db.add_element(label, text[:40], cx, cy,
                           description=f"ocr text conf={confidence:.2f}")
            stored += 1

    stored += _record_known_elements(ctx, db, label, img)
    db.record_capture(
        image_path=None,
        phash=db.phash(img),
        screen_label=label,
        ocr_text=" | ".join(text for text, _, _ in raw_texts),
        elements=capture_elements,
    )
    summary = {"screen": label, "n_texts": len(raw_texts), "n_elements": stored}
    ctx.log(f"mapper: {label} texts={len(raw_texts)} elements={stored}")
    return summary


def _safe_tap(step):
    words = " ".join(str(value) for value in step.values()).lower()
    if any(word in words for word in GEM_WORDS):
        return False
    return not (step.get("action") == "tap" and step.get("x", 0) > 800 and step.get("y", 1920) < 200)


def _guard(ctx, screen_fsm):
    img = ctx.screencap()
    if screen_fsm.is_disconnect(img):
        ctx.log("mapper: disconnect detected; stopping without input")
        return None
    return img


def explore(ctx, db, plan=None, max_steps=60) -> list[dict]:
    """Execute a bounded data plan, mapping views and guarding every input."""
    classify = getattr(ctx, "classify", None)
    read_all = getattr(ctx, "read_all", None)
    screen_fsm = getattr(ctx, "screen_fsm", None)
    classify, read_all, screen_fsm = _real_defaults(classify, read_all, screen_fsm)
    results = []
    steps = DEFAULT_PLAN if plan is None else plan

    for index, step in enumerate(steps):
        if index >= max(0, max_steps):
            break
        action = step.get("action")
        ctx.log(f"mapper: step {index + 1}/{min(len(steps), max_steps)} {action}")
        if action == "map":
            result = map_current(ctx, db, classify, read_all, screen_fsm)
            results.append(result)
            if result.get("stopped"):
                break
            continue

        img = _guard(ctx, screen_fsm)
        if img is None:
            results.append({"screen": "disconnect", "stopped": True})
            break
        if action in ("tap", "find_tap") and not _safe_tap(step):
            ctx.log(f"mapper: skipped unsafe tap step {index + 1}")
            continue
        if action == "tap":
            ctx.tap(step["x"], step["y"], label=step.get("label", "mapper"))
        elif action == "find_tap":
            ctx.find_tap(step["description"], label=step.get("label", ""), img=img)
        elif action == "swipe":
            ctx.swipe(step["x1"], step["y1"], step["x2"], step["y2"])
        elif action == "back":
            ctx.back()
        else:
            ctx.log(f"mapper: skipped unknown action {action!r}")
    return results


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    import numpy as np

    from vision_db import VisionDB

    class Frame(np.ndarray):
        """Numpy image carrying deterministic fake-frame metadata."""

    class FakePerception:
        def find_all(self, img, template):
            return []

        def red_dot(self, img, box):
            return False

    class FakeCtx:
        def __init__(self, session):
            self.session = session
            self.frame = 0
            self.calls = []
            self.logs = []
            self.perception = FakePerception()

        def screencap(self):
            self.frame += 1
            seed = self.frame + sum(map(ord, self.session))
            image = np.random.default_rng(seed).integers(0, 256, (80, 80, 3), dtype=np.uint8).view(Frame)
            image.index = self.frame
            image.session = self.session
            self.calls.append(("screencap", self.frame))
            return image

        def tap(self, x, y, label=""):
            self.calls.append(("tap", self.frame, x, y, label))

        def swipe(self, x1, y1, x2, y2):
            self.calls.append(("swipe", self.frame, x1, y1, x2, y2))

        def back(self):
            self.calls.append(("back", self.frame))

        def find(self, description, img=None):
            return (120, 180)

        def find_tap(self, description, label="", img=None):
            point = self.find(description, img)
            if point is not None:
                self.tap(*point, label=label or description)
            return point

        def log(self, message):
            self.logs.append(message)

    class FakeFSM:
        def __init__(self, ctx, disconnect_on=None):
            self.ctx = ctx
            self.disconnect_on = disconnect_on
            self.tap_count_at_disconnect = None

        def is_disconnect(self, img):
            disconnected = self.disconnect_on is not None and img.index >= self.disconnect_on
            if disconnected and self.tap_count_at_disconnect is None:
                self.tap_count_at_disconnect = sum(call[0] == "tap" for call in self.ctx.calls)
            return disconnected

    def fake_classify(img):
        return f"{img.session}_{img.index}", f"fake {img.session} screen", 1

    def fake_read_all(img):
        return [
            ("Keep", (100, 200), 0.99),
            ("Alliance", (300, 400), 0.88),
            ("World Map", (500, 600), 0.75),
        ]

    ok = True
    with tempfile.TemporaryDirectory() as temporary:
        db = VisionDB(Path(temporary) / "vision.db", dedup_dist=0)

        try:
            one = FakeCtx("single")
            one.screen_fsm = FakeFSM(one)
            summary = map_current(one, db, fake_classify, fake_read_all, one.screen_fsm)
            expected = {("Keep", 100, 200), ("Alliance", 300, 400), ("World Map", 500, 600)}
            actual = {(row["name"], row["cx"], row["cy"]) for row in db.elements("single_1")}
            captures = [row for row in db.search("Keep") if row["type"] == "capture"]
            assert summary == {"screen": "single_1", "n_texts": 3, "n_elements": 3}
            assert actual == expected
            assert len(captures) == 1
            assert captures[0]["elements"] == [
                {"text": "Keep", "cx": 100, "cy": 200, "conf": 0.99},
                {"text": "Alliance", "cx": 300, "cy": 400, "conf": 0.88},
                {"text": "World Map", "cx": 500, "cy": 600, "conf": 0.75},
            ]
            print("a) OCR elements and capture persistence: PASS")
        except Exception as error:
            ok = False
            print(f"a) OCR elements and capture persistence: FAIL ({error!r})")

        try:
            explorer = FakeCtx("explore")
            explorer.classify = fake_classify
            explorer.read_all = fake_read_all
            explorer.screen_fsm = FakeFSM(explorer, disconnect_on=5)
            small_plan = [
                {"action": "map"},
                {"action": "tap", "x": 100, "y": 1800, "label": "safe menu"},
                {"action": "map"},
                {"action": "back"},
                {"action": "tap", "x": 200, "y": 1800, "label": "must not happen"},
            ]
            results = explore(explorer, db, small_plan, max_steps=10)
            taps = [call for call in explorer.calls if call[0] == "tap"]
            mapped = [result["screen"] for result in results if not result.get("stopped")]
            assert mapped == ["explore_1", "explore_3"]
            assert results[-1] == {"screen": "disconnect", "stopped": True}
            assert explorer.screen_fsm.tap_count_at_disconnect == 1
            assert len(taps) == explorer.screen_fsm.tap_count_at_disconnect
            assert all(call[1] < explorer.screen_fsm.disconnect_on for call in taps)
            print("b) explore disconnect stop and no post-disconnect tap: PASS")
        except Exception as error:
            ok = False
            print(f"b) explore disconnect stop and no post-disconnect tap: FAIL ({error!r})")

        try:
            assert db.stats() == {"screens": 3, "captures": 3, "elements": 9}
            print(f"c) VisionDB growth {db.stats()}: PASS")
        except Exception as error:
            ok = False
            print(f"c) VisionDB growth {db.stats()}: FAIL ({error!r})")
        db.close()

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
