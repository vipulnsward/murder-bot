"""Auto-research loop: keep learning about Evony from OUTSIDE the game.

Periodically ingests authoritative Evony guide pages (and YouTube transcripts)
and distills them — Kimi-refined when MOONSHOT_API_KEY is set — into the brain's
knowledge_distilled.md, which counter_ai/pvp reads. Runs alongside the rally
loop so the bot learns by research, not only by playing."""
import os
import subprocess
import sys
import time

PY = sys.executable
CADENCE_S = 3 * 3600          # a research pass every ~3 hours (guides change slowly)
STEP_TIMEOUT = 1200


def _run(args):
    try:
        r = subprocess.run([PY] + args, capture_output=True, text=True, timeout=STEP_TIMEOUT)
        tail = ((r.stdout or "").strip()[-600:]) + ("\n" + (r.stderr or "").strip()[-200:] if r.stderr else "")
        return tail.strip() or "(no output)"
    except Exception as exc:  # noqa: BLE001
        return f"ERR {exc!r}"


def main():
    n = 0
    while True:
        n += 1
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{stamp}] === research pass {n}: ingest guides (--web) ===", flush=True)
        print(_run(["knowledge_ingest.py", "--web"]), flush=True)
        print(f"[{stamp}] === research pass {n}: ingest YouTube (best generals) ===", flush=True)
        print(_run(["knowledge_ingest.py", "--youtube", "evony best general 2025", "-n", "3"]), flush=True)
        chans = [c.strip() for c in os.environ.get("DISCORD_CHANNELS", "").split(",") if c.strip()]
        if os.environ.get("DISCORD_BOT_TOKEN") and chans:
            print(f"[{stamp}] === research pass {n}: ingest Discord ({len(chans)} channels) ===", flush=True)
            dargs = ["discord_ingest.py"]
            for c in chans:
                dargs += ["--channel", c]
            dargs += ["-n", "200", "--topic", "pvp"]
            print(_run(dargs), flush=True)
        else:
            print(f"[{stamp}] discord: skipped (set DISCORD_BOT_TOKEN + DISCORD_CHANNELS to enable)", flush=True)
        print(f"[{stamp}] === research pass {n}: synth (Kimi-refined) ===", flush=True)
        print(_run(["knowledge_synth.py", "--synth", "--llm"]), flush=True)
        print(f"[{stamp}] === coverage after pass {n} ===", flush=True)
        print(_run(["knowledge_synth.py", "--stats"]), flush=True)
        time.sleep(CADENCE_S)


if __name__ == "__main__":
    main()
