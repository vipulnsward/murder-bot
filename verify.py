"""Read-only post-action verification predicates for Evony skills."""

import game_hud
import gen_fsm
import live_map
import live_rally
import nav
import ocr_read
import screen_fsm


def is_city(frame):
    return frame is not None and nav.is_city(
        ocr_read.read_all(frame, box=nav.CITY_BOX, cache=True)
    )


def no_popup(frame):
    return frame is not None and not live_map.has_popup(frame)


def on_war_screen(frame):
    return frame is not None and live_rally.on_war_screen(frame)


def rally_joined(frame):
    return on_war_screen(frame) and any(
        rally["status"] == "joined" for rally in live_rally.read_rallies(frame)
    )


def not_ideal_land(frame):
    return frame is not None and not live_map.is_ideal_land(frame)


def hud_ok(frame):
    return frame is not None and bool(game_hud.read_hud(frame).get("ok"))


def disconnected(frame):
    return frame is not None and screen_fsm.is_disconnect(frame)


def buildings_detected(frame):
    """The detector ran successfully; an empty candidate list is a valid result."""
    return frame is not None and live_map.find_building_candidates(frame) is not None


def valid_screen_label(frame):
    if frame is None:
        return False
    label, score = gen_fsm.classify(frame)
    return isinstance(label, str) and bool(label) and isinstance(score, (int, float))


if __name__ == "__main__":
    import shared_capture

    live_frame = shared_capture.grab_wait("127.0.0.1:5555")
    if live_frame is None:
        raise SystemExit("No fresh shared frame available")
    for name in (
        "is_city", "no_popup", "on_war_screen", "rally_joined",
        "not_ideal_land", "hud_ok", "disconnected", "buildings_detected",
        "valid_screen_label",
    ):
        print(f"{name}: {globals()[name](live_frame)}")
