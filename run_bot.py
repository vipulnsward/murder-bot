#!/usr/bin/env python3
"""Launchable entrypoint for the Evony bot.

Ties the Phase-0 stack into one command: the orchestrator (scheduler + FSM
disconnect-guard + watchdog), the macro activity schedule (human rhythm, kb/30),
humanized input, and notifications. Logs to console + a rotating file, and shuts
down cleanly on Ctrl-C.

  python run_bot.py                 # run for real (training task; gem-safe)
  python run_bot.py --dry-run       # wire everything, 0 ticks, no ADB (smoke test)
  python run_bot.py --no-macro      # 24/7, no sleep/breaks (NOT recommended, kb/30)
  python run_bot.py --llm-fallback  # escalate stuck states to the vision LLM (costs)

Exit codes: 0 done, 2 disconnect, 3 stopped (bot-tell/human), 1 error/other.
"""

import argparse
import logging
import logging.handlers
import os
import signal
import sys

RESULT_EXIT = {"done": 0, "error": 1, "disconnect": 2, "stopped": 3}
_STOP = {"flag": False}


def build_parser():
    p = argparse.ArgumentParser(prog="run_bot", description="Evony bot launcher (gem-safe).")
    p.add_argument("--device", default="127.0.0.1:5555")
    p.add_argument("--max-ticks", type=int, default=None, help="stop after N ticks (default: run forever)")
    p.add_argument("--dry-run", action="store_true", help="wire everything, run 0 ticks, no ADB")
    p.add_argument("--no-macro", action="store_true", help="disable the human-rhythm schedule (24/7)")
    p.add_argument("--no-watchdog", action="store_true", help="disable crash/stuck recovery")
    p.add_argument("--llm-fallback", action="store_true", help="escalate stuck states to the vision LLM")
    p.add_argument("--log-file", default="evony_bot.log")
    p.add_argument("--quiet", action="store_true", help="console warnings+ only (file still full)")
    return p


def configure_logging(log_file, quiet=False):
    logger = logging.getLogger("evony")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    con = logging.StreamHandler()
    con.setLevel(logging.WARNING if quiet else logging.INFO)
    con.setFormatter(fmt)
    logger.addHandler(con)
    if log_file:
        fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def _install_signals(logger):
    def handler(signum, _frame):
        _STOP["flag"] = True
        logger.warning(f"signal {signum} received -> graceful stop after current tick")
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass   # not on the main thread (e.g. under test) -> skip


def main(argv=None):
    args = build_parser().parse_args(argv)
    logger = configure_logging(args.log_file, quiet=args.quiet)
    _install_signals(logger)

    import notify
    import orchestrator

    max_ticks = 0 if args.dry_run else args.max_ticks
    mode = "DRY-RUN" if args.dry_run else "live"
    logger.info(f"evony-bot starting [{mode}] device={args.device} "
                f"macro={'off' if args.no_macro else 'on'} watchdog={'off' if args.no_watchdog else 'on'} "
                f"llm_fallback={args.llm_fallback}")
    if not args.dry_run:
        notify.notify(f"evony-bot starting ({mode})", "info")

    try:
        result = orchestrator.run(
            device=args.device,
            max_ticks=max_ticks,
            logger=logger.info,
            llm_fallback=args.llm_fallback,
            macro=(False if args.no_macro else "default"),
            watchdog=not args.no_watchdog,
            should_stop=lambda: _STOP["flag"],
        )
    except KeyboardInterrupt:
        result = "stopped"
        logger.warning("KeyboardInterrupt -> stopped")
    except Exception as e:                      # never crash silently; surface + notify
        logger.exception("orchestrator crashed")
        if not args.dry_run:
            notify.notify(f"evony-bot CRASHED: {e}", "alert")
        return RESULT_EXIT["error"]

    logger.info(f"orchestrator returned: {result}")
    if not args.dry_run:
        notify.notify(f"evony-bot stopped: {result}",
                      "info" if result == "done" else "warn")
    return RESULT_EXIT.get(result, 1)


if __name__ == "__main__" and not os.environ.get("RUN_BOT_SELFTEST"):
    sys.exit(main())


if os.environ.get("RUN_BOT_SELFTEST"):
    ok = True
    os.environ["EVONY_NOTIFY_MAC"] = "0"

    # 1) parser wires flags correctly
    a = build_parser().parse_args(["--device", "1.2.3.4:5", "--no-macro", "--dry-run", "--llm-fallback"])
    print(f"parse -> device={a.device} no_macro={a.no_macro} dry_run={a.dry_run} llm={a.llm_fallback}")
    ok &= a.device == "1.2.3.4:5" and a.no_macro and a.dry_run and a.llm_fallback

    # 2) logging writes to a file
    import tempfile
    lf = os.path.join(tempfile.gettempdir(), "evony_selftest.log")
    open(lf, "w").close()
    lg = configure_logging(lf)
    lg.info("hello-selftest")
    for h in lg.handlers:
        h.flush()
    wrote = "hello-selftest" in open(lf).read()
    print(f"logging -> file_wrote={wrote}")
    ok &= wrote

    # 3) full-wiring smoke test with no ADB: --dry-run => orchestrator runs 0 ticks => 'done' => exit 0
    rc = main(["--dry-run", "--log-file", lf])
    body = open(lf).read()
    print(f"dry-run -> exit={rc} logged_start={'DRY-RUN' in body} logged_done={'returned: done' in body}")
    ok &= rc == 0 and "DRY-RUN" in body and "returned: done" in body

    # 4) exit-code mapping
    print(f"exit map -> disconnect={RESULT_EXIT['disconnect']} stopped={RESULT_EXIT['stopped']}")
    ok &= RESULT_EXIT["disconnect"] == 2 and RESULT_EXIT["stopped"] == 3

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
