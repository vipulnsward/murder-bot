#!/usr/bin/env python3
"""Run every module's self-test and report — the project's health check.

Each module has an `if __name__ == "__main__":` block that ends in
`SELF-TEST: PASS|FAIL`. This runs the pure-logic suite (no ADB, no heavy model),
so a green run means the decision policies, safety guards, humanizer, scheduler,
perception toolkit, and vision-classification logic are all intact.

  python selftest.py           # pure-logic suite (fast; default)
  python selftest.py --holo    # also run holo_vision (loads the 15GB model)
  python selftest.py --device  # also run device tests (needs ADB + emulator)

Exit 0 iff every selected test passes.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = str(HERE / ".venv" / "bin" / "python")

# module -> env overrides (run_bot gates its self-test behind a flag)
PURE = [
    "humanize", "notify", "macro_schedule",
    "auto_shield", "daily_collect", "alliance", "base_dev",
    "gather", "rally_join", "monster",
    "perception", "screen_id", "screen_fsm",
    "scheduler", "multiscale", "orchestrator",
]
RUN_BOT = ("run_bot", {"RUN_BOT_SELFTEST": "1"})
HOLO = ["holo_vision"]
DEVICE = ["watchdog", "ocr_read", "fast_screenshot"]


def _run(module, env_extra=None, timeout=180):
    path = HERE / f"{module}.py"
    if not path.exists():
        return module, "MISSING", ""
    import os
    env = {**os.environ, **(env_extra or {})}
    try:
        p = subprocess.run([PY, str(path)], capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return module, "TIMEOUT", ""
    out = p.stdout + p.stderr
    if "SELF-TEST: FAIL" in out or p.returncode != 0:
        status = "FAIL"
    elif "SELF-TEST: PASS" in out:
        status = "PASS"
    else:
        status = "PASS?"   # exited clean but printed no explicit verdict
    tail = "\n".join(l for l in out.splitlines() if l.strip())[-400:]
    return module, status, tail


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    targets = [(m, None) for m in PURE] + [RUN_BOT]
    if "--holo" in argv:
        targets += [(m, None) for m in HOLO]
    if "--device" in argv:
        targets += [(m, None) for m in DEVICE]

    results = []
    for module, env_extra in targets:
        module_name = module if isinstance(module, str) else module
        name, status, tail = _run(module_name, env_extra)
        results.append((name, status))
        mark = {"PASS": "✓", "PASS?": "~", "FAIL": "✗", "TIMEOUT": "⧗", "MISSING": "?"}.get(status, "✗")
        print(f"  {mark} {name:16s} {status}")
        if status in ("FAIL", "TIMEOUT") and tail:
            print("      " + tail.replace("\n", "\n      ")[-360:])

    passed = sum(1 for _, s in results if s in ("PASS", "PASS?"))
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
