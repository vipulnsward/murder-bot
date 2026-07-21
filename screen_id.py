"""screen_id — Holo-based fallback screen classification for Evony (kb/31).

Asks Holo to describe an untemplated screen, then maps description keywords to
a known label. Complements screen_fsm's fast template matching.
"""


# Screen catalog, ordered from specific dialogs to broad views
SCREENS = [
    ("disconnect", ("disconnect", "logged in", "quit", "restart")),
    ("exit_dialog", ("exit game", "exit dialog", "confirm exit", "cancel")),
    ("speedup_modal", ("speed up", "finish all", "speedup", "use speedups")),
    ("radial_dial", ("radial", "circular menu", "action wheel", "speed up ring")),
    ("training_barracks", ("train", "troop", "barracks", "training queue")),
    ("search_panel", ("search panel", "search coordinates", "level range", "search button")),
    ("rally_list", ("rally list", "war rally", "join rally", "rally timer")),
    ("watchtower", ("watchtower", "incoming attack", "enemy march", "march details")),
    ("academy_research", ("academy research", "research tree", "technology", "research button")),
    ("shield_truce", ("truce agreement", "peace shield", "shield duration", "buy and use")),
    ("keep_menu", ("keep menu", "upgrade keep", "keep level", "city buff")),
    ("world_map", ("world map", "map", "tiles", "zoomed out")),
    ("resources", ("resource", "food", "wood", "stone", "ore")),
    ("alliance", ("alliance", "members", "alliance science", "alliance help")),
    ("monster", ("monster", "boss", "stamina", "attack monster")),
    ("mail", ("mail", "inbox", "system message", "battle report")),
    ("city", ("city view", "city", "buildings", "inside the walls")),
]

QUESTION = "In one sentence, what game screen or dialog is shown and what are its main buttons?"


# Public API
def classify(img, describe_fn=None, min_hits=1):
    if describe_fn is None:
        from holo_vision import describe as describe_fn

    # The Holo backend needs a path/PIL image; a raw cv2/numpy frame is written to
    # a temp PNG first (injected describe_fns for tests just get the value as-is).
    describe_arg, _tmp = img, None
    try:
        import numpy as _np
        if isinstance(img, _np.ndarray):
            import cv2 as _cv2
            import tempfile as _tf
            _tmp = _tf.NamedTemporaryFile(suffix=".png", delete=False).name
            _cv2.imwrite(_tmp, img)
            describe_arg = _tmp
    except Exception:
        describe_arg = img
    try:
        description = describe_fn(describe_arg, QUESTION)
    finally:
        if _tmp:
            import os as _os
            try:
                _os.unlink(_tmp)
            except OSError:
                pass
    lowered = description.lower()
    best_label = "unknown"
    best_score = 0
    for label, keywords in SCREENS:
        score = sum(keyword in lowered for keyword in keywords)
        if score > best_score:
            best_label, best_score = label, score
    if best_score < min_hits:
        return "unknown", description, 0
    return best_label, description, best_score


def is_screen(img, label, describe_fn=None):
    return classify(img, describe_fn)[0] == label


# Deterministic self-test
if __name__ == "__main__":
    cases = [
        ("A message says you were disconnected because someone logged in; buttons Quit and Restart.", "disconnect"),
        ("The troop training screen for barracks with a green Train button.", "training_barracks"),
        ("A zoomed-out world map showing resource tiles and monsters.", "world_map"),
        ("The city view with buildings like keep and academy.", "city"),
        ("A resource inventory listing food, wood, stone, ore items.", "resources"),
        ("An unrelated image with no recognizable game interface.", "unknown"),
    ]

    def fake_describe(description, _question):
        return description

    ok = True
    for description, expected in cases:
        got = classify(description, fake_describe)[0]
        print(f"expected={expected} got={got}")
        try:
            assert got == expected
        except AssertionError:
            ok = False

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
