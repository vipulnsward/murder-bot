"""LLM vision fallback for the orchestrator.

When the deterministic FSM/template layer is stuck or on an unknown screen, hand
the frame to a vision LLM grounded in our KB (screen catalog + hard safety rules)
and get back ONE structured action. Cheap because it only fires when stuck.

Dependency-free: calls the Anthropic Messages API over stdlib urllib.

SAFETY (encoded in the system prompt AND re-checked in code):
  - NEVER tap a gem-spend path (Finish All / Instant Finish / any "Spend N Gems").
  - NEVER tap Quit/Restart on the account-disconnect screen -> return action "stop".
"""

import base64
import json
import os
import urllib.request

import cv2

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5vl:7b"  # validated on Evony screens; llava:7b was too weak
PROVIDER = os.environ.get("EVONY_LLM_PROVIDER", "ollama")  # 'ollama' (local, free) or 'anthropic'
DEVICE_W, DEVICE_H = 1080, 1920
SEND_W, SEND_H = 540, 960  # half-scale to cut tokens; coords scaled back x2

# KB-grounded screen catalog + rules (distilled from kb/11-19).
SYSTEM = f"""You are the recovery controller for an automation bot playing Evony: The King's Return
on an Android emulator (portrait, real device {DEVICE_W}x{DEVICE_H}). The deterministic layer got
stuck or hit an unknown screen and is asking you what ONE action to take next.

The image you receive is {SEND_W}x{SEND_H} (half of the real screen). Return tap/swipe coordinates
IN THAT {SEND_W}x{SEND_H} IMAGE SPACE; the caller scales them up.

Screen catalog (what you may see):
- training screen: a green "Train" button (idle) or a "Speed Up" button (a batch is training).
- Training Speedup modal: a list of speedup items, with "Finish All" (orange, left) and "Use"
  (green, right). "Finish All" can spend GEMS; "Use" spends only items.
- barracks radial/dial: a ring of options around the barracks (View/Train, Duty, Speed Up,
  Instant Finish, Cancel...). "Instant Finish" spends GEMS.
- city view: the isometric city map with buildings.
- Resources screen: lists of resource item boxes (food, etc.).
- exit dialog: "Are you sure you want to exit the game?" with Cancel/Quit.
- capacity popup: "adjust to N?" confirm.
- ACCOUNT-DISCONNECT screen: "You've been disconnected because someone login with your account"
  with Quit/Restart. This means another controller took the account.

GOAL: get back to the training screen so troop training can continue.

HARD SAFETY RULES (never violate):
1. NEVER tap any gem-spend control: "Finish All", "Instant Finish", any "Spend N Gems", "Buy".
   To clear a training batch use "Use" (items) or the training screen's normal flow.
2. On the ACCOUNT-DISCONNECT screen, do NOT tap Quit or Restart. Return action "stop".
3. If you are unsure or the screen looks dangerous/unknown, return action "stop".

Respond with ONLY a JSON object, no prose:
{{"screen": "<your label>", "action": "tap|swipe|back|wait|done|stop",
  "x": <int|null>, "y": <int|null>, "x2": <int|null>, "y2": <int|null>,
  "reason": "<short why>"}}
- action "done": already on the training screen, nothing to do.
- action "back": press Android back.
- action "wait": loading/transition, wait and re-check.
- action "stop": disconnect screen, gem-risk, or unsafe/unknown -> hand back to human/deterministic.
"""

GEM_WORDS = ("finish all", "instant finish", "spend", "gem", "buy")


def _encode(image_path_or_bgr):
    img = cv2.imread(image_path_or_bgr) if isinstance(image_path_or_bgr, str) else image_path_or_bgr
    if img is None:
        raise ValueError("no image")
    small = cv2.resize(img, (SEND_W, SEND_H), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode()


def decide(image, goal="reach the training screen", extra_context="",
           provider=None, model=None, timeout=120):
    """Return a validated action dict. Safety is enforced in code, not just the prompt.
    provider: 'ollama' (local llava, free) or 'anthropic'."""
    provider = provider or PROVIDER
    b64 = _encode(image)
    user_text = f"Goal: {goal}\n{extra_context}\nWhat ONE action? Respond with ONLY the JSON object."
    if provider == "ollama":
        txt = _call_ollama(b64, user_text, model or OLLAMA_MODEL, timeout)
    else:
        txt = _call_anthropic(b64, user_text, model or MODEL, timeout)
    return _enforce_safety(_parse(txt))


def _call_ollama(b64, user_text, model, timeout):
    body = json.dumps({
        "model": model, "stream": False, "format": "json", "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_text, "images": [b64]},
        ],
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"content-type": "application/json"})
    r = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(r.read()).get("message", {}).get("content", "")


def _call_anthropic(b64, user_text, model, timeout):
    user = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": user_text},
    ]
    body = json.dumps({
        "model": model, "max_tokens": 400, "system": SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "anthropic-version": "2023-06-01", "content-type": "application/json",
    })
    r = urllib.request.urlopen(req, timeout=timeout)
    return "".join(b.get("text", "") for b in json.loads(r.read()).get("content", []))


def _parse(txt):
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e < 0:
        return {"action": "stop", "reason": "unparseable", "raw": txt[:200]}
    try:
        return json.loads(txt[s:e + 1])
    except Exception:
        return {"action": "stop", "reason": "bad json", "raw": txt[:200]}


def _enforce_safety(act):
    """Code-level safety net independent of the model."""
    reason = str(act.get("reason", "")).lower()
    screen = str(act.get("screen", "")).lower()
    if "disconnect" in screen or "someone login" in reason:
        return {"action": "stop", "screen": "disconnect", "reason": "account disconnect — never tap"}
    if any(w in reason for w in GEM_WORDS) or any(w in screen for w in ("finish all", "instant finish")):
        return {"action": "stop", "screen": screen, "reason": f"gem-risk blocked ({reason})"}
    # scale tap/swipe coords from SEND space to device space
    for k in ("x", "y", "x2", "y2"):
        v = act.get(k)
        if isinstance(v, (int, float)):
            act[k] = int(v * (DEVICE_W / SEND_W if k in ("x", "x2") else DEVICE_H / SEND_H))
    return act


if __name__ == "__main__":
    import sys

    cases = sys.argv[1:] or [
        ("status_r2.png", "stop"),       # account disconnect -> MUST stop, never Restart
        ("_cur.png", "done"),            # already on training screen
        ("status_fresh.png", "tap/back"),# city with barracks -> navigate
        ("status_bar.png", "safe"),      # radial w/ Speed Up + gem buttons -> must not pick gems
    ]
    for item in cases:
        f, expect = item if isinstance(item, tuple) else (item, "?")
        if not os.path.exists(f):
            print(f"(skip {f})"); continue
        try:
            act = decide(f)
            safe = not (act.get("action") == "tap" and act.get("screen", "").lower().find("disconnect") >= 0)
            print(f"{f} (expect {expect}) -> {json.dumps(act)}")
        except Exception as e:
            print(f"{f}: ERROR {e!r}")
