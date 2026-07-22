"""Small rule-based proposer for the next registered Evony skill."""

import game_hud
import live_map
import live_rally
import nav
import ocr_read
import shared_capture


def next_task(hud, frame):
    if live_map.is_ideal_land(frame):
        return "exit_ideal_land"
    if live_rally.on_war_screen(frame) and any(
        rally["status"] == "joinable" for rally in live_rally.read_rallies(frame)
    ):
        return "join_monster_rallies"
    texts = ocr_read.read_all(frame, box=nav.CITY_BOX, cache=True) if frame is not None else []
    if not nav.is_city(texts):
        return "dismiss_popups"
    return "read_city_stats"


if __name__ == "__main__":
    live_frame = shared_capture.grab_wait("127.0.0.1:5555")
    if live_frame is None:
        raise SystemExit("No fresh shared frame available")
    live_hud = game_hud.read_hud(live_frame)
    print(f"curriculum.next_task: {next_task(live_hud, live_frame)}")
