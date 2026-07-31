import asyncio
import json
import os
import secrets
import signal
import subprocess
import tempfile
import time
from copy import deepcopy
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

import cv2
import numpy as np
import psycopg2
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from pydantic import BaseModel, Field
from psycopg2.errors import UniqueViolation

BASE_DIR = Path(__file__).resolve().parent
DB_DSN = os.environ.get("DB_DSN", "dbname=murderbot host=localhost")
COOKIE_NAME = "neo_session"
SESSION_MAX_AGE = 7 * 24 * 60 * 60
DEVICE = os.environ.get("ADB_TARGET", "127.0.0.1:5555")
BOT_SCRIPT = Path(os.environ.get("BOT_SCRIPT",
    "/private/tmp/claude-501/-Users-sward-work-scratch/"
    "c2e71639-9f51-4ec5-b5ef-685684771afc/scratchpad/video_report_loop.sh"))
BOT_PIDFILE = Path(os.environ.get("BOT_PIDFILE", "/tmp/video_report_loop.pid"))
BOT_CONFIG_PATH = Path(os.environ.get("BOT_CONFIG_PATH", "/Users/sward/work/scratch/evony-bot/bot_config.json"))
BOT_STATUS_PATH = Path(os.environ.get("BOT_STATUS_PATH", "/Users/sward/work/scratch/evony-bot/bot_status.json"))
BOT_LOG_PATH = Path(os.environ.get("BOT_LOG_PATH", "/tmp/video_report_loop.log"))
BOT_CONFIG_DEFAULTS = {
    "rally": {"enabled": True, "interval_sec": 60, "max_marches": 6},
    "stamina": {"topup_enabled": True, "threshold": 5000},
    "reports": {
        "scan_enabled": True,
        "interval_sec": 600,
        "record_seconds": 170,
        "keep_videos": 5,
    },
    "dashboard": {"deploy_enabled": True},
    "safety": {
        "never_tap_quit": True,
        "wait_on_disconnect": True,
        "disconnect_wait_sec": 90,
        "gem_resource_safe": True,
    },
    "kickout": {"reclaim_on_disconnect": True, "kickout_wait_sec": 60},
    "advanced": {
        "auto_bubble": False,
        "auto_reinforce": False,
        "auto_help_alliance": False,
    },
}
BOT_CONFIG_DEFAULTS["kickout"]["_note"] = (
    "On disconnect (kicked out), wait kickout_wait_sec then tap Restart "
    "(never Quit) to reclaim. Per-user setting."
)
BOT_CONFIG_DEFAULTS["advanced"]["_note"] = (
    "auto_bubble consumes owned truce items; kept OFF by default (consent-gated)."
)
CONFIG_RANGES = {
    "rally.interval_sec": (10, 3600),
    "rally.max_marches": (1, 6),
    "stamina.threshold": (0, None),
    "reports.interval_sec": (10, 3600),
    "reports.record_seconds": (1, 3600),
    "reports.keep_videos": (0, 100),
    "safety.disconnect_wait_sec": (0, 3600),
    "kickout.kickout_wait_sec": (0, None),
}
RECOMMENDED_GENERALS = {
    "wall": [
        "Zhou Yu",
        "Takenaka Shigeharu",
        "Stephen II",
        "Leo III",
        "Niccolo Piccinino",
    ],
    "debuff_mayor": [
        "Cimon",
        "Gilgamesh",
        "Jan Karol Chodkiewicz",
        "Zizka",
        "Baldwin IV",
        "Flavius Aetius",
    ],
}


def persisted_secret(env_name: str, filename: str, factory) -> bytes:
    if value := os.environ.get(env_name):
        return value.encode()
    path = BASE_DIR / filename
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "wb") as file:
            file.write(factory())
    os.chmod(path, 0o600)
    return path.read_bytes().strip()


signer = TimestampSigner(
    persisted_secret("NEO_SECRET", ".secret", lambda: secrets.token_urlsafe(48).encode()),
    salt="neo-session",
)
fernet = Fernet(persisted_secret("EVONY_ENC_KEY", ".enc_key", Fernet.generate_key))
password_hasher = PasswordHasher()
app = FastAPI(title="Murder Bot")

# CORS so the Cloudflare-Pages React SPA (a different origin) can call this API.
# Allows localhost dev, *.pages.dev previews, and murderbot.gg. Credentialed
# auth across origins additionally needs HTTPS + SameSite=None cookies (once the
# domain is on HTTPS); the public /api/demo-counter works cross-origin today.
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=os.environ.get(
        "CORS_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://[a-z0-9-]+\.pages\.dev|https://(www\.)?murderbot\.gg",
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def database():
    connection = psycopg2.connect(DB_DSN)
    try:
        yield connection
    finally:
        connection.close()


def _apply_full_schema_if_empty() -> None:
    """Apply the full schema dump on a brand-new Postgres (e.g. a fresh Render
    instance) so every page's tables exist. Idempotent: only runs when a core
    table (enemies) is missing, so it never touches an already-populated DB."""
    schema_path = Path(__file__).with_name("schema.sql")
    if not schema_path.exists():
        return
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.enemies')")
            if cursor.fetchone()[0] is not None:
                return
            cursor.execute(schema_path.read_text())
        connection.commit()


def initialize_database() -> None:
    _apply_full_schema_if_empty()
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id serial PRIMARY KEY,
                    email text UNIQUE NOT NULL,
                    pw_hash text NOT NULL,
                    created_at timestamptz DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evony_accounts (
                    id serial PRIMARY KEY,
                    user_id int REFERENCES app_users(id) ON DELETE CASCADE,
                    label text,
                    enc_username text NOT NULL,
                    enc_password text NOT NULL,
                    created_at timestamptz DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'generals'
                          AND column_name = 'troop_type'
                    ) AND NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'generals'
                          AND column_name = 'gen_type'
                    ) THEN
                        ALTER TABLE generals RENAME TO combat_generals;
                    END IF;
                END
                $$;
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS generals (
                    id serial PRIMARY KEY,
                    name text UNIQUE,
                    gen_type text,
                    level int,
                    stars int,
                    role text,
                    owned bool DEFAULT true,
                    updated_at timestamptz DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS generals_name_lower_idx
                ON generals (lower(name))
                """
            )
        connection.commit()


# Retry init for ~60s: on a fresh deploy Postgres may not accept connections the
# instant the manager imports (even with depends_on), which previously left the
# schema uncreated. Retry so the schema self-applies without any manual step.
for _attempt in range(30):
    try:
        initialize_database()
        break
    except Exception as _db_exc:  # noqa: BLE001
        if _attempt >= 29:
            print(f"[startup] initialize_database gave up after retries: {_db_exc}", flush=True)
        else:
            time.sleep(2)


class AuthInput(BaseModel):
    email: Annotated[
        str,
        Field(
            min_length=3,
            max_length=320,
            pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        ),
    ]
    password: Annotated[str, Field(min_length=8, max_length=1024)]


class AccountInput(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=100)]
    gmail_username: Annotated[str, Field(min_length=1, max_length=320)]
    gmail_password: Annotated[str, Field(min_length=1, max_length=1024)]


class GeneralInput(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    gen_type: Literal["ground", "ranged", "mounted", "siege", "other"]
    level: Annotated[int | None, Field(ge=1, le=45)] = None
    stars: Annotated[int | None, Field(ge=0, le=5)] = None
    role: Annotated[str | None, Field(max_length=100)] = None
    owned: bool = True


def enc(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def dec(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()


def masked(value: str) -> str:
    return value[:2] + "***"


def session_user_id(request: Request) -> int | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return int(signer.unsign(token, max_age=SESSION_MAX_AGE).decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None


def current_user(request: Request) -> int:
    user_id = session_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM app_users WHERE id = %s", (user_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def set_session(response: JSONResponse, user_id: int) -> None:
    response.set_cookie(
        COOKIE_NAME,
        signer.sign(str(user_id)).decode(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


import time as _time  # noqa: E402
from collections import defaultdict, deque  # noqa: E402

_RATE_HITS: dict = defaultdict(deque)


def _rate_limit(request: Request, bucket: str, limit: int = 12, window: int = 60):
    """In-memory per-IP sliding-window limiter — brute-force protection on public endpoints."""
    ip = request.client.host if request and request.client else "?"
    key = f"{bucket}:{ip}"
    now = _time.time()
    dq = _RATE_HITS[key]
    while dq and dq[0] < now - window:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(status_code=429, detail="Too many attempts — slow down and try again shortly.")
    dq.append(now)


@app.post("/api/signup", status_code=201)
def signup(body: AuthInput, request: Request):
    _rate_limit(request, "signup", limit=6, window=60)
    email = body.email.strip().lower()
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO app_users (email, pw_hash) VALUES (%s, %s) RETURNING id",
                    (email, password_hasher.hash(body.password)),
                )
                user_id = cursor.fetchone()[0]
            connection.commit()
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="Email already registered")
    response = JSONResponse({"id": user_id, "email": email}, status_code=201)
    set_session(response, user_id)
    return response


@app.post("/api/login")
def login(body: AuthInput, request: Request):
    _rate_limit(request, "login", limit=10, window=60)
    email = body.email.strip().lower()
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, pw_hash FROM app_users WHERE email = %s",
                (email,),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    try:
        password_hasher.verify(row[1], body.password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    response = JSONResponse({"id": row[0], "email": email})
    set_session(response, row[0])
    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
    return response


@app.post("/api/evony-accounts", status_code=201)
def create_account(body: AccountInput, user_id: int = Depends(current_user)):
    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Label cannot be blank")
    # These are the user's real Evony/Gmail credentials, encrypted at rest, and must never be printed or logged in plaintext.
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evony_accounts
                    (user_id, label, enc_username, enc_password)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    label,
                    enc(body.gmail_username),
                    enc(body.gmail_password),
                ),
            )
            account_id = cursor.fetchone()[0]
        connection.commit()
    return {
        "id": account_id,
        "label": label,
        "username_masked": masked(body.gmail_username),
    }


@app.get("/api/evony-accounts")
def list_accounts(user_id: int = Depends(current_user)):
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, label, enc_username
                FROM evony_accounts
                WHERE user_id = %s
                ORDER BY id
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
    return [
        {"id": row[0], "label": row[1], "username_masked": masked(dec(row[2]))}
        for row in rows
    ]


def pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def bot_status() -> dict:
    try:
        pid = int(BOT_PIDFILE.read_text().strip())
    except (FileNotFoundError, OSError, ValueError):
        pid = None
    lines = deque(maxlen=8)
    try:
        with BOT_LOG_PATH.open(errors="replace") as log:
            lines.extend(line.rstrip() for line in log if line.strip())
    except OSError:
        pass
    return {"running": pid_alive(pid), "pid": pid, "last_log": list(lines)}


def validate_config(config: dict, partial: bool = False, prefix: str = "") -> None:
    expected = BOT_CONFIG_DEFAULTS
    if prefix:
        for part in prefix.rstrip(".").split("."):
            expected = expected[part]
    for key, value in config.items():
        if key not in expected:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown config key: {prefix}{key}",
            )
        expected_value = expected[key]
        path = f"{prefix}{key}"
        if isinstance(expected_value, dict):
            if not isinstance(value, dict):
                raise HTTPException(status_code=422, detail=f"{path} must be an object")
            validate_config(value, partial=partial, prefix=f"{path}.")
            continue
        if type(value) is not type(expected_value):
            raise HTTPException(
                status_code=422,
                detail=f"{path} must be {type(expected_value).__name__}",
            )
        if path in CONFIG_RANGES:
            minimum, maximum = CONFIG_RANGES[path]
            if value < minimum or (maximum is not None and value > maximum):
                limit = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
                raise HTTPException(status_code=422, detail=f"{path} must be {limit}")
    if not partial:
        for key in expected:
            if key not in config:
                raise HTTPException(status_code=422, detail=f"Missing config key: {prefix}{key}")


def read_bot_config() -> dict:
    try:
        config = json.loads(BOT_CONFIG_PATH.read_text())
        if not isinstance(config, dict):
            raise ValueError
        validate_config(config)
        return config
    except (OSError, json.JSONDecodeError, ValueError, HTTPException):
        return deepcopy(BOT_CONFIG_DEFAULTS)


def deep_merge(target: dict, update: dict) -> dict:
    for key, value in update.items():
        if isinstance(value, dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def write_bot_config(config: dict) -> None:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=BOT_CONFIG_PATH.parent,
            prefix=f".{BOT_CONFIG_PATH.name}.",
            delete=False,
        ) as file:
            temp_path = Path(file.name)
            json.dump(config, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, BOT_CONFIG_PATH)
    except OSError as error:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not save bot config: {error}")


@app.get("/api/bot/status")
def get_bot_status(_user_id: int = Depends(current_user)):
    status = bot_status()
    try:
        loop_status = json.loads(BOT_STATUS_PATH.read_text())
        if not isinstance(loop_status, dict):
            loop_status = {}
    except (OSError, json.JSONDecodeError):
        loop_status = {}
    pid = loop_status.get("pid", status["pid"])
    alive = pid_alive(pid)
    status.update(
        {
            "pid": pid,
            "alive": alive,
            "pid_alive": alive,
            "state": loop_status.get("state", "offline"),
            "joined_total": loop_status.get("joined_total", 0),
            "errors": loop_status.get("errors", 0),
            "last_rally": loop_status.get("last_rally", ""),
            "reports_last": loop_status.get("reports_last", ""),
        }
    )
    status["running"] = alive
    return status


@app.get("/api/bot/config")
def get_bot_config(_user_id: int = Depends(current_user)):
    return read_bot_config()


@app.post("/api/bot/config")
def update_bot_config(body: dict, _user_id: int = Depends(current_user)):
    validate_config(body, partial=True)
    config = deep_merge(read_bot_config(), body)
    if not config["safety"]["never_tap_quit"] or not config["safety"]["gem_resource_safe"]:
        raise HTTPException(
            status_code=422,
            detail="safety.never_tap_quit and safety.gem_resource_safe are locked on",
        )
    validate_config(config)
    write_bot_config(config)
    return config


@app.get("/api/bot/logs")
def get_bot_logs(n: int = 120, _user_id: int = Depends(current_user)):
    lines = deque(maxlen=max(1, min(n, 500)))
    try:
        with BOT_LOG_PATH.open(errors="replace") as log:
            lines.extend(line.rstrip("\n") for line in log)
    except OSError:
        pass
    return {"lines": list(lines)}


@app.post("/api/bot/stop")
def stop_bot(_user_id: int = Depends(current_user)):
    status = bot_status()
    if status["running"]:
        try:
            os.kill(status["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        BOT_PIDFILE.unlink(missing_ok=True)
    return bot_status()


@app.post("/api/bot/start")
def start_bot(_user_id: int = Depends(current_user)):
    status = bot_status()
    if not status["running"]:
        BOT_PIDFILE.unlink(missing_ok=True)
        with BOT_LOG_PATH.open("ab") as log:
            subprocess.Popen(
                ["bash", str(BOT_SCRIPT)],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        for _ in range(20):
            status = bot_status()
            if status["running"]:
                break
            time.sleep(0.01)
    return status


@app.get("/api/generals")
def list_generals(_user_id: int = Depends(current_user)):
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, gen_type, level, stars, role, owned, updated_at
                FROM generals
                ORDER BY lower(name)
                """
            )
            rows = cursor.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "gen_type": row[2],
            "level": row[3],
            "stars": row[4],
            "role": row[5],
            "owned": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]


@app.post("/api/generals")
def upsert_general(body: GeneralInput, _user_id: int = Depends(current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be blank")
    role = body.role.strip() if body.role else None
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO generals (name, gen_type, level, stars, role, owned)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (lower(name)) DO UPDATE SET
                    name = EXCLUDED.name,
                    gen_type = EXCLUDED.gen_type,
                    level = EXCLUDED.level,
                    stars = EXCLUDED.stars,
                    role = EXCLUDED.role,
                    owned = EXCLUDED.owned,
                    updated_at = now()
                RETURNING id, name, gen_type, level, stars, role, owned, updated_at
                """,
                (name, body.gen_type, body.level, body.stars, role, body.owned),
            )
            row = cursor.fetchone()
        connection.commit()
    return {
        "id": row[0],
        "name": row[1],
        "gen_type": row[2],
        "level": row[3],
        "stars": row[4],
        "role": row[5],
        "owned": row[6],
        "updated_at": row[7],
    }


@app.delete("/api/generals/{general_id}")
def delete_general(general_id: int, _user_id: int = Depends(current_user)):
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM generals WHERE id = %s RETURNING id", (general_id,))
            row = cursor.fetchone()
        connection.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="General not found")
    return {"deleted": row[0]}


@app.get("/api/generals/recommendations")
def general_recommendations(_user_id: int = Depends(current_user)):
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, gen_type, level, stars, role, owned, updated_at
                FROM generals
                WHERE owned
                ORDER BY lower(name)
                """
            )
            rows = cursor.fetchall()
    owned_names = {row[1].casefold() for row in rows if row[1]}
    recommended_names = {
        name.casefold()
        for names in RECOMMENDED_GENERALS.values()
        for name in names
    }
    recommendations = {
        group: [
            {
                "name": name,
                "status": "owned" if name.casefold() in owned_names else "needed",
            }
            for name in names
        ]
        for group, names in RECOMMENDED_GENERALS.items()
    }
    recommendations["extras"] = [
        {
            "id": row[0],
            "name": row[1],
            "gen_type": row[2],
            "level": row[3],
            "stars": row[4],
            "role": row[5],
            "owned": row[6],
            "updated_at": row[7],
        }
        for row in rows
        if row[1].casefold() not in recommended_names
    ]
    return recommendations


def capture_jpeg() -> bytes | None:
    try:
        result = subprocess.run(
            ["adb", "-s", DEVICE, "exec-out", "screencap", "-p"],
            capture_output=True,
            check=True,
            timeout=3,
        )
        image = cv2.imdecode(np.frombuffer(result.stdout, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        height, width = image.shape[:2]
        if width > 720:
            image = cv2.resize(
                image,
                (720, round(height * 720 / width)),
                interpolation=cv2.INTER_AREA,
            )
        success, jpeg = cv2.imencode(
            ".jpg",
            image,
            [cv2.IMWRITE_JPEG_QUALITY, 70],
        )
        return jpeg.tobytes() if success else None
    except (OSError, subprocess.SubprocessError):
        return None


async def live_frames():
    while True:
        frame = await asyncio.to_thread(capture_jpeg)
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                + frame
                + b"\r\n"
            )
        await asyncio.sleep(0.07)


@app.get("/live.mjpeg")
def live_view(user_id: int = Depends(current_user)):
    return StreamingResponse(
        live_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


SHARED_CSS = """
<style>
:root{color-scheme:dark;
  --bg:#0a0806;--card:#16120b;--line:#3a2f1a;--ink:#efe6d2;--mut:#b8a888;--dim:#8a7a5a;
  --red:#c0392b;--gold:#e6c35c;--gold2:#f7dd8f;--grn:#57c08a;
  font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--ink);
  background:radial-gradient(1200px 520px at 14% -8%,rgba(230,195,92,.10),transparent 60%),
    radial-gradient(1000px 480px at 100% 0%,rgba(192,57,43,.14),transparent 55%),#0a0806;background-attachment:fixed;}
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.5;
  background-image:repeating-linear-gradient(115deg,rgba(255,255,255,.013) 0 2px,transparent 2px 8px);}
main{position:relative;z-index:1;width:min(1100px,92vw);margin:0 auto;padding:2.6rem 0}
h1,h2{margin-top:0;font-family:Georgia,"Iowan Old Style",serif;letter-spacing:.005em;
  background:linear-gradient(180deg,var(--gold2),var(--gold) 60%,#b8902f);-webkit-background-clip:text;background-clip:text;
  -webkit-text-fill-color:transparent;color:transparent;text-shadow:0 2px 24px rgba(230,195,92,.16)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}
.card{background:linear-gradient(180deg,rgba(42,33,18,.6),rgba(16,12,7,.9));border:1px solid var(--line);border-radius:14px;padding:1.25rem;
  box-shadow:inset 0 0 0 1px rgba(230,195,92,.07),0 20px 44px -26px rgba(0,0,0,.95);position:relative}
.card::before{content:"";position:absolute;inset:4px;border-radius:11px;border:1px solid rgba(230,195,92,.14);pointer-events:none}
form{display:grid;gap:.8rem;position:relative;z-index:1}
label{display:grid;gap:.35rem;color:var(--mut)}
input,select{width:100%;padding:.7rem;color:var(--ink);background:rgba(8,6,4,.7);border:1px solid rgba(230,195,92,.22);border-radius:8px}
button{width:fit-content;padding:.68rem 1.15rem;color:#fff;border:0;border-radius:9px;cursor:pointer;font-weight:700;
  background:linear-gradient(180deg,#e0553f,#a02a1c);
  box-shadow:0 0 0 1px rgba(255,190,130,.38),0 10px 24px -12px rgba(192,57,43,.7),inset 0 1px 0 rgba(255,255,255,.26);
  text-shadow:0 1px 2px rgba(0,0,0,.4);transition:transform .12s ease}
button:hover{transform:translateY(-1px)}
button.secondary{background:linear-gradient(180deg,#2a2214,#191207);color:var(--gold);box-shadow:0 0 0 1px rgba(230,195,92,.35)}
button.danger{background:linear-gradient(180deg,#c0392b,#7d1f16)}
.error{min-height:1.2rem;color:#ff7d5c}
.viewer{overflow:hidden;text-align:center;background:#050302;border:1px solid var(--line);border-radius:12px}
.viewer img{display:block;max-width:100%;margin:auto}
ul{padding-left:1.2rem}li{margin:.55rem 0}
header{display:flex;align-items:center;justify-content:space-between;gap:1rem;position:relative;z-index:1}
.banner{margin:1rem 0;padding:.75rem 1rem;color:var(--gold);background:rgba(42,33,18,.55);border:1px solid rgba(230,195,92,.3);border-radius:10px}
.status{color:var(--mut)}.status.running{color:var(--grn)}.status.stopped{color:#ff7d5c}
.controls{display:flex;gap:.6rem;margin:1rem 0;flex-wrap:wrap}
pre{min-height:8rem;max-height:16rem;overflow:auto;padding:.8rem;white-space:pre-wrap;background:#050302;border:1px solid var(--line);border-radius:8px;color:var(--mut)}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px}
table{width:100%;border-collapse:collapse}
th,td{padding:.7rem;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
thead th{color:var(--gold);font-size:.82rem;letter-spacing:.04em;text-transform:uppercase}
.general-form{grid-template-columns:repeat(auto-fit,minmax(130px,1fr));align-items:end}
.general-form .wide{grid-column:span 2}
.checkbox{display:flex;align-items:center;gap:.5rem;padding-bottom:.7rem}
.checkbox input{width:auto}
.row-actions{display:flex;gap:.4rem}.row-actions button{padding:.4rem .6rem}
.recommendations{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}
.badge{display:inline-block;margin-left:.4rem;padding:.14rem .5rem;border-radius:999px;font-size:.78rem;font-weight:700}
.badge.owned{color:var(--grn);background:rgba(87,192,138,.14)}
.badge.needed{color:#ff7d5c;background:rgba(192,57,43,.18)}
.badge.unknown{color:var(--gold);background:rgba(230,195,92,.14)}
</style>
"""

AUTH_PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Murder Bot — the Evony bot that thinks | Easy Bot alternative</title>
<meta name="description" content="Murder Bot runs your Evony account 24/7 and out-thinks your enemies with a real battle-sim AI. Everything Easy Bot does — plus AI PvP counters, enemy intel, and attack planning. Free during open beta, no credit card.">
<meta name="keywords" content="evony bot, easy bot alternative, evony automation, evony rally bot, evony pvp counter, evony auto farm, evony bot cheap, best evony bot 2026">
<link rel="canonical" href="https://murderbot.vipulnsward.com/">
<meta property="og:type" content="website">
<meta property="og:title" content="Murder Bot — the Evony bot that thinks">
<meta property="og:description" content="Everything Easy Bot does — plus an AI PvP brain that counters every attacker. Free during open beta, no credit card.">
<meta property="og:url" content="https://murderbot.vipulnsward.com/">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Murder Bot","applicationCategory":"GameApplication","operatingSystem":"Web","description":"AI-powered Evony automation and PvP counter engine. An Easy Bot alternative with a real battle-sim brain.","offers":[{"@type":"Offer","name":"Brain","price":"5","priceCurrency":"USD"},{"@type":"Offer","name":"Auto","price":"9","priceCurrency":"USD"}]}
</script>
<style>
:root{--bg:#0b0c10;--card:#14161e;--line:#23262f;--ink:#e9e7e4;--mut:#9aa0ab;--dim:#6b7280;--red:#e5484d;--red2:#ff6b6f;--gold:#d8a24a;--grn:#3fb27f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:0 22px}
a{color:var(--red2);text-decoration:none}
h1,h2,h3{line-height:1.12;letter-spacing:-.02em;margin:0;text-wrap:balance}
.num{font-variant-numeric:tabular-nums}
header{padding:70px 0 46px;background:radial-gradient(1100px 420px at 12% -10%,rgba(229,72,77,.16),transparent 60%),radial-gradient(900px 360px at 100% 0%,rgba(216,162,74,.10),transparent 55%);border-bottom:1px solid var(--line)}
.pill{display:inline-flex;gap:8px;align-items:center;font-size:12.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:6px 12px;background:var(--card)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--grn);box-shadow:0 0 0 3px rgba(63,178,127,.18)}
h1{font-size:clamp(34px,6vw,56px);font-weight:800;margin:20px 0 14px}
h1 .r{color:var(--red)}
.lede{font-size:clamp(17px,2.4vw,21px);color:var(--mut);max-width:60ch}
.cta{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}
.btn{display:inline-block;padding:13px 22px;border-radius:12px;font-weight:700;border:1px solid var(--line)}
.btn.p{background:var(--red);color:#fff;border-color:var(--red)}
.btn.s{background:var(--card);color:var(--ink)}
section{padding:46px 0;border-bottom:1px solid var(--line)}
.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--red2);font-weight:700}
h2{font-size:clamp(22px,3.2vw,30px);font-weight:800;margin:6px 0 20px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
@media(max-width:760px){.grid3{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}
.card .ic{font-size:22px;display:block;margin-bottom:10px}
.card h3{font-size:16px;font-weight:750;margin-bottom:6px}
.card p{color:var(--mut);font-size:14.5px;margin:0}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:16px;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th,td{padding:12px 16px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
thead th{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim);font-weight:700}
tbody tr:last-child td{border-bottom:0}
td.c,th.c{text-align:center}
.yes{color:var(--grn);font-weight:700}.no{color:var(--dim)}.us{color:var(--red2);font-weight:750}
.price{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:760px){.price{grid-template-columns:1fr}}
.tier{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px}
.tier.hot{border-color:rgba(229,72,77,.5);box-shadow:0 0 0 1px rgba(229,72,77,.25)}
.tier .t{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut)}
.tier .p{font-size:30px;font-weight:800;margin:4px 0}.tier .p small{font-size:13px;color:var(--dim);font-weight:600}
.tier ul{margin:10px 0 0;padding:0;list-style:none;font-size:13px;color:var(--mut)}
.tier li{padding:4px 0 4px 18px;position:relative}.tier li:before{content:"▸";position:absolute;left:0;color:var(--red)}
.auth{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:640px}
@media(max-width:620px){.auth{grid-template-columns:1fr}}
form{display:flex;flex-direction:column;gap:10px}
label{display:flex;flex-direction:column;gap:5px;font-size:13px;color:var(--mut)}
input{padding:11px 12px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:15px}
button{padding:12px;border-radius:10px;border:0;background:var(--red);color:#fff;font-weight:700;font-size:15px;cursor:pointer}
.card h2{font-size:17px;margin-bottom:12px}
.error{color:var(--red2);min-height:20px}
footer{padding:32px 0 60px;color:var(--dim);font-size:13px}
.demo{margin-top:4px}
.drow{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end}
.drow label{flex:1;min-width:130px}
.drow input,.drow select{width:100%;padding:11px 12px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:15px}
.drow button{white-space:nowrap;padding:12px 22px;border:0;border-radius:10px;background:var(--red);color:#fff;font-weight:700;font-size:15px;cursor:pointer}
.dout{margin-top:16px;padding:16px;border:1px solid var(--line);border-radius:12px;background:var(--bg);color:var(--mut);font-size:14.5px;min-height:48px}
.dout .act{font-size:20px;font-weight:800;color:var(--red2);text-transform:uppercase;letter-spacing:.02em}
.dout .conf{color:var(--gold);font-weight:700}
</style>
<style>
/* ===== EVONY WAR-ROOM — epic gaming theme (layered override) ===== */
:root{
  --bg:#0a0806;--card:#16120b;--line:#3a2f1a;--ink:#efe6d2;--mut:#b8a888;--dim:#8a7a5a;
  --red:#c0392b;--red2:#ff7d5c;--gold:#e6c35c;--gold2:#f7dd8f;--grn:#57c08a;
}
body{
  background:
    radial-gradient(1200px 520px at 14% -8%, rgba(230,195,92,.11), transparent 60%),
    radial-gradient(1000px 480px at 100% 0%, rgba(192,57,43,.16), transparent 55%),
    radial-gradient(1000px 800px at 50% 118%, rgba(230,195,92,.06), transparent 60%),
    #0a0806;
  background-attachment:fixed;
}
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.55;
  background-image:repeating-linear-gradient(115deg,rgba(255,255,255,.014) 0 2px,transparent 2px 8px);}
.wrap{position:relative;z-index:1}
h1,h2{font-family:Georgia,"Iowan Old Style","Times New Roman",serif!important;letter-spacing:.005em}
h1{background:linear-gradient(180deg,var(--gold2),var(--gold) 55%,#b8902f);-webkit-background-clip:text;background-clip:text;
  -webkit-text-fill-color:transparent;color:transparent;text-shadow:0 2px 34px rgba(230,195,92,.22);filter:drop-shadow(0 1px 0 rgba(0,0,0,.65))}
h1 .r{-webkit-text-fill-color:var(--red2);color:var(--red2)}
h2{color:var(--gold2)}
.eyebrow{color:var(--gold)}
header{background:
  radial-gradient(1100px 480px at 12% -12%,rgba(230,195,92,.15),transparent 60%),
  radial-gradient(900px 400px at 100% -4%,rgba(192,57,43,.20),transparent 55%)!important;
  border-bottom:1px solid rgba(230,195,92,.22)!important;text-align:center}
header .cta{justify-content:center}
.pill{border-color:rgba(230,195,92,.32);color:var(--gold);background:rgba(22,18,11,.8)}
.dot{background:var(--gold)!important;box-shadow:0 0 0 3px rgba(230,195,92,.20)!important;animation:pulse 2.6s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:.8}50%{opacity:1}}
.card,.tier,.tw,.demo{border:1px solid var(--line)!important;
  background:linear-gradient(180deg,rgba(42,33,18,.62),rgba(16,12,7,.9))!important;
  box-shadow:inset 0 0 0 1px rgba(230,195,92,.07),0 20px 44px -24px rgba(0,0,0,.95)!important;position:relative}
.card::before{content:"";position:absolute;inset:4px;border-radius:12px;border:1px solid rgba(230,195,92,.16);pointer-events:none}
.card .ic{filter:drop-shadow(0 2px 10px rgba(230,195,92,.35))}
.card h3{color:var(--gold2)}
thead th{color:var(--gold)}
.yes{color:var(--grn)!important}.us{color:var(--gold2)!important}
.btn.p,button,.tier button{background:linear-gradient(180deg,#e0553f,#a02a1c)!important;color:#fff!important;
  box-shadow:0 0 0 1px rgba(255,190,130,.4),0 10px 26px -12px rgba(192,57,43,.75),inset 0 1px 0 rgba(255,255,255,.28)!important;
  text-shadow:0 1px 2px rgba(0,0,0,.45);transition:transform .12s ease,box-shadow .12s ease}
.btn.p:hover,button:hover{transform:translateY(-1px);box-shadow:0 0 0 1px rgba(255,205,150,.6),0 14px 30px -12px rgba(192,57,43,.9),inset 0 1px 0 rgba(255,255,255,.35)!important}
.btn.s{border-color:rgba(230,195,92,.42)!important;color:var(--gold)!important;background:rgba(22,18,11,.7)!important}
.tier.hot{border-color:rgba(230,195,92,.55)!important;box-shadow:0 0 0 1px rgba(230,195,92,.5),0 0 44px -8px rgba(230,195,92,.3)!important}
.tier .p{color:var(--gold2)}.tier li:before{color:var(--gold)}
.demo{box-shadow:inset 0 0 0 1px rgba(230,195,92,.16),0 0 56px -16px rgba(230,195,92,.3)!important}
.demo::before{display:none}
.dout{background:rgba(8,6,4,.72)!important;border-color:rgba(230,195,92,.22)!important}
.dout .act{color:var(--gold2)!important;text-shadow:0 0 22px rgba(230,195,92,.45)}
.drow input,.drow select,input{background:rgba(8,6,4,.7)!important;border-color:rgba(230,195,92,.22)!important;color:var(--ink)!important}
.crest{width:104px;height:104px;display:block;margin:0 auto 10px;filter:drop-shadow(0 6px 20px rgba(230,195,92,.4))}
footer{border-top:1px solid rgba(230,195,92,.14);color:var(--dim)}
</style>
</head>
<body>
<header><div class="wrap">
  <svg class="crest" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7dd8f"/><stop offset=".55" stop-color="#e6c35c"/><stop offset="1" stop-color="#b8902f"/></linearGradient></defs>
    <g stroke="url(#cg)" stroke-width="4" stroke-linecap="round" opacity=".88"><path d="M26 26 L84 84"/><path d="M94 26 L36 84"/><circle cx="26" cy="26" r="4" fill="url(#cg)"/><circle cx="94" cy="26" r="4" fill="url(#cg)"/></g>
    <path d="M60 16 L98 30 V58 C98 80 80 94 60 102 C40 94 22 80 22 58 V30 Z" fill="#140f08" stroke="url(#cg)" stroke-width="4"/>
    <path d="M60 34 C52 42 52 54 60 62 C68 54 68 42 60 34 Z" fill="url(#cg)"/>
    <path d="M48 68 Q60 80 72 68 Q60 74 48 68 Z" fill="url(#cg)"/>
  </svg>
  <span class="pill"><span class="dot"></span> Live &middot; free beta &middot; built for NFG</span>
  <h1>The Evony bot that <span class="r">thinks.</span></h1>
  <p class="lede">Everything Easy Bot does &mdash; auto-rally, farm, reports &mdash; <b>cheaper</b>, plus a real battle-sim AI that tells you exactly how to counter every attacker. Automate your account <em>and</em> out-think your enemies.</p>
  <div class="cta">
    <a class="btn p" href="#start">Start free &rarr;</a>
    <a class="btn s" href="#demo">See the brain counter an attack</a>
  </div>
  <p style="margin-top:12px;font-size:.9rem;opacity:.72">Free during beta &middot; no credit card &middot; cancel anytime</p>
</div></header>

<section><div class="wrap">
  <span class="eyebrow">Why switch</span>
  <h2>Automation, plus an intelligence Easy&nbsp;Bot doesn't have</h2>
  <div class="grid3">
    <div class="card"><span class="ic">&#9876;&#65039;</span><h3>Full automation</h3><p>Joins rallies every minute, tops stamina, farms, scans battle reports, auto-reclaims after a kickout. Runs 24/7. The parity you expect.</p></div>
    <div class="card"><span class="ic">&#129504;</span><h3>AI PvP brain</h3><p>Paste an incoming attack or an enemy &mdash; a real battle simulator + learned meta says <b>defend / rally / ghost / bubble</b> and the exact lead. Easy Bot has nothing like it.</p></div>
    <div class="card"><span class="ic">&#128225;</span><h3>Enemy intel + attack planner</h3><p>A live database on every player &mdash; troops, buffs, generals, W/L &mdash; and a planner that ranks favorable trades. Learns the meta nightly.</p></div>
  </div>
</div></section>

<section id="demo"><div class="wrap">
  <span class="eyebrow">Live demo &middot; no signup</span>
  <h2>Watch the brain counter an attack</h2>
  <p class="lede" style="margin-bottom:20px">Set an incoming rally, hit counter. This is the exact battle-sim AI that runs on your account &mdash; the thing Easy&nbsp;Bot can't do.</p>
  <div class="card demo">
    <div class="drow">
      <label>Incoming power (M)<input id="d-power" type="number" value="60" min="1" max="5000"></label>
      <label>Their lead<select id="d-lead"><option>SIEGE</option><option>GROUND</option><option>RANGED</option><option>MOUNTED</option></select></label>
      <button id="d-go" type="button">Counter it &rarr;</button>
    </div>
    <div id="d-out" class="dout">Set an attack and hit <b>Counter&nbsp;it</b>.</div>
  </div>
</div></section>

<section><div class="wrap">
  <span class="eyebrow">Murder Bot vs Easy Bot</span>
  <h2>Same automation. Lower price. A brain.</h2>
  <div class="tw"><table>
    <thead><tr><th>Feature</th><th class="c">Easy Bot</th><th class="c">Murder Bot</th></tr></thead>
    <tbody>
      <tr><td>Price / user / mo</td><td class="c num">$8</td><td class="c us num">from $5</td></tr>
      <tr><td>Auto rally-join, farm, stamina</td><td class="c yes">&check;</td><td class="c yes">&check;</td></tr>
      <tr><td>Battle-report parsing</td><td class="c yes">&check;</td><td class="c yes">&check;</td></tr>
      <tr><td>AI counter engine (sim-backed)</td><td class="c no">&mdash;</td><td class="c yes">&check;</td></tr>
      <tr><td>Enemy intel database</td><td class="c no">&mdash;</td><td class="c yes">&check;</td></tr>
      <tr><td>Attack / favorable-trade planner</td><td class="c no">&mdash;</td><td class="c yes">&check;</td></tr>
      <tr><td>Learns the meta 24/7</td><td class="c no">&mdash;</td><td class="c yes">&check;</td></tr>
    </tbody>
  </table></div>
</div></section>

<section><div class="wrap">
  <span class="eyebrow">Pricing &middot; open beta</span>
  <h2>Free right now &mdash; every tier, no card</h2>
  <p class="lede" style="margin-bottom:22px">We're in open beta: <b>everything below is free</b> while we onboard alliances. The monthly prices are what they'll cost later &mdash; sign up now and lock in free access.</p>
  <div class="price">
    <div class="tier hot"><div class="t" style="color:var(--red2)">Brain</div><div class="p"><span style="color:#3fb950">Free</span> <small><s style="opacity:.55">then $5/mo</s></small></div><ul><li>Unlimited AI counters</li><li>Enemy intel</li><li>Attack planner</li><li>No setup &mdash; works instantly</li></ul></div>
    <div class="tier"><div class="t">Auto</div><div class="p"><span style="color:#3fb950">Free</span> <small><s style="opacity:.55">then $9/mo</s></small></div><ul><li>Everything in Brain</li><li>24/7 account automation</li><li>Rally + farm + reports</li></ul></div>
    <div class="tier"><div class="t">Alliance</div><div class="p"><span style="color:#3fb950">Free</span> <small><s style="opacity:.55">then $29/mo</s></small></div><ul><li>Up to 5 accounts</li><li>Fleet dashboard</li><li>Intel on everyone</li></ul></div>
  </div>
  <p style="text-align:center;margin-top:18px"><a class="btn p" href="#start">Claim your free access &rarr;</a></p>
</div></section>

<section id="start"><div class="wrap">
  <span class="eyebrow">Switching from Easy Bot?</span>
  <h2>Migrate in under a minute</h2>
  <p class="lede" style="margin-bottom:22px">Create an account, connect your Evony login, and Murder Bot takes it from there. No downtime, no lock-in.</p>
  <div class="auth">
    <section class="card"><h2>Create account</h2>
      <form id="signup">
        <label>Email<input name="email" type="email" autocomplete="email" required></label>
        <label>Password<input name="password" type="password" autocomplete="new-password" minlength="8" required></label>
        <button>Start free &rarr;</button>
      </form>
    </section>
    <section class="card"><h2>Log in</h2>
      <form id="login">
        <label>Email<input name="email" type="email" autocomplete="email" required></label>
        <label>Password<input name="password" type="password" autocomplete="current-password" minlength="8" required></label>
        <button>Log in</button>
      </form>
    </section>
  </div>
  <p id="message" class="error"></p>
</div></section>

<footer><div class="wrap">Murder Bot &middot; the Evony bot that thinks. Everything Easy Bot does, cheaper &mdash; plus a brain. Built for alliances.</div></footer>

<script>
async function authenticate(event, path) {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget));
  const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
  const result = await response.json();
  if (response.ok) location.reload();
  else document.getElementById("message").textContent = result.detail || "Request failed";
}
document.getElementById("login").addEventListener("submit", event => authenticate(event, "/api/login"));
document.getElementById("signup").addEventListener("submit", event => authenticate(event, "/api/signup"));
async function runDemo() {
  const out = document.getElementById("d-out");
  if (!out) return;
  const power = document.getElementById("d-power").value || 60;
  const lead = document.getElementById("d-lead").value || "SIEGE";
  out.textContent = "Running the battle sim…";
  try {
    const r = await fetch("/api/demo-counter?power=" + encodeURIComponent(power) + "&lead=" + encodeURIComponent(lead));
    const p = await r.json();
    const conf = (p.confidence != null) ? Math.round(p.confidence * 100) + "% confidence" : "";
    const lt = p.lead_type ? " · counter-lead " + p.lead_type : "";
    let gens = "";
    if (p.counter_generals && p.counter_generals.length) {
      gens = '<div style="margin-top:12px"><div style="font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;opacity:.7">Field these generals</div>' +
        p.counter_generals.map(g =>
          '<div style="margin-top:5px"><b>' + (g.general || "") + '</b>' +
          '<span style="opacity:.7"> — ' + (g.counter_type || "") +
          (g.tier ? ' · Tier ' + g.tier : "") + '</span></div>'
        ).join("") + '</div>';
    }
    out.innerHTML = '<div class="act">' + (p.action || "—") + lt + '</div>' +
      '<div style="margin-top:8px">' + (p.reasoning || "") + '</div>' +
      '<div style="margin-top:8px" class="conf">' + conf + '</div>' + gens;
  } catch (e) { out.textContent = "Brain unavailable, try again in a moment."; }
}
const dgo = document.getElementById("d-go");
if (dgo) { dgo.addEventListener("click", runDemo); runDemo(); }
</script>
</body>
</html>
"""

DASHBOARD_PAGE = f"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Murder Bot</title>
{SHARED_CSS}
</head>
<body>
<main>
<header><h1>Murder Bot</h1><button id="logout" class="secondary">Log out</button></header>
<section class="card viewer"><img src="/live.mjpeg" alt="Live emulator screen"></section>
<p class="banner">Phase 2: one emulator serves one Evony account, so these controls operate the single shared bot. Per-user bot isolation requires one device per user in Phase 3.</p>
<div class="grid" style="margin-top:1rem">
<section class="card">
<h2>Add Evony account</h2>
<form id="account">
<label>Label<input name="label" maxlength="100" required></label>
<label>Gmail username<input name="gmail_username" autocomplete="username" required></label>
<label>Gmail password<input name="gmail_password" type="password" autocomplete="off" required></label>
<button>Save account</button>
</form>
<p id="message" class="error"></p>
</section>
<section class="card">
<h2>Saved accounts</h2>
<ul id="accounts"></ul>
</section>
</div>
<div class="grid" style="margin-top:1rem">
<section class="card">
<h2>Bot control</h2>
<p id="bot-status" class="status" aria-live="polite">Checking status…</p>
<div class="controls">
<button id="bot-start">Start</button>
<button id="bot-stop" class="secondary">Stop</button>
</div>
<pre id="bot-log">No log output.</pre>
</section>
<section class="card">
<h2>My Generals</h2>
<form id="general-form" class="general-form">
<label class="wide">Name<input name="name" maxlength="100" required></label>
<label>Type<select name="gen_type" required>
<option value="ground">Ground</option>
<option value="ranged">Ranged</option>
<option value="mounted">Mounted</option>
<option value="siege">Siege</option>
<option value="other">Other</option>
</select></label>
<label>Level<input name="level" type="number" min="1" max="45"></label>
<label>Stars<input name="stars" type="number" min="0" max="5"></label>
<label>Role<select name="role">
<option value="">None</option>
<option value="attacker">Attacker</option>
<option value="wall">Wall</option>
<option value="debuff_mayor">Debuff mayor</option>
<option value="duty">Duty</option>
<option value="assistant">Assistant</option>
<option value="other">Other</option>
</select></label>
<label class="checkbox"><input name="owned" type="checkbox" checked> Owned</label>
<button>Save general</button>
</form>
<p id="general-message" class="error"></p>
<p id="roster-empty" class="status" hidden>No owned generals recorded yet.</p>
<div class="table-wrap">
<table id="generals-table">
<thead><tr><th>Name</th><th>Type</th><th>Level</th><th>Stars</th><th>Role</th><th>Actions</th></tr></thead>
<tbody id="generals"></tbody>
</table>
</div>
<h3>Recommendations</h3>
<div class="recommendations">
<div><h3>Wall</h3><ul id="wall"></ul></div>
<div><h3>Debuff mayor</h3><ul id="debuff-mayor"></ul></div>
<div><h3>Owned extras</h3><ul id="extras"></ul></div>
</div>
</section>
</div>
</main>
<script>
async function loadAccounts() {{
  const response = await fetch("/api/evony-accounts");
  if (!response.ok) return;
  const accounts = await response.json();
  const list = document.getElementById("accounts");
  list.replaceChildren();
  for (const account of accounts) {{
    const item = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = account.label;
    item.append(label, document.createTextNode(" — " + account.username_masked));
    list.append(item);
  }}
}}
async function loadBotStatus() {{
  const response = await fetch("/api/bot/status");
  if (!response.ok) return;
  const status = await response.json();
  const line = document.getElementById("bot-status");
  line.textContent = status.running ? "Running (PID " + status.pid + ")" : "Stopped";
  line.className = "status " + (status.running ? "running" : "stopped");
  document.getElementById("bot-start").disabled = status.running;
  document.getElementById("bot-stop").disabled = !status.running;
  document.getElementById("bot-log").textContent = status.last_log.join("\\n") || "No log output.";
}}
async function controlBot(action) {{
  const response = await fetch("/api/bot/" + action, {{method: "POST"}});
  if (response.ok) await loadBotStatus();
}}
async function loadGenerals() {{
  const [rosterResponse, recommendationResponse] = await Promise.all([
    fetch("/api/generals"),
    fetch("/api/generals/recommendations")
  ]);
  if (!rosterResponse.ok || !recommendationResponse.ok) return;
  const roster = await rosterResponse.json();
  const recommendations = await recommendationResponse.json();
  const ownedRoster = roster.filter(general => general.owned);
  const table = document.getElementById("generals-table");
  const tableBody = document.getElementById("generals");
  tableBody.replaceChildren();
  table.hidden = ownedRoster.length === 0;
  document.getElementById("roster-empty").hidden = ownedRoster.length > 0;
  for (const general of ownedRoster) {{
    const row = document.createElement("tr");
    for (const value of [general.name, general.gen_type, general.level ?? "—", general.stars ?? "—", general.role || "—"]) {{
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }}
    const actions = document.createElement("td");
    actions.className = "row-actions";
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "secondary";
    editButton.textContent = "Edit";
    editButton.addEventListener("click", () => editGeneral(general));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => deleteGeneral(general.id));
    actions.append(editButton, deleteButton);
    row.append(actions);
    tableBody.append(row);
  }}
  for (const [group, target] of [["wall", "wall"], ["debuff_mayor", "debuff-mayor"]]) {{
    const recommendationList = document.getElementById(target);
    recommendationList.replaceChildren();
    for (const general of recommendations[group]) {{
      const item = document.createElement("li");
      const badge = document.createElement("span");
      badge.className = "badge " + general.status;
      badge.textContent = general.status === "owned" ? "✓ owned" : "needed";
      item.append(document.createTextNode(general.name), badge);
      recommendationList.append(item);
    }}
  }}
  const extras = document.getElementById("extras");
  extras.replaceChildren();
  for (const general of recommendations.extras) {{
    const item = document.createElement("li");
    item.textContent = general.name;
    extras.append(item);
  }}
  if (recommendations.extras.length === 0) {{
    const item = document.createElement("li");
    item.className = "status";
    item.textContent = "None";
    extras.append(item);
  }}
}}
function editGeneral(general) {{
  const form = document.getElementById("general-form");
  form.elements.name.value = general.name;
  form.elements.gen_type.value = general.gen_type;
  form.elements.level.value = general.level ?? "";
  form.elements.stars.value = general.stars ?? "";
  form.elements.role.value = general.role || "";
  form.elements.owned.checked = general.owned;
  form.elements.name.focus();
}}
async function deleteGeneral(id) {{
  const response = await fetch("/api/generals/" + id, {{method: "DELETE"}});
  if (response.ok) await loadGenerals();
  else document.getElementById("general-message").textContent = "Delete failed";
}}
document.getElementById("account").addEventListener("submit", async event => {{
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget));
  const response = await fetch("/api/evony-accounts", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(body)
  }});
  const result = await response.json();
  const message = document.getElementById("message");
  if (response.ok) {{
    event.currentTarget.reset();
    message.textContent = "";
    loadAccounts();
  }} else message.textContent = result.detail || "Request failed";
}});
document.getElementById("general-form").addEventListener("submit", async event => {{
  event.preventDefault();
  const form = event.currentTarget;
  const body = {{
    name: form.elements.name.value,
    gen_type: form.elements.gen_type.value,
    level: form.elements.level.value ? Number(form.elements.level.value) : null,
    stars: form.elements.stars.value ? Number(form.elements.stars.value) : null,
    role: form.elements.role.value || null,
    owned: form.elements.owned.checked
  }};
  const response = await fetch("/api/generals", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(body)
  }});
  const result = await response.json();
  const message = document.getElementById("general-message");
  if (response.ok) {{
    form.reset();
    form.elements.owned.checked = true;
    message.textContent = "";
    await loadGenerals();
  }} else message.textContent = typeof result.detail === "string" ? result.detail : "Invalid general";
}});
document.getElementById("logout").addEventListener("click", async () => {{
  await fetch("/api/logout", {{method: "POST"}});
  location.reload();
}});
document.getElementById("bot-start").addEventListener("click", () => controlBot("start"));
document.getElementById("bot-stop").addEventListener("click", () => controlBot("stop"));
loadAccounts();
loadBotStatus();
loadGenerals();
</script>
</body>
</html>
"""

MANAGER_PAGE = (
    """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Murder Bot</title>
"""
    + SHARED_CSS
    + """
<style>
.manager-head a { color: #58a6ff; text-decoration: none; }
.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: .75rem; margin: 1rem 0; }
.metric { padding: 1rem; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }
.metric span { display: block; color: #8b949e; font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; }
.metric strong { display: block; margin-top: .35rem; font-size: 1.15rem; overflow-wrap: anywhere; }
.metric strong.good { color: #3fb950; }
.metric strong.warn { color: #d29922; }
.metric strong.bad { color: #ff7b72; }
.config-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; }
.config-group { margin: 0; padding: 1rem; border: 1px solid #30363d; border-radius: 8px; }
.config-group legend { padding: 0 .35rem; font-weight: 700; }
.config-group label + label { margin-top: .75rem; }
.manager-note { color: #b1bac4; font-size: .9rem; line-height: 1.5; }
#manager-log { height: 18rem; min-height: 18rem; margin-bottom: 0; }
.toast { position: fixed; right: 1rem; bottom: 1rem; z-index: 10; max-width: min(360px, calc(100vw - 2rem)); padding: .8rem 1rem; border-radius: 8px; color: white; background: #238636; box-shadow: 0 8px 28px #0009; }
.toast.error { min-height: 0; background: #b62324; }
button:disabled { cursor: not-allowed; opacity: .5; }
@media (max-width: 560px) {
  main { width: min(94vw, 1100px); padding: 1.25rem 0; }
  .manager-head { align-items: flex-start; }
  .controls { flex-wrap: wrap; }
}
</style>
</head>
<body>
<main>
<header class="manager-head">
  <div><h1>Murder Bot</h1><a href="/">← Dashboard</a></div>
</header>

<section class="status-grid" aria-label="Live bot status">
  <div class="metric"><span>State</span><strong id="manager-state">Loading…</strong></div>
  <div class="metric"><span>Rallies joined</span><strong id="manager-rallies">—</strong></div>
  <div class="metric"><span>Errors</span><strong id="manager-errors">—</strong></div>
  <div class="metric"><span>Last rally</span><strong id="manager-last-rally">—</strong></div>
  <div class="metric"><span>Last report scan</span><strong id="manager-last-report">—</strong></div>
  <div class="metric"><span>PID</span><strong id="manager-pid">—</strong></div>
</section>

<div class="controls">
  <button id="manager-start">Start bot</button>
  <button id="manager-stop" class="danger">Stop bot</button>
</div>

<section class="card viewer">
  <img src="/live.mjpeg" alt="Live emulator screen">
</section>

<section class="card" style="margin-top:1rem">
<h2>Bot configuration</h2>
<form id="manager-config">
<div class="config-grid">
  <fieldset class="config-group">
    <legend>Rallies</legend>
    <label class="checkbox"><input type="checkbox" data-path="rally.enabled"> Join rallies</label>
    <label>Interval (seconds)<input type="number" min="10" max="3600" data-path="rally.interval_sec" required></label>
    <label>Maximum marches<input type="number" min="1" max="6" data-path="rally.max_marches" required></label>
  </fieldset>
  <fieldset class="config-group">
    <legend>Stamina & reports</legend>
    <label class="checkbox"><input type="checkbox" data-path="stamina.topup_enabled"> Top up stamina</label>
    <label>Stamina threshold<input type="number" min="0" data-path="stamina.threshold" required></label>
    <label class="checkbox"><input type="checkbox" data-path="reports.scan_enabled"> Scan reports</label>
    <label>Report interval (seconds)<input type="number" min="10" max="3600" data-path="reports.interval_sec" required></label>
  </fieldset>
  <fieldset class="config-group">
    <legend>Recovery & dashboard</legend>
    <label class="checkbox"><input type="checkbox" data-path="kickout.reclaim_on_disconnect"> Reclaim after disconnect</label>
    <label>Kickout wait (seconds)<input type="number" min="0" data-path="kickout.kickout_wait_sec" required></label>
    <label class="checkbox"><input type="checkbox" data-path="dashboard.deploy_enabled"> Deploy dashboard</label>
  </fieldset>
  <fieldset class="config-group">
    <legend>Advanced</legend>
    <label class="checkbox"><input type="checkbox" data-path="advanced.auto_bubble"> Auto Bubble</label>
    <label class="checkbox"><input type="checkbox" data-path="advanced.auto_reinforce"> Auto Reinforce</label>
    <label class="checkbox"><input type="checkbox" data-path="advanced.auto_help_alliance"> Auto Help Alliance</label>
  </fieldset>
</div>
<p class="manager-note">Safety is locked on: the bot never taps Quit and remains gem/resource-safe. Auto Bubble can spend owned truce items.</p>
<button>Save configuration</button>
</form>
</section>

<section class="card" style="margin-top:1rem">
  <h2>Live logs</h2>
  <pre id="manager-log" aria-live="polite">Loading logs…</pre>
</section>
</main>
<div id="manager-toast" class="toast" role="status" hidden></div>
<script>
let loadedConfig;
const configForm = document.getElementById("manager-config");
const configInputs = [...configForm.querySelectorAll("[data-path]")];

function atPath(object, path) {
  return path.split(".").reduce((value, key) => value[key], object);
}

function putPath(object, path, value) {
  const [group, key] = path.split(".");
  (object[group] ||= {})[key] = value;
}

function toast(message, error = false) {
  const element = document.getElementById("manager-toast");
  element.textContent = message;
  element.className = "toast" + (error ? " error" : "");
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.hidden = true, 3500);
}

async function loadConfig() {
  const response = await fetch("/api/bot/config");
  if (!response.ok) return toast("Could not load configuration", true);
  loadedConfig = await response.json();
  for (const input of configInputs) {
    const value = atPath(loadedConfig, input.dataset.path);
    if (input.type === "checkbox") input.checked = value;
    else input.value = value;
  }
}

configForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (!loadedConfig) return toast("Configuration is still loading", true);
  const changes = {};
  for (const input of configInputs) {
    const value = input.type === "checkbox" ? input.checked : Number(input.value);
    if (value !== atPath(loadedConfig, input.dataset.path)) {
      putPath(changes, input.dataset.path, value);
    }
  }
  if (!Object.keys(changes).length) return toast("No changes to save");
  const response = await fetch("/api/bot/config", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(changes)
  });
  const result = await response.json();
  if (!response.ok) return toast(
    typeof result.detail === "string" ? result.detail : "Invalid configuration",
    true
  );
  loadedConfig = result;
  toast("Configuration saved");
});

async function loadStatus() {
  const response = await fetch("/api/bot/status");
  if (!response.ok) return;
  const status = await response.json();
  const state = status.alive ? status.state : "offline";
  const stateElement = document.getElementById("manager-state");
  stateElement.textContent = state;
  stateElement.className = state === "running"
    ? "good"
    : ["waiting", "kicked-out", "reclaiming"].includes(state) ? "warn" : "bad";
  document.getElementById("manager-rallies").textContent = status.joined_total ?? 0;
  document.getElementById("manager-errors").textContent = status.errors ?? 0;
  document.getElementById("manager-last-rally").textContent = status.last_rally || "Never";
  document.getElementById("manager-last-report").textContent = status.reports_last || "Never";
  document.getElementById("manager-pid").textContent = status.pid ?? "—";
  document.getElementById("manager-start").disabled = status.alive;
  document.getElementById("manager-stop").disabled = !status.alive;
}

async function controlBot(action) {
  const response = await fetch("/api/bot/" + action, {method: "POST"});
  if (!response.ok) return toast("Could not " + action + " bot", true);
  toast(action === "start" ? "Bot started" : "Bot stopped");
  await loadStatus();
}

async function loadLogs() {
  const response = await fetch("/api/bot/logs?n=120");
  if (!response.ok) return;
  const result = await response.json();
  const log = document.getElementById("manager-log");
  log.textContent = result.lines.join("\\n") || "No log output.";
  log.scrollTop = log.scrollHeight;
}

document.getElementById("manager-start").addEventListener("click", () => controlBot("start"));
document.getElementById("manager-stop").addEventListener("click", () => controlBot("stop"));
loadConfig();
loadStatus();
loadLogs();
setInterval(loadStatus, 3000);
setInterval(loadLogs, 5000);
</script>
</body>
</html>
"""
)


@app.get("/manager", response_class=HTMLResponse)
def manager(_user_id: int = Depends(current_user)):
    return MANAGER_PAGE


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user_id = session_user_id(request)
    if user_id is not None:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM app_users WHERE id = %s", (user_id,))
                if cursor.fetchone() is not None:
                    return RedirectResponse("/home", status_code=303)
    return AUTH_PAGE


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return "User-agent: *\nAllow: /\nSitemap: https://murderbot.vipulnsward.com/sitemap.xml\n"


@app.get("/sitemap.xml")
def sitemap_xml():
    urls = ["/", "/demo", *sitemap_paths()]
    body = "".join(f"<url><loc>https://murderbot.vipulnsward.com{u}</loc><changefreq>weekly</changefreq></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(content=xml, media_type="application/xml")


@app.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt_route():
    """AI-crawler manifest so LLM answer engines can find + cite the guide content."""
    import seo_extras  # noqa: E402
    return seo_extras.llms_txt()


@app.get("/7f3c9a1e2b4d6f8091a3c5e7b9d2f406.txt", response_class=PlainTextResponse)
def indexnow_key_route():
    """IndexNow ownership key so Bing/Yandex accept our URL submissions."""
    return "7f3c9a1e2b4d6f8091a3c5e7b9d2f406"


@app.get("/api/demo-counter")
def demo_counter(request: Request, power: float = 60, lead: str = "SIEGE",
                 kind: str = "auto", mode: str = "open_map"):
    """PUBLIC, no-auth AI counter demo for the landing page (the sales wedge).
    Uses the doctrine baked into the manager image; rate-limited per IP."""
    _rate_limit(request, "demo", 40, 60)
    lead = (lead or "SIEGE").upper()
    if lead not in ("SIEGE", "GROUND", "RANGED", "MOUNTED"):
        lead = "SIEGE"
    try:
        power = max(1.0, min(float(power), 5000.0))
    except (TypeError, ValueError):
        power = 60.0
    # A manageable hit (< ~120M) is a solo you counter-lead; bigger is a
    # coordinated rally you bubble to deny the kill. Lets the demo show BOTH.
    if kind == "auto":
        kind = "rally" if power >= 120 else "solo"
    elif kind not in ("rally", "solo", "scout"):
        kind = "solo"
    try:
        import sys as _sys
        import os as _os
        _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        import counter_ai  # noqa: E402
        plan = counter_ai.decide({
            "mode": mode,
            "incoming": {"kind": kind, "lead_type": lead, "total_millions": power},
        })
        try:
            from counter_general import recommend_counters  # noqa: E402
            cg = recommend_counters(lead, top=3).get("recommendations", [])
        except Exception:
            cg = []
        return {
            "action": plan.get("action"),
            "lead_type": plan.get("lead_type"),
            "reasoning": plan.get("reasoning"),
            "confidence": plan.get("confidence"),
            "expected_loss_pct": plan.get("expected_loss_pct"),
            "sim_used": plan.get("sim_used"),
            "counter_generals": [
                {"general": p.get("general"), "counter_type": p.get("counter_type"),
                 "tier": p.get("tier"), "why": p.get("why")} for p in cg
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"action": "defend", "lead_type": lead,
             "reasoning": f"Brain warming up ({exc}). Front your counter-lead, keep the anvil garrisoned.",
             "confidence": 0.5}, status_code=200)


@app.get("/api/counter-generals")
def counter_generals_api(request: Request, enemy: str = "ground", role: str = "attack", top: int = 5):
    """PUBLIC alliance intel lookup: given an enemy troop type OR a named general,
    return the best counter generals from the roster — grounded troop-type table
    (Mounted>Ground/Siege, Ranged>Mounted, Siege>Ranged, Ground>Ranged/Siege) plus
    the tiered ratings. Rate-limited per IP."""
    _rate_limit(request, "demo", 40, 60)
    try:
        top = max(1, min(int(top), 8))
    except (TypeError, ValueError):
        top = 5
    role = "defense" if str(role).lower().startswith("def") else "attack"
    try:
        import sys as _sys
        import os as _os
        _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        from counter_general import recommend_counters  # noqa: E402
        return recommend_counters(enemy, role=role, top=top)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"enemy": enemy, "error": str(exc), "recommendations": []},
                            status_code=200)


# Ensure the repo root is importable so view modules can import root modules
# (game_kb, counter_general, ...) at their OWN module-load time, not just at runtime.
import sys as _sys_root  # noqa: E402
import os as _os_root  # noqa: E402
_REPO_ROOT = _os_root.path.dirname(_os_root.path.dirname(_os_root.path.abspath(__file__)))
if _REPO_ROOT not in _sys_root.path:
    _sys_root.path.insert(0, _REPO_ROOT)

# --- Murder Bot feature routers (self-contained modules) ---
from reports_view import router as reports_router  # noqa: E402
from generals_view import build_router as build_generals_router  # noqa: E402
from counter_view import build_router as build_counter_router  # noqa: E402
from map_view import build_router as build_map_router  # noqa: E402
from billing_view import build_router as build_billing_router  # noqa: E402

from intel_view import build_router as build_intel_router  # noqa: E402
from attack_view import build_router as build_attack_router  # noqa: E402
from brain_view import build_router as build_brain_router  # noqa: E402
from settings_view import build_router as build_settings_router  # noqa: E402
from alliance_view import build_router as build_alliance_router  # noqa: E402
from mybot_view import build_router as build_mybot_router  # noqa: E402
from guides_view import build_router as build_guides_router, sitemap_paths, static_files as guide_static_files  # noqa: E402

app.mount("/static/guides", guide_static_files, name="guide-images")
app.include_router(reports_router)                                  # GET /reports, /api/reports[/{rid}]
app.include_router(build_guides_router())                           # PUBLIC: /guides, /generals
app.include_router(build_generals_router(current_user, database))   # GET /generals-gallery, portraits
app.include_router(build_counter_router(current_user, database))    # GET /counter — AI counter engine
app.include_router(build_map_router(current_user, database))        # GET /map — vision-DB world map
app.include_router(build_billing_router(current_user, database))    # GET /billing — subscription tiers
app.include_router(build_intel_router(current_user, database))      # GET /intel — enemy intel on everyone
app.include_router(build_attack_router(current_user, database))     # GET /attack — favorable-trade planner (advisory)
app.include_router(build_brain_router(current_user, database))      # GET /brain — self-evolving knowledge
app.include_router(build_settings_router(current_user, database, fernet))  # GET /settings — accounts + tokens
from hub_view import build_router as build_hub_router  # noqa: E402
app.include_router(build_hub_router(current_user, database))        # GET /home — the nav hub
app.include_router(build_alliance_router(current_user, database))   # GET /alliance — alliance threat board
app.include_router(build_mybot_router(current_user, database))      # GET /mybot — NeoIsTlatoani local-bot data


@app.get("/healthz")
def healthz():
    """Unauthenticated liveness/readiness probe for load balancers + uptime monitoring."""
    db_ok = True
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
    except Exception:
        db_ok = False
    bot_ok = False
    try:
        pid = int(BOT_PIDFILE.read_text().strip())
        os.kill(pid, 0)
        bot_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "down",
            "bot": "running" if bot_ok else "stopped"}
