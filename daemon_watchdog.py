"""Process-level overnight watchdog: keep the core daemons alive so a crash at
3am doesn't silently stop rallies / research / the live view. Checks every ~2 min
and relaunches any daemon that has died, logging each restart. Detaches children
(start_new_session) so they survive this process too.

Distinct from watchdog.py, which detects an in-GAME crash (black screen / stuck)
and recovers Evony itself. This one guards the Python daemons."""
import os
import subprocess
import time

REPO = "/Users/sward/work/scratch/evony-bot"
PY = os.path.join(REPO, ".venv/bin/python")
LOGDIR = "/tmp/murderbot"
CHECK_S = 120

DAEMONS = [
    ("rally_night.py", [PY, "rally_night.py"]),
    ("research_night.py", [PY, "research_night.py"]),
    ("keep_live.py", [PY, "keep_live.py", "--port", "8000"]),
]


def _running(pattern):
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return bool(r.stdout.strip())


def _launch(name, argv):
    os.makedirs(LOGDIR, exist_ok=True)
    logf = open(os.path.join(LOGDIR, name + ".log"), "a")
    subprocess.Popen(argv, cwd=REPO, stdout=logf, stderr=subprocess.STDOUT,
                     start_new_session=True)


def main():
    os.makedirs(LOGDIR, exist_ok=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] daemon_watchdog up, guarding "
          f"{[d[0] for d in DAEMONS]}", flush=True)
    while True:
        for name, argv in DAEMONS:
            if not _running(name):
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {name} DOWN -> relaunching",
                      flush=True)
                _launch(name, argv)
        time.sleep(CHECK_S)


if __name__ == "__main__":
    main()
