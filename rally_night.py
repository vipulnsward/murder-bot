"""All-night rally loop: the proven single-shot cycle
(ensure_game -> clear_popups -> live_rally.run -> stamina -> clear_popups) run
forever on a fixed cadence, so no rally is missed overnight. Gem-safe: never taps
Buy/Confirm/Quit; clear_popups now also dismisses stacked pack notices via the
learned cross. Disconnects are handled by live_map.ensure_game (restart-only)."""
import sys
import time

sys.path.insert(0, ".")

import live_map
import live_rally

DEV = "127.0.0.1:5555"
CADENCE_S = 80          # scan roughly every ~80s + cycle time; rallies live ~5 min
STAMINA_FLOOR = 5000


def _cycle():
    live_map.ensure_game()
    live_map.clear_popups(max_iters=6)
    joined = live_rally.run(max_marches=6)
    stamina = "off"
    try:
        import stamina as _st
        stamina = _st.top_up_if_low(STAMINA_FLOOR)
    except Exception:
        stamina = "err"
    live_map.clear_popups(max_iters=3)
    try:
        import game_hud
        import shared_capture
        game_hud.write_hud(game_hud.read_hud(shared_capture.grab_wait(DEV, timeout=6)))
    except Exception:
        pass
    return joined, stamina


def main():
    total = 0
    cycles = 0
    while True:
        cycles += 1
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            joined, stamina = _cycle()
            if isinstance(joined, int):
                total += joined
            print(f"[{stamp}] cycle={cycles} joined={joined} stamina={stamina} total_joined={total}",
                  flush=True)
        except Exception as exc:  # noqa: BLE001 — never let one bad cycle kill the night
            print(f"[{stamp}] cycle={cycles} ERROR: {exc!r}", flush=True)
        time.sleep(CADENCE_S)


if __name__ == "__main__":
    main()
