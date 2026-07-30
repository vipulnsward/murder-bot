"""Subscription billing — Razorpay-backed plans for the Murder Bot manager.

Self-contained FastAPI APIRouter. Like ``generals_view`` it does NOT import
``app.py`` (no circular import): the host app injects its own ``current_user``
auth dependency and ``database`` context manager through ``build_router(...)``.

Safety posture (read before touching payments)
-----------------------------------------------
This module is wired so it can NEVER create a live financial resource by
accident. Two independent guards must both pass before a Razorpay call runs:

1. Real API keys must be present in the environment
   (``RAZORPAY_KEY_ID`` / ``RAZORPAY_KEY_SECRET``). Missing keys → a clear
   "billing not configured" stub is returned and no network call is made.
2. Any key that looks live (``rzp_live_...``) is refused unless the operator
   has *explicitly* opted in with ``BILLING_LIVE=1``. Test keys
   (``rzp_test_...``) hit the Razorpay sandbox only, where "orders" and
   "subscriptions" carry no real money.

The default configuration therefore stays in the sandbox. Ship real plans only
after creating them in the Razorpay dashboard and setting ``BILLING_LIVE=1``.

Data
----
A new ``subscriptions`` table (one row per user) records the active plan,
provider subscription/order id, status and current-period end. It is created
idempotently the first time ``build_router`` runs.
"""

from __future__ import annotations

import base64
import hmac
import html
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

RAZORPAY_API_ROOT = "https://api.razorpay.com/v1"

PLANS: dict[str, dict] = {
    "free": {
        "rank": 0,
        "name": "Free",
        "price_usd": 0,
        "tagline": "View-only. See your roster and public intel.",
        "features": [
            "Generals gallery + owned roster (read-only)",
            "World map viewer",
            "One Evony account linked",
            "No automation, no AI counter, no reports",
        ],
    },
    "pro": {
        "rank": 1,
        "name": "Pro",
        "price_usd": 7,
        "tagline": "The full bot for a single commander.",
        "features": [
            "Everything in Free",
            "Full automation: rally, stamina top-up, kickout reclaim",
            "AI counter engine (matchup recommendations)",
            "Battle-report scanning + parsed history",
            "One Evony account, fully automated",
        ],
    },
    "alliance": {
        "rank": 2,
        "name": "Alliance",
        "price_usd": 29,
        "tagline": "Run the whole R4 desk: many accounts, intel on everyone.",
        "features": [
            "Everything in Pro",
            "Multi-account control (up to 10 linked Evony accounts)",
            "Alliance-wide intel: scout + track every enemy you see",
            "Shared counter/PvP brain across accounts",
            "Priority scan cadence",
        ],
    },
}

PLAN_RANK = {key: plan["rank"] for key, plan in PLANS.items()}
ACTIVE_STATUSES = {"active", "authenticated", "charged", "created"}

DEFAULT_PERIOD_DAYS = 30


class SubscribeInput(BaseModel):
    plan: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _ensure_schema(database) -> None:
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id serial PRIMARY KEY,
                        user_id int UNIQUE REFERENCES app_users(id) ON DELETE CASCADE,
                        plan text NOT NULL DEFAULT 'free',
                        status text NOT NULL DEFAULT 'inactive',
                        provider text DEFAULT 'razorpay',
                        provider_id text,
                        current_period_end timestamptz,
                        created_at timestamptz DEFAULT now(),
                        updated_at timestamptz DEFAULT now()
                    )
                    """
                )
            connection.commit()
    except Exception:
        pass


def subscription_status(database, user_id: int) -> dict:
    """Return the caller's effective plan/status.

    Defaults to the Free plan when the user has no subscription row. A paid row
    whose ``current_period_end`` has passed is reported as ``expired`` so gating
    dependencies treat it as unpaid without needing a separate cron job.
    """
    row = None
    try:
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT plan, status, provider, provider_id, current_period_end
                    FROM subscriptions
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
    except Exception:
        row = None

    if not row:
        return {
            "plan": "free",
            "status": "active",
            "provider": None,
            "provider_id": None,
            "current_period_end": None,
        }

    plan, status, provider, provider_id, period_end = row
    plan = plan if plan in PLANS else "free"
    if (
        plan != "free"
        and period_end is not None
        and period_end < _now()
        and status in ACTIVE_STATUSES
    ):
        status = "expired"
    return {
        "plan": plan,
        "status": status,
        "provider": provider,
        "provider_id": provider_id,
        "current_period_end": _iso(period_end),
    }


def _upsert_subscription(
    database,
    user_id: int,
    plan: str,
    status: str,
    provider_id: str | None,
    current_period_end: datetime | None,
) -> None:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO subscriptions
                    (user_id, plan, status, provider, provider_id, current_period_end, updated_at)
                VALUES (%s, %s, %s, 'razorpay', %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    plan = EXCLUDED.plan,
                    status = EXCLUDED.status,
                    provider = EXCLUDED.provider,
                    provider_id = EXCLUDED.provider_id,
                    current_period_end = EXCLUDED.current_period_end,
                    updated_at = now()
                """,
                (user_id, plan, status, provider_id, current_period_end),
            )
        connection.commit()


def make_require_plan(current_user, database):
    """Build a ``require_plan(min_plan)`` dependency factory bound to this app.

    Usage in app.py once billing is wired::

        billing_router = build_billing_router(current_user, database)
        require_plan = billing_router.require_plan
        ...
        @app.post("/api/bot/start")
        def start_bot(user_id: int = Depends(require_plan("pro"))):
            ...

    A caller below the required tier — or a lapsed subscriber — gets HTTP 402.
    """

    def require_plan(min_plan: str):
        if min_plan not in PLAN_RANK:
            raise ValueError(f"Unknown plan: {min_plan}")
        min_rank = PLAN_RANK[min_plan]

        def dependency(user_id: int = Depends(current_user)) -> int:
            status = subscription_status(database, user_id)
            has_rank = PLAN_RANK.get(status["plan"], 0) >= min_rank
            is_active = min_rank == 0 or status["status"] in ACTIVE_STATUSES
            if not (has_rank and is_active):
                raise HTTPException(
                    status_code=402,
                    detail=f"{PLANS[min_plan]['name']} plan required",
                )
            return user_id

        return dependency

    return require_plan


def _razorpay_keys() -> tuple[str | None, str | None]:
    return os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")


def _live_allowed(key_id: str) -> bool:
    if key_id.startswith("rzp_live_"):
        return os.environ.get("BILLING_LIVE") == "1"
    return True


def _razorpay_api(
    method: str, path: str, key_id: str, key_secret: str, body: dict | None = None
) -> dict:
    url = f"{RAZORPAY_API_ROOT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        try:
            message = json.loads(detail).get("error", {}).get("description", detail)
        except Exception:
            message = detail
        raise HTTPException(status_code=502, detail=f"Razorpay error: {message}")
    except urllib.error.URLError as error:
        raise HTTPException(status_code=502, detail=f"Razorpay unreachable: {error.reason}")


def _create_razorpay_resource(plan_key: str, user_id: int) -> dict:
    key_id, key_secret = _razorpay_keys()
    if not key_id or not key_secret:
        return {
            "configured": False,
            "message": (
                "Billing not configured. Set RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET (test keys) to enable checkout."
            ),
        }
    if not _live_allowed(key_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "Refusing to create a LIVE Razorpay resource. A live key "
                "(rzp_live_...) is configured but BILLING_LIVE is not '1'. "
                "Set BILLING_LIVE=1 to explicitly enable real billing, or use "
                "test keys (rzp_test_...) for the sandbox."
            ),
        )

    plan = PLANS[plan_key]
    currency = os.environ.get("RAZORPAY_CURRENCY", "USD")
    notes = {"user_id": str(user_id), "plan": plan_key}

    subscription_plan_id = os.environ.get(f"RAZORPAY_PLAN_{plan_key.upper()}")
    if subscription_plan_id:
        result = _razorpay_api(
            "POST",
            "/subscriptions",
            key_id,
            key_secret,
            {
                "plan_id": subscription_plan_id,
                "total_count": 12,
                "customer_notify": 1,
                "notes": notes,
            },
        )
        return {
            "configured": True,
            "mode": "test" if key_id.startswith("rzp_test_") else "live",
            "kind": "subscription",
            "id": result.get("id"),
            "short_url": result.get("short_url"),
            "razorpay_key_id": key_id,
            "plan": plan_key,
        }

    result = _razorpay_api(
        "POST",
        "/orders",
        key_id,
        key_secret,
        {
            "amount": int(plan["price_usd"]) * 100,
            "currency": currency,
            "notes": notes,
        },
    )
    return {
        "configured": True,
        "mode": "test" if key_id.startswith("rzp_test_") else "live",
        "kind": "order",
        "id": result.get("id"),
        "amount": result.get("amount"),
        "currency": result.get("currency"),
        "razorpay_key_id": key_id,
        "plan": plan_key,
    }


def _verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_context(payload: dict) -> tuple[str | None, dict, int | None]:
    """Pull (provider_id, notes, current_period_end unix) out of any Razorpay entity."""
    for key in ("subscription", "order", "payment", "invoice"):
        entity = payload.get(key, {}).get("entity")
        if not entity:
            continue
        notes = entity.get("notes") or {}
        period_end = entity.get("current_end") or entity.get("end_at")
        return entity.get("id"), notes, period_end
    return None, {}, None


def _render_billing_page(current: dict) -> str:
    current_plan = current.get("plan", "free")
    current_name = PLANS.get(current_plan, PLANS["free"])["name"]
    status = current.get("status", "active")
    period_end = current.get("current_period_end")
    renews = (
        f'<p class="renews">Current period ends {html.escape(period_end[:10])}</p>'
        if period_end
        else ""
    )

    cards = []
    for key, plan in PLANS.items():
        is_current = key == current_plan
        price = "Free" if plan["price_usd"] == 0 else f"${plan['price_usd']}<span>/mo</span>"
        features = "".join(
            f"<li>{html.escape(feature)}</li>" for feature in plan["features"]
        )
        if is_current:
            button = '<button class="btn current" disabled>Current plan</button>'
        elif key == "free":
            button = (
                f'<button class="btn ghost" data-plan="{key}">Downgrade to Free</button>'
            )
        else:
            button = f'<button class="btn primary" data-plan="{key}">Choose {html.escape(plan["name"])}</button>'
        cards.append(
            f"""
        <article class="tier {'current' if is_current else ''} tier-{key}">
          <header>
            <h2>{html.escape(plan['name'])}</h2>
            <p class="price">{price}</p>
            <p class="tagline">{html.escape(plan['tagline'])}</p>
          </header>
          <ul>{features}</ul>
          {button}
        </article>"""
        )
    cards_html = "".join(cards)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Billing &amp; Plans — Murder Bot</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: #0d1117; color: #e6edf3; }}
main {{ width: min(1080px, 94vw); margin: 0 auto; padding: 2rem 0 4rem; }}
a {{ color: #58a6ff; text-decoration: none; }}
header.top {{ display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .75rem; }}
h1 {{ margin: 0; font-size: 1.7rem; }}
.current-banner {{ margin: 1.1rem 0 1.6rem; padding: .8rem 1.1rem; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }}
.current-banner b {{ color: #fff; }}
.current-banner .renews {{ margin: .3rem 0 0; color: #8b949e; font-size: .85rem; }}
.tiers {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.1rem; }}
.tier {{ display: flex; flex-direction: column; background: #161b22; border: 1px solid #30363d; border-radius: 14px; padding: 1.3rem 1.2rem 1.4rem; }}
.tier.current {{ border-color: #238636; box-shadow: 0 0 0 1px #23863644; }}
.tier-pro {{ border-color: #1f6feb55; }}
.tier h2 {{ margin: 0 0 .2rem; font-size: 1.25rem; }}
.price {{ margin: .1rem 0 .4rem; font-size: 2rem; font-weight: 800; color: #fff; }}
.price span {{ font-size: .9rem; font-weight: 600; color: #8b949e; }}
.tagline {{ margin: 0 0 1rem; color: #adbac7; font-size: .9rem; min-height: 2.4em; }}
.tier ul {{ list-style: none; margin: 0 0 1.3rem; padding: 0; display: flex; flex-direction: column; gap: .5rem; }}
.tier li {{ position: relative; padding-left: 1.4rem; font-size: .88rem; color: #c9d1d9; }}
.tier li::before {{ content: "✓"; position: absolute; left: 0; color: #3fb950; font-weight: 800; }}
.btn {{ margin-top: auto; padding: .6rem 1rem; border-radius: 8px; border: 1px solid transparent; font-size: .95rem; font-weight: 700; cursor: pointer; }}
.btn.primary {{ background: #238636; color: #fff; }}
.btn.primary:hover {{ background: #2ea043; }}
.btn.ghost {{ background: transparent; color: #adbac7; border-color: #30363d; }}
.btn.current {{ background: #21262d; color: #8b949e; cursor: default; }}
.result {{ margin-top: 1.4rem; padding: .9rem 1.1rem; border-radius: 10px; font-size: .88rem; display: none; }}
.result.show {{ display: block; }}
.result.ok {{ background: #12261a; border: 1px solid #1c3d28; color: #3fb950; }}
.result.warn {{ background: #3d2f0b; border: 1px solid #9e6a03; color: #d29922; }}
.result.err {{ background: #2a1615; border: 1px solid #4a2321; color: #ff7b72; }}
.result code {{ color: #e6edf3; word-break: break-all; }}
footer {{ margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid #21262d; color: #6e7681; font-size: .8rem; line-height: 1.6; }}
</style>
</head>
<body>
<main>
<header class="top">
  <div><h1>Billing &amp; Plans</h1><a href="/">&larr; Dashboard</a></div>
</header>
<div class="current-banner">
  You are on the <b>{html.escape(current_name)}</b> plan
  (<b>{html.escape(status)}</b>).
  {renews}
</div>
<section class="tiers">{cards_html}</section>
<div class="result" id="result"></div>
<footer>
  <p>Payments are processed by Razorpay. In sandbox mode no real money moves —
     use Razorpay test cards.</p>
  <p><b>Automation notice:</b> Automating Evony may violate Top Games Inc.'s
     Terms of Service and can get accounts banned. Subscribe only if you accept
     that risk. See deploy/COST_MODEL.md.</p>
</footer>
</main>
<script>
const result = document.getElementById('result');
function show(kind, htmlText) {{
  result.className = 'result show ' + kind;
  result.innerHTML = htmlText;
}}
document.querySelectorAll('button[data-plan]').forEach((button) => {{
  button.addEventListener('click', async () => {{
    const plan = button.getAttribute('data-plan');
    button.disabled = true;
    try {{
      const response = await fetch('/api/billing/subscribe', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ plan }}),
      }});
      const data = await response.json();
      if (!response.ok) {{
        show('err', 'Error: ' + (data.detail || response.status));
      }} else if (data.configured === false) {{
        show('warn', data.message || 'Billing not configured.');
      }} else if (data.plan === 'free') {{
        show('ok', 'Switched to the Free plan. Reload to refresh.');
      }} else {{
        show('ok', 'Checkout created (' + (data.mode || 'test') + ' ' +
          (data.kind || '') + '): <code>' + (data.id || '') + '</code>. ' +
          'Complete payment in Razorpay to activate.');
      }}
    }} catch (error) {{
      show('err', 'Request failed: ' + error);
    }} finally {{
      button.disabled = false;
    }}
  }});
}});
</script>
</body>
</html>"""


def build_router(current_user, database) -> APIRouter:
    """Return the billing router wired to the host app's auth + DB.

    Also exposes, as attributes on the returned router for app.py to reuse:

    * ``router.require_plan(min_plan)`` — a gating dependency factory.
    * ``router.subscription_status(user_id)`` — the current-plan lookup helper.
    """
    _ensure_schema(database)
    router = APIRouter(tags=["billing"])
    require_plan = make_require_plan(current_user, database)

    @router.get("/billing", response_class=HTMLResponse)
    def billing_page(user_id: int = Depends(current_user)):
        return HTMLResponse(_render_billing_page(subscription_status(database, user_id)))

    @router.get("/api/billing/status")
    def billing_status(user_id: int = Depends(current_user)):
        current = subscription_status(database, user_id)
        key_id, key_secret = _razorpay_keys()
        return JSONResponse(
            {
                "current": current,
                "plans": {
                    key: {
                        "name": plan["name"],
                        "price_usd": plan["price_usd"],
                        "rank": plan["rank"],
                    }
                    for key, plan in PLANS.items()
                },
                "billing_configured": bool(key_id and key_secret),
            }
        )

    @router.post("/api/billing/subscribe")
    def subscribe(body: SubscribeInput, user_id: int = Depends(current_user)):
        plan_key = body.plan
        if plan_key not in PLANS:
            raise HTTPException(status_code=422, detail=f"Unknown plan: {plan_key}")

        if plan_key == "free":
            _upsert_subscription(database, user_id, "free", "active", None, None)
            return JSONResponse({"configured": True, "plan": "free", "status": "active"})

        return JSONResponse(_create_razorpay_resource(plan_key, user_id))

    @router.post("/api/billing/webhook")
    async def webhook(request: Request):
        secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
        if not secret:
            raise HTTPException(status_code=503, detail="Webhook secret not configured")
        raw_body = await request.body()
        signature = request.headers.get("X-Razorpay-Signature")
        if not _verify_webhook_signature(raw_body, signature, secret):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

        try:
            event = json.loads(raw_body.decode() or "{}")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Malformed webhook body")

        event_type = event.get("event", "")
        payload = event.get("payload", {})
        provider_id, notes, period_unix = _extract_context(payload)

        raw_user = notes.get("user_id")
        plan_key = notes.get("plan")
        try:
            user_id = int(raw_user) if raw_user is not None else None
        except (TypeError, ValueError):
            user_id = None

        activating = event_type in {
            "order.paid",
            "payment.captured",
            "subscription.activated",
            "subscription.charged",
            "subscription.authenticated",
        }
        cancelling = event_type in {
            "subscription.cancelled",
            "subscription.halted",
            "subscription.completed",
            "subscription.paused",
        }

        if user_id is None or plan_key not in PLANS or plan_key == "free":
            return JSONResponse({"ok": True, "ignored": True, "event": event_type})

        if activating:
            if period_unix:
                period_end = datetime.fromtimestamp(int(period_unix), tz=timezone.utc)
            else:
                period_end = _now() + timedelta(days=DEFAULT_PERIOD_DAYS)
            _upsert_subscription(
                database, user_id, plan_key, "active", provider_id, period_end
            )
            return JSONResponse({"ok": True, "event": event_type, "plan": plan_key})

        if cancelling:
            _upsert_subscription(database, user_id, "free", "cancelled", provider_id, None)
            return JSONResponse({"ok": True, "event": event_type, "cancelled": True})

        return JSONResponse({"ok": True, "ignored": True, "event": event_type})

    router.require_plan = require_plan
    router.subscription_status = lambda user_id: subscription_status(database, user_id)
    return router
