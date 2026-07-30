"""Settings page — configure accounts + integration tokens from the UI.

Self-contained FastAPI APIRouter. It does NOT import app.py (no circular
import): the host app injects its own ``current_user`` auth dependency, its
``database`` context manager, and its ``fernet`` object through
``build_router(current_user, database, fernet)``.

What it configures
------------------
* Evony account (label / Gmail username / Gmail password): reuses the host
  app's existing encrypted ``POST /api/evony-accounts`` flow. The settings page
  posts to that endpoint and shows only masked usernames read back from
  ``GET /api/evony-accounts`` — plaintext credentials never leave the server.
* Discord bot token (for the 24/7 hotspot): Fernet-encrypted at rest in a new
  ``integrations`` table (``user_id, kind, enc_value, updated_at``). The token
  is never returned in plaintext; status is reported as ``configured`` plus the
  last four characters only.

Security model
--------------
Everything secret is encrypted with the host app's Fernet key before it touches
Postgres, and no endpoint here ever returns a decrypted secret. The Discord
token is decrypted server-side solely to derive its masked last-four preview.
"""

from __future__ import annotations

from typing import Annotated

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

DISCORD_KIND = "discord_bot_token"


class DiscordTokenInput(BaseModel):
    token: Annotated[str, Field(min_length=1, max_length=500)]


def _mask_username(value: str) -> str:
    return value[:2] + "***"


def _last4(value: str) -> str:
    return value[-4:] if value else ""


def _ensure_integrations_table(database) -> None:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS integrations (
                    id serial PRIMARY KEY,
                    user_id int REFERENCES app_users(id) ON DELETE CASCADE,
                    kind text NOT NULL,
                    enc_value text NOT NULL,
                    updated_at timestamptz DEFAULT now(),
                    UNIQUE (user_id, kind)
                )
                """
            )
        connection.commit()


def _evony_status(database, fernet, user_id: int) -> dict:
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
    accounts = []
    for account_id, label, enc_username in rows:
        try:
            username_masked = _mask_username(fernet.decrypt(enc_username.encode()).decode())
        except InvalidToken:
            username_masked = "??***"
        accounts.append({"id": account_id, "label": label, "username_masked": username_masked})
    return {"configured": bool(accounts), "count": len(accounts), "accounts": accounts}


def _discord_status(database, fernet, user_id: int) -> dict:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT enc_value, updated_at FROM integrations WHERE user_id = %s AND kind = %s",
                (user_id, DISCORD_KIND),
            )
            row = cursor.fetchone()
    if row is None:
        return {"configured": False, "last4": "", "updated_at": None}
    enc_value, updated_at = row
    try:
        last4 = _last4(fernet.decrypt(enc_value.encode()).decode())
    except InvalidToken:
        last4 = ""
    return {
        "configured": True,
        "last4": last4,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


SETTINGS_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Settings — Murder Bot</title>
<style>
:root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }
main { width: min(880px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }
a { color: #58a6ff; text-decoration: none; }
header.top { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .75rem; }
h1 { margin: 0; font-size: 1.7rem; }
h2 { margin-top: 0; }
.card { margin-top: 1.25rem; padding: 1.3rem 1.4rem; background: #161b22; border: 1px solid #30363d; border-radius: 14px; }
form { display: grid; gap: .8rem; margin: 0; }
label { display: grid; gap: .35rem; color: #b1bac4; font-size: .9rem; }
input { width: 100%; padding: .7rem; color: inherit; background: #0d1117; border: 1px solid #484f58; border-radius: 7px; font: inherit; }
button { justify-self: start; padding: .65rem 1.1rem; color: white; background: #238636; border: 0; border-radius: 7px; cursor: pointer; font-weight: 650; }
button:disabled { cursor: not-allowed; opacity: .55; }
.error { min-height: 1.2rem; margin: .4rem 0 0; color: #ff7b72; font-size: .88rem; }
.ok { color: #3fb950; }
.status-line { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem; margin: 0 0 1rem; padding: .6rem .8rem; background: #0d1117; border: 1px solid #30363d; border-radius: 9px; font-size: .9rem; }
.pill { padding: .12rem .55rem; border-radius: 999px; font-size: .74rem; font-weight: 700; letter-spacing: .03em; }
.pill.on { color: #3fb950; background: #12261a; border: 1px solid #1c3d28; }
.pill.off { color: #d29922; background: #2a2109; border: 1px solid #4a3a12; }
code { padding: .1rem .35rem; background: #0d1117; border: 1px solid #30363d; border-radius: 5px; font-size: .82rem; }
.accounts { margin: .3rem 0 1rem; padding-left: 1.1rem; color: #adbac7; font-size: .9rem; }
.accounts li { margin: .3rem 0; }
.accounts strong { color: #e6edf3; }
.hint { margin: .6rem 0 0; padding: .7rem .85rem; color: #8b949e; font-size: .84rem; line-height: 1.5; background: #0d1117; border: 1px solid #21262d; border-left: 3px solid #388bfd; border-radius: 0 8px 8px 0; }
.note { margin-top: 1.6rem; color: #6e7681; font-size: .82rem; line-height: 1.6; }
</style>
</head>
<body>
<main>
<header class="top">
  <div><h1>Settings</h1><a href="/">&larr; Dashboard</a></div>
</header>

<section class="card">
  <h2>Evony account</h2>
  <p class="status-line" id="evony-status"><span class="pill off">not configured</span></p>
  <ul class="accounts" id="evony-accounts" hidden></ul>
  <form id="evony-form">
    <label>Label<input name="label" maxlength="100" placeholder="Main account" required></label>
    <label>Evony / Gmail email<input name="gmail_username" autocomplete="username" placeholder="you@gmail.com" required></label>
    <label>Password<input name="gmail_password" type="password" autocomplete="off" required></label>
    <button>Save Evony account</button>
    <p class="error" id="evony-error"></p>
  </form>
  <p class="hint">Use the email and password you log into Evony with (the linked Google/Gmail
  account). Stored Fernet-encrypted; only a masked username is ever shown back.</p>
</section>

<section class="card">
  <h2>Discord bot token</h2>
  <p class="status-line" id="discord-status"><span class="pill off">not configured</span></p>
  <form id="discord-form">
    <label>Bot token<input name="token" type="password" autocomplete="off" placeholder="Paste the bot token" required></label>
    <button>Save Discord token</button>
    <p class="error" id="discord-error"></p>
  </form>
  <p class="hint">Powers the 24/7 hotspot bot. Get it at
  <a href="https://discord.com/developers/applications" target="_blank" rel="noopener">discord.com/developers/applications</a>
  &rarr; your application &rarr; <strong>Bot</strong> &rarr; <em>Reset Token</em>. The token is stored
  Fernet-encrypted and never displayed again &mdash; only <code>configured</code> and its last 4 characters.</p>
</section>

<p class="note">Secrets are encrypted at rest with the app's Fernet key before touching the
database. No endpoint on this page ever returns a decrypted password or token.</p>
</main>
<script>
function setPill(element, on, onText, offText) {
  element.replaceChildren();
  const pill = document.createElement("span");
  pill.className = "pill " + (on ? "on" : "off");
  pill.textContent = on ? onText : offText;
  element.append(pill);
  return pill;
}

async function loadStatus() {
  const response = await fetch("/api/settings");
  if (!response.ok) return;
  const status = await response.json();

  const evony = status.evony || {};
  const evonyStatus = document.getElementById("evony-status");
  const pill = setPill(evonyStatus, evony.configured, "configured \\u2713", "not configured");
  if (evony.configured) {
    evonyStatus.append(document.createTextNode(" " + evony.count + " account" + (evony.count === 1 ? "" : "s")));
  }
  const list = document.getElementById("evony-accounts");
  list.replaceChildren();
  list.hidden = !(evony.accounts && evony.accounts.length);
  for (const account of evony.accounts || []) {
    const item = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = account.label;
    item.append(label, document.createTextNode(" \\u2014 " + account.username_masked));
    list.append(item);
  }

  const discord = status.discord_token || {};
  const discordStatus = document.getElementById("discord-status");
  setPill(discordStatus, discord.configured, "configured \\u2713", "not configured");
  if (discord.configured && discord.last4) {
    const suffix = document.createElement("span");
    suffix.textContent = "ends in ";
    const code = document.createElement("code");
    code.textContent = discord.last4;
    discordStatus.append(document.createTextNode(" "), suffix, code);
  }
}

document.getElementById("evony-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form));
  const error = document.getElementById("evony-error");
  error.textContent = "";
  const response = await fetch("/api/evony-accounts", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  const result = await response.json().catch(() => ({}));
  if (response.ok) {
    form.reset();
    error.className = "error ok";
    error.textContent = "Saved.";
    await loadStatus();
  } else {
    error.className = "error";
    error.textContent = typeof result.detail === "string" ? result.detail : "Could not save account";
  }
});

document.getElementById("discord-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.getElementById("discord-error");
  error.textContent = "";
  const response = await fetch("/api/settings/discord-token", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({token: form.elements.token.value})
  });
  const result = await response.json().catch(() => ({}));
  if (response.ok) {
    form.reset();
    error.className = "error ok";
    error.textContent = "Saved. Token ends in " + (result.last4 || "");
    await loadStatus();
  } else {
    error.className = "error";
    error.textContent = typeof result.detail === "string" ? result.detail : "Could not save token";
  }
});

loadStatus();
</script>
</body>
</html>
"""


def build_router(current_user, database, fernet) -> APIRouter:
    """Return the settings router wired to the host app's auth, DB, and Fernet.

    Parameters
    ----------
    current_user:
        The host app's FastAPI auth dependency (``request -> user_id``).
    database:
        The host app's ``@contextmanager`` yielding a psycopg2 connection.
    fernet:
        The host app's ``cryptography.fernet.Fernet`` instance used to encrypt
        secrets at rest with the same key as the rest of the app.
    """
    try:
        _ensure_integrations_table(database)
    except Exception as exc:  # noqa: BLE001
        # Don't crash app boot if the DB is unreachable; schema.sql creates this
        # table on first successful connect and requests re-check as needed.
        print(f"[settings_view] integrations-table ensure deferred: {exc}", flush=True)

    router = APIRouter(tags=["settings"])

    @router.get("/settings", response_class=HTMLResponse)
    def settings_page(_user_id: int = Depends(current_user)):
        return HTMLResponse(SETTINGS_PAGE)

    @router.get("/api/settings")
    def settings_status(user_id: int = Depends(current_user)):
        return JSONResponse(
            {
                "evony": _evony_status(database, fernet, user_id),
                "discord_token": _discord_status(database, fernet, user_id),
            }
        )

    @router.post("/api/settings/discord-token")
    def save_discord_token(body: DiscordTokenInput, user_id: int = Depends(current_user)):
        token = body.token.strip()
        if not token:
            raise HTTPException(status_code=422, detail="Token cannot be blank")
        if any(character.isspace() for character in token):
            raise HTTPException(status_code=422, detail="Token cannot contain whitespace")
        if len(token) < 8:
            raise HTTPException(status_code=422, detail="Token looks too short")
        enc_value = fernet.encrypt(token.encode()).decode()
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO integrations (user_id, kind, enc_value, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (user_id, kind) DO UPDATE SET
                        enc_value = EXCLUDED.enc_value,
                        updated_at = now()
                    RETURNING updated_at
                    """,
                    (user_id, DISCORD_KIND, enc_value),
                )
                updated_at = cursor.fetchone()[0]
            connection.commit()
        return {
            "configured": True,
            "last4": _last4(token),
            "updated_at": updated_at.isoformat() if updated_at else None,
        }

    return router
