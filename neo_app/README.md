# Neo Evony Dashboard — Phase 2

## Run

Install the pinned dependencies:

```sh
/Users/sward/work/scratch/evony-bot/.venv/bin/pip install -r /Users/sward/work/scratch/evony-bot/neo_app/requirements.txt
```

Start the app from its directory:

```sh
cd /Users/sward/work/scratch/evony-bot/neo_app
/Users/sward/work/scratch/evony-bot/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8800
```

Open `http://127.0.0.1:8800/`.

Postgres must be running locally with a database named `murderbot`. The app creates the `app_users`, `evony_accounts`, and `generals` tables when it starts. ADB must expose the emulator as `127.0.0.1:5555`.

## Phase 2 bot limitation

One emulator currently serves one Evony account. The bot controls operate that single shared bot for every logged-in dashboard user. True per-user bot isolation requires a separate device per user and is deferred to Phase 3.

## Security model

App passwords are hashed with Argon2 and are never stored in plaintext. Evony/Gmail usernames and passwords are separately encrypted with Fernet before being stored in Postgres. Account APIs return only labels and masked usernames.

Set `NEO_SECRET` and `EVONY_ENC_KEY` in the environment for managed production secrets. Without them, the app generates `.secret` and `.enc_key` locally, reuses them on later starts, and enforces file mode `0600`. Both files are gitignored. Back up `.enc_key` securely: losing it makes stored account credentials unrecoverable.

The signed session cookie is HTTP-only and SameSite=Lax. This Phase 2 server is configured for local HTTP, so deploy it only behind HTTPS and set an appropriate secure-cookie policy before exposing it to a network.

## Warning

**Automating Evony login violates Evony's Terms of Service and can result in an account ban.** Stored credentials remain sensitive even though they are encrypted. Restrict host access, protect secret keys, use dummy credentials for testing, and never log decrypted values.
