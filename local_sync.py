"""Send the local Evony bot's latest read-only state to the product."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
VISION_DB = ROOT / "game_brain" / "vision.db"
# The live rally daemon (and the watchdog) log here; overridable with --log.
DEFAULT_LOG = Path("/tmp/murderbot/rally_night.log")
DEVICE = "127.0.0.1:5555"

# (display name, pgrep pattern) for the core bot daemons whose health we surface.
DAEMON_PATTERNS = [
    ("rally", "rally_night.py"),
    ("map", "map_night.py"),
    ("research", "research_night.py"),
    ("live-view", "keep_live.py --device 127.0.0.1:5555"),
    ("watchdog", "daemon_watchdog.py"),
]


def read_roster(db_path: Path = VISION_DB) -> list[dict]:
    if not db_path.is_file():
        raise FileNotFoundError(f"troop database not found: {db_path}")
    uri = f"{db_path.resolve().as_uri()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT building, tier, name, own FROM troops ORDER BY building, tier, name"
        ).fetchall()
    return [dict(zip(("building", "tier", "name", "own"), row)) for row in rows]


def read_rally(log_path: Path) -> dict:
    if not log_path.is_file():
        raise FileNotFoundError(
            f"rally log not found: {log_path}; pass --log /path/to/rally_night.log"
        )
    total_joined = last_ts = None
    max_cycle = 0
    for line in log_path.read_text(errors="replace").splitlines():
        if match := re.search(r"\[([^]]+)]", line):
            last_ts = match.group(1)
        if match := re.search(r"\btotal_joined=(\d+)", line):
            total_joined = int(match.group(1))
        if match := re.search(r"\bcycle=(\d+)", line):
            max_cycle = max(max_cycle, int(match.group(1)))
    if total_joined is None:
        raise ValueError(f"no total_joined=N entry found in rally log: {log_path}")
    return {"total_joined": total_joined, "cycles": max_cycle, "last_ts": last_ts}


def read_log_extras(log_path: Path) -> tuple[dict, list[dict], str | None]:
    """From the rally log: free-claim tallies (Alliance Gift + Treasure), a recent activity
    feed (most-recent-first), and the latest stamina reading. Tolerant of a missing log."""
    claims = {"gift_open_alls": 0, "gift_claims": 0,
              "treasure_open_alls": 0, "treasure_opens": 0, "last_claim_ts": None}
    activity: list[dict] = []
    stamina = None
    if not log_path.is_file():
        return claims, activity, stamina
    lines = log_path.read_text(errors="replace").splitlines()
    last_ts = None
    for line in lines:
        if m := re.search(r"\[([^]]+)]", line):
            last_ts = m.group(1)
        if g := re.search(
            r"free-claim: gift\(open_all=(\w+), claims=(\d+)\) "
            r"treasure\(open_all=(\w+), opens=(\d+)\)", line
        ):
            claims["gift_open_alls"] += g.group(1) == "True"
            claims["gift_claims"] += int(g.group(2))
            claims["treasure_open_alls"] += g.group(3) == "True"
            claims["treasure_opens"] += int(g.group(4))
            claims["last_claim_ts"] = last_ts
        if s := re.search(r"stamina=(\S+)", line):
            stamina = s.group(1)
    feed: list[dict] = []
    for line in lines[-80:]:
        ts = m.group(1) if (m := re.search(r"\[([^]]+)]", line)) else None
        text = None
        if c := re.search(r"cycle=(\d+) (?:RETRY )?joined=(\S+) stamina=(\S+) total_joined=(\d+)", line):
            text = (f"cycle {c.group(1)} — joined {c.group(2)}, "
                    f"stamina {c.group(3)}, total {c.group(4)}")
        elif "free-claim:" in line:
            text = "claimed free rss — " + line.split("free-claim:", 1)[1].strip()
        elif "[RELOAD]" in line and "fresh session" in line:
            text = "fresh game reload"
        if text:
            feed.append({"ts": ts, "text": text[:240]})
    activity = feed[-12:][::-1]
    return claims, activity, stamina


def _pgrep(pattern: str) -> str:
    try:
        return subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def read_daemons() -> list[dict]:
    return [{"name": name, "running": bool(_pgrep(pat))} for name, pat in DAEMON_PATTERNS]


def read_uptime() -> str | None:
    """Elapsed run time of the rally daemon (its ps etime), e.g. '01:23:45'."""
    pids = _pgrep("rally_night.py")
    if not pids:
        return None
    try:
        out = subprocess.run(["ps", "-o", "etime=", "-p", pids.split()[0]],
                             capture_output=True, text=True).stdout.strip()
        return out or None
    except Exception:
        return None


def read_account() -> tuple[dict, dict]:
    account = {"name": "NeoIsTlatoani", "level": None, "vip": None, "alliance": "NFG", "power": None}
    frame = None
    hud = {}
    try:
        import game_hud
        import shared_capture

        frame = shared_capture.grab(DEVICE)
        hud = game_hud.read_hud(frame) if callable(getattr(game_hud, "read_hud", None)) else {}
    except Exception as exc:
        print(f"HUD read unavailable: {exc}", file=sys.stderr)
    if hud:
        account.update({key: hud.get(key) for key in ("level", "vip", "power")})
    screen = "city" if hud.get("ok") else ("captured" if frame is not None else "unavailable")
    return account, {"running": frame is not None, "screen": screen}


def assemble_payload(log_path: Path) -> dict:
    account, status = read_account()
    claims, activity, stamina = read_log_extras(log_path)
    status["stamina"] = stamina
    status["uptime"] = read_uptime()
    return {
        "account": account,
        "roster": read_roster(),
        "rally": read_rally(log_path),
        "status": status,
        "claims": claims,
        "daemons": read_daemons(),
        "activity": activity,
    }


def send_once(log_path: Path, base_url: str) -> bool:
    payload_json = json.dumps(assemble_payload(log_path), separators=(",", ":"), ensure_ascii=False)
    print("JSON payload:")
    print(payload_json)
    headers = {"Content-Type": "application/json"}
    if token := os.environ.get("MYBOT_SYNC_TOKEN"):
        headers["X-Sync-Token"] = token
    request = Request(
        f"{base_url.rstrip('/')}/api/mybot/report",
        data=payload_json.encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode(errors="replace")
            print(f"HTTP status: {response.status}")
            print(f"Response body: {body}")
            return 200 <= response.status < 300
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"HTTP status: {exc.code}")
        print(f"Response body: {body}")
    except URLError as exc:
        print("HTTP status: unavailable")
        print(f"Response body: {exc.reason}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, help="rally log path (overrides the known local path)")
    parser.add_argument("--interval", type=float, help="repeat every N seconds")
    args = parser.parse_args()
    if args.interval is not None and args.interval <= 0:
        parser.error("--interval must be greater than zero")
    log_path = args.log or DEFAULT_LOG
    base_url = os.environ.get("MYBOT_URL", "https://murderbot.vipulnsward.com")
    try:
        if args.interval is None:
            return 0 if send_once(log_path, base_url) else 1
        while True:
            send_once(log_path, base_url)
            time.sleep(args.interval)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
