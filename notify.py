"""Push notifications for the bot's human-in-the-loop events (kb/30 fail-safe).

Alerts a human when an unattended run needs attention: account-disconnect,
self-detected bot-tell (TooManyClicks), under-attack, crash, "needs takeover".
No-ops silently on any missing channel / failure, so it's always safe to call.
Dependency-free (stdlib only).

Channels (in send order):
  - macOS banner   -> DEFAULT ON (bot runs locally on this Mac; zero config).
                      Disable with EVONY_NOTIFY_MAC=0.
  - Slack          -> EVONY_NOTIFY_SLACK = an incoming-webhook URL (posts {"text": ...}).
  - Discord        -> EVONY_NOTIFY_DISCORD = a webhook URL (posts {"content": ...}).
"""

import json
import subprocess
import urllib.request

SLACK_ENV = "EVONY_NOTIFY_SLACK"
DISCORD_ENV = "EVONY_NOTIFY_DISCORD"
MAC_ENV = "EVONY_NOTIFY_MAC"          # set to "0" to silence the local banner
_ICON = {"info": "•", "warn": "⚠️", "alert": "🚨", "ok": "✅"}
_SOUND = {"alert": "Sosumi", "warn": "Funk"}   # only the loud levels make a sound


def _post(url, payload, timeout=10):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=timeout).read()


def _mac_banner(title, body, level, runner):
    # AppleScript string-escape: backslash first, then double-quote.
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(body)}" with title "{esc(title)}"'
    snd = _SOUND.get(level)
    if snd:
        script += f' sound name "{esc(snd)}"'
    runner(["osascript", "-e", script])


def notify(msg, level="info", env=None, poster=_post, mac_runner=None):
    """Send `msg` to every configured channel. Returns list of channels reached.
    Never raises — a notification failure must not crash the bot."""
    import os
    env = env if env is not None else os.environ
    text = f"{_ICON.get(level, '•')} [evony-bot] {msg}"
    sent = []

    if env.get(MAC_ENV, "1").strip() != "0":
        runner = mac_runner or (lambda a: subprocess.run(a, capture_output=True, timeout=5))
        try:
            _mac_banner("evony-bot", msg, level, runner)
            sent.append("mac")
        except Exception:
            pass

    slack = env.get(SLACK_ENV, "").strip()
    if slack:
        try:
            poster(slack, {"text": text})
            sent.append("slack")
        except Exception:
            pass

    dis = env.get(DISCORD_ENV, "").strip()
    if dis:
        try:
            poster(dis, {"content": text})
            sent.append("discord")
        except Exception:
            pass

    return sent


if __name__ == "__main__":
    ok = True
    posts, banners = [], []
    fake_post = lambda url, payload, timeout=10: posts.append((url, payload))
    fake_mac = lambda argv: banners.append(argv)

    # 1) default (no webhooks) -> mac banner only, no HTTP
    posts.clear(); banners.clear()
    r = notify("disconnect detected", level="alert", env={}, poster=fake_post, mac_runner=fake_mac)
    script = banners[0][2] if banners else ""
    print(f"default -> sent={r} posts={len(posts)} sound_in_script={'sound name' in script}")
    ok &= r == ["mac"] and len(posts) == 0 and "disconnect detected" in script and "sound name" in script

    # 2) mac silenced -> nothing on empty env
    posts.clear(); banners.clear()
    r = notify("x", env={MAC_ENV: "0"}, poster=fake_post, mac_runner=fake_mac)
    print(f"mac-off, no webhooks -> sent={r}")
    ok &= r == [] and len(banners) == 0

    # 3) slack + discord formats (icon-prefixed; slack=text, discord=content)
    posts.clear(); banners.clear()
    r = notify("under attack", level="warn",
               env={MAC_ENV: "0", SLACK_ENV: "https://hooks.slack/x", DISCORD_ENV: "https://discord/x"},
               poster=fake_post, mac_runner=fake_mac)
    slack_body = next((p for u, p in posts if "slack" in u), {})
    disc_body = next((p for u, p in posts if "discord" in u), {})
    print(f"webhooks -> sent={r} slack={slack_body.get('text')!r} discord={disc_body.get('content')!r}")
    ok &= r == ["slack", "discord"] and slack_body.get("text", "").startswith("⚠️ [evony-bot]") \
          and "under attack" in disc_body.get("content", "")

    # 4) an escape-worthy body must not break the AppleScript quoting
    posts.clear(); banners.clear()
    notify('say "hi" \\ done', env={}, poster=fake_post, mac_runner=fake_mac)
    s = banners[0][2]
    print(f'escaping -> {s!r}')
    ok &= '\\"hi\\"' in s and "\\\\" in s

    # 5) a raising channel must NOT propagate
    posts.clear()
    def boom(*a, **k): raise RuntimeError("down")
    r = notify("y", env={MAC_ENV: "0", SLACK_ENV: "https://x"}, poster=boom, mac_runner=fake_mac)
    print(f"poster-error -> sent={r} (must be [])")
    ok &= r == []

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
