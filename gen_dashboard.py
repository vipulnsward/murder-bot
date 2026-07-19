import base64
import datetime
import glob
import os
import re
import subprocess

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
QTY = 269228
TARGET = 1_500_000_000
SESSION_START = 685_654_504

PROFILE = {
    "name": "NeoIsTlatoani", "alliance": "NFG", "server": "K49",
    "keep": "49", "vip": "23", "power": "113.4B", "gems": "9.8M",
    "troop": "T1 Warriors · Ground",
}


def newest_log():
    logs = sorted(glob.glob(os.path.join(HERE, "run_*.log")), key=os.path.getmtime)
    return logs[-1] if logs else None


def read_stats(log):
    rows, batches = [], 0
    for l in open(log):
        mt = re.match(r"\[(\d\d:\d\d:\d\d)\]", l)
        mo = re.search(r"own=([\d,]+)", l)
        if mt and mo:
            rows.append((mt.group(1), int(mo.group(1).replace(",", ""))))
        mb = re.search(r"batch (\d+) ok", l)
        if mb:
            batches = int(mb.group(1))
        ms = re.search(r"batches=(\d+)", l)
        if ms:
            batches = max(batches, int(ms.group(1)))
    ts = lambda s: datetime.datetime.strptime(s, "%H:%M:%S")
    rate = None
    if len(rows) >= 2:
        secs = (ts(rows[-1][0]) - ts(rows[0][0])).total_seconds() or 1
        rate = (len(rows) * 10) * QTY / secs * 60
    return (rows[-1][1] if rows else None), batches, rate


def read_food():
    raw = subprocess.run(["adb", "-s", "127.0.0.1:5555", "exec-out", "screencap", "-p"],
                         capture_output=True).stdout
    if raw:
        open(os.path.join(HERE, "status_latest.png"), "wb").write(raw)
    img = cv2.imread(os.path.join(HERE, "status_latest.png"))
    if img is None:
        return None
    g = cv2.cvtColor(img[8:64, 150:300], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3)
    _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cv2.imwrite(os.path.join(HERE, "_fd.png"), t)
    o = subprocess.run(["tesseract", os.path.join(HERE, "_fd.png"), "stdout", "--psm", "7",
                        "-c", "tessedit_char_whitelist=0123456789.KMB"],
                       capture_output=True, text=True).stdout.strip().replace(" ", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KMB])", o)
    return float(m.group(1)) * {"B": 1e9, "M": 1e6, "K": 1e3}[m.group(2)] if m else None


def shot_b64():
    img = cv2.imread(os.path.join(HERE, "status_latest.png"))
    if img is None:
        return None
    h, w = img.shape[:2]
    img = cv2.resize(img, (420, int(h * 420 / w)))
    ok, b = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return "data:image/jpeg;base64," + base64.b64encode(b).decode() if ok else None


def asset(name):
    p = os.path.join(HERE, "assets", name)
    return open(p).read().strip() if os.path.exists(p) else ""


def human(n):
    if n is None:
        return "—"
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}K"
    return str(int(n))


def main():
    log = newest_log()
    own, batches, rate = read_stats(log) if log else (None, 0, None)
    running = subprocess.run(["pgrep", "-f", "train_to_1b.py"],
                             capture_output=True).returncode == 0
    food = read_food()
    to_go = (TARGET - own) if own else None
    pct = (own / TARGET * 100) if own else 0
    eta_h = (to_go / rate / 60) if (to_go and rate) else None
    food_batches = int(food / 43_500_000) if food else None
    sess = (own - SESSION_START) if own else 0
    now = datetime.datetime.now().strftime("%b %d · %H:%M:%S")
    crest, banner, shot = asset("crest_b64.txt"), asset("banner_b64.txt"), shot_b64()
    state = "TRAINING" if running else "PAUSED"
    scls = "run" if running else "stop"
    warn = food is not None and food < 600_000_000
    P = PROFILE

    def chip(v, l):
        return f'<div class="chip"><span class="cv">{v}</span><span class="cl">{l}</span></div>'

    def stat(l, v, s=""):
        sh = f'<span class="sub">{s}</span>' if s else ""
        return f'<div class="stat"><span class="lbl">{l}</span><span class="val">{v}</span>{sh}</div>'

    empire = "".join([chip(P["power"], "Power"), chip("K" + P["keep"], "Keep"),
                      chip("VIP " + P["vip"], "VIP"), chip(P["gems"], "Gems"),
                      chip(P["server"], "Server")])
    session = "".join([
        stat("Batches this run", f"{batches:,}"),
        stat("Trained this run", f"+{batches*QTY/1e6:.1f}M"),
        stat("Trained this session", f"+{sess/1e6:.1f}M", "since 685.7M"),
        stat("Rate", (human(rate) + "/min") if rate else "—", f"{3600/(rate/QTY):.1f}s / batch" if rate else ""),
        stat("Food reserve", human(food), f"~{food_batches} batches" if food_batches else ""),
        stat("ETA to 1B", f"{eta_h:.1f} h" if eta_h else "—", "at current pace"),
    ])
    shot_html = (f'<img alt="Live game" src="{shot}">' if shot
                 else '<div class="noimg">screenshot unavailable</div>')
    warn_html = ('<div class="warn">⚠ Food reserve under 600M — an automated resupply is due shortly.</div>'
                 if warn else "")
    mon = asset("avatar_b64.txt")
    if mon:
        avatar = (f'<div class="ava"><img class="portrait" alt="Monarch" src="{mon}">'
                  + (f'<img class="crestbadge" alt="NFG" src="{crest}">' if crest else "")
                  + '</div>')
    else:
        avatar = (f'<img class="crest" alt="NFG crest" src="{crest}">' if crest
                  else '<div class="crest"></div>')

    html = f"""<title>NFG · NEO — Training Command</title>
<style>
:root{{
 --navy:#0a1322;--panel:#12233d;--panel2:#16294a;--border:#274063;--ink:#ece4cf;
 --muted:#9db0cb;--gold:#e6c568;--gold2:#caa03a;--good:#74d493;--warn:#e6c568;--bad:#e2745e;--track:#0c1a2e;
}}
@media(prefers-color-scheme:light){{:root{{
 --navy:#eceff4;--panel:#ffffff;--panel2:#f5efe0;--border:#dcd2ba;--ink:#1d2b44;--muted:#5f6f8c;
 --gold:#b1861d;--gold2:#977016;--good:#2e9e57;--warn:#b1861d;--bad:#c0503e;--track:#e7ddc6;}}}}
:root[data-theme="dark"]{{--navy:#0a1322;--panel:#12233d;--panel2:#16294a;--border:#274063;--ink:#ece4cf;
 --muted:#9db0cb;--gold:#e6c568;--gold2:#caa03a;--good:#74d493;--warn:#e6c568;--bad:#e2745e;--track:#0c1a2e;}}
:root[data-theme="light"]{{--navy:#eceff4;--panel:#ffffff;--panel2:#f5efe0;--border:#dcd2ba;--ink:#1d2b44;
 --muted:#5f6f8c;--gold:#b1861d;--gold2:#977016;--good:#2e9e57;--warn:#b1861d;--bad:#c0503e;--track:#e7ddc6;}}
*{{box-sizing:border-box;}}
body{{margin:0;background:radial-gradient(1200px 620px at 50% -12%,color-mix(in srgb,var(--gold) 10%,transparent),transparent 60%),var(--navy);
 color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5;-webkit-font-smoothing:antialiased;}}
.serif{{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;}}
.wrap{{max-width:940px;margin:0 auto;padding:28px 20px 56px;}}
.top{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:18px;}}
.crest{{width:58px;height:58px;border-radius:12px;object-fit:cover;
 border:1px solid color-mix(in srgb,var(--gold) 55%,var(--border));box-shadow:0 4px 16px rgba(0,0,0,.4);}}
.ava{{position:relative;width:62px;height:62px;flex:0 0 auto;}}
.portrait{{width:62px;height:62px;border-radius:12px;object-fit:cover;
 border:1px solid color-mix(in srgb,var(--gold) 60%,var(--border));box-shadow:0 4px 16px rgba(0,0,0,.45);}}
.crestbadge{{position:absolute;right:-7px;bottom:-7px;width:28px;height:28px;border-radius:7px;
 object-fit:cover;border:1px solid var(--gold);box-shadow:0 2px 7px rgba(0,0,0,.55);}}
.brand .name{{font-size:1.4rem;font-weight:600;color:var(--gold);letter-spacing:.01em;line-height:1.1;}}
.brand .sub{{font-size:.74rem;color:var(--muted);letter-spacing:.09em;text-transform:uppercase;margin-top:2px;}}
.pill{{font:600 .72rem/1 ui-monospace,Menlo,monospace;letter-spacing:.11em;padding:7px 12px;border-radius:999px;border:1px solid;}}
.pill.run{{color:var(--good);border-color:color-mix(in srgb,var(--good) 45%,transparent);background:color-mix(in srgb,var(--good) 12%,transparent);}}
.pill.stop{{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 45%,transparent);background:color-mix(in srgb,var(--bad) 12%,transparent);}}
.dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:currentColor;margin-right:7px;}}
.pill.run .dot{{animation:pulse 1.9s ease-in-out infinite;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
@media(prefers-reduced-motion:reduce){{.pill.run .dot{{animation:none;}}}}
.updated{{margin-left:auto;color:var(--muted);font:500 .78rem/1 ui-monospace,monospace;}}
.empire{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;}}
.chip{{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);
 border-radius:11px;padding:9px 14px;display:flex;flex-direction:column;gap:1px;min-width:76px;}}
.chip .cv{{font:600 1rem/1.1 ui-monospace,Menlo,monospace;color:var(--gold);}}
.chip .cl{{font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}}
.hero{{position:relative;overflow:hidden;border-radius:18px;border:1px solid var(--border);padding:28px 30px 24px;
 margin-bottom:16px;background:linear-gradient(180deg,var(--panel),var(--panel2));}}
.hero .bg{{position:absolute;inset:0;background-size:cover;background-position:center 30%;opacity:.15;
 mask-image:linear-gradient(180deg,#000,transparent);}}
.hero .in{{position:relative;}}
.eyebrow{{text-transform:uppercase;letter-spacing:.16em;font-size:.68rem;font-weight:600;color:var(--gold2);}}
.own{{font-weight:600;font-size:clamp(2.5rem,8vw,4rem);line-height:1;color:var(--gold);
 font-variant-numeric:tabular-nums;margin:8px 0 4px;text-shadow:0 2px 20px color-mix(in srgb,var(--gold) 22%,transparent);}}
.own small{{color:var(--muted);font-size:.32em;font-weight:500;}}
.subline{{color:var(--muted);font-size:.92rem;margin-bottom:16px;}}
.subline b{{color:var(--ink);font-variant-numeric:tabular-nums;}}
.track{{height:13px;background:var(--track);border-radius:999px;overflow:hidden;border:1px solid var(--border);
 box-shadow:inset 0 1px 3px rgba(0,0,0,.3);}}
.fill{{height:100%;width:{pct:.2f}%;border-radius:999px;background:linear-gradient(90deg,var(--gold2),var(--gold));
 box-shadow:0 0 12px color-mix(in srgb,var(--gold) 55%,transparent);}}
.pctrow{{display:flex;justify-content:space-between;margin-top:9px;font:600 .8rem/1 ui-monospace,monospace;
 color:var(--muted);font-variant-numeric:tabular-nums;}}
.pctrow b{{color:var(--gold);}}
.tagline{{margin-top:15px;padding-top:14px;border-top:1px solid var(--border);text-align:center;
 color:var(--gold2);letter-spacing:.14em;font-size:.72rem;text-transform:uppercase;}}
.warn{{margin-top:13px;padding:11px 14px;border-radius:11px;font-size:.86rem;color:var(--warn);
 border:1px solid color-mix(in srgb,var(--warn) 40%,transparent);background:color-mix(in srgb,var(--warn) 10%,transparent);}}
.cols{{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;align-items:start;}}
@media(max-width:660px){{.cols{{grid-template-columns:1fr;}}}}
.sect{{font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);font-weight:600;margin:2px 2px 10px;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.stat{{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);
 border-radius:13px;padding:14px 16px;display:flex;flex-direction:column;gap:3px;}}
.stat .lbl{{text-transform:uppercase;letter-spacing:.08em;font-size:.64rem;color:var(--muted);font-weight:600;}}
.stat .val{{font:600 1.3rem/1.1 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;color:var(--ink);}}
.stat .sub{{font-size:.7rem;color:var(--muted);}}
.shot{{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);
 border-radius:16px;padding:12px;display:flex;flex-direction:column;gap:9px;}}
.shot img{{width:100%;border-radius:10px;display:block;border:1px solid var(--border);}}
.shot .cap{{text-align:center;font-size:.68rem;color:var(--muted);letter-spacing:.09em;text-transform:uppercase;}}
.noimg{{color:var(--muted);text-align:center;padding:44px 0;}}
.foot{{margin-top:22px;text-align:center;color:var(--muted);font-size:.74rem;}}
.foot b{{color:var(--gold2);}}
</style>
<div class="wrap">
 <div class="top">
  {avatar}
  <div class="brand">
   <div class="name serif">{P['name']}</div>
   <div class="sub">[{P['alliance']}] · Server {P['server']} · {P['troop']}</div>
  </div>
  <div class="pill {scls}"><span class="dot"></span>{state}</div>
  <div class="updated">{now}</div>
 </div>

 <div class="empire">{empire}</div>

 <div class="hero">
  <div class="bg" style="background-image:url('{banner}')"></div>
  <div class="in">
   <div class="eyebrow">T1 Warriors mustered · goal 1,000,000,000</div>
   <div class="own">{own:,}<small> / 1B</small></div>
   <div class="subline"><b>{to_go:,}</b> to go · <b>{(to_go//QTY) if to_go else 0:,}</b> batches remaining</div>
   <div class="track"><div class="fill"></div></div>
   <div class="pctrow"><span><b>{pct:.1f}%</b> to goal</span><span>{(human(rate)+" / min") if rate else ""}</span></div>
   {warn_html}
   <div class="tagline">Together we build · Together we conquer</div>
  </div>
 </div>

 <div class="cols">
  <div>
   <div class="sect">Training Session</div>
   <div class="grid">{session}</div>
  </div>
  <div class="shot">
   <div class="sect" style="margin-bottom:2px">Live Feed</div>
   {shot_html}
   <div class="cap">BlueStacks · real-time</div>
  </div>
 </div>

 <div class="foot"><b>NFG</b> Vision Bot · ADB + OpenCV + Tesseract · auto-refreshed each minute</div>
</div>
"""
    open(os.path.join(HERE, "evony_status.html"), "w").write(html)
    print(f"wrote evony_status.html | own={own} batches={batches} food={human(food)} running={running}")


if __name__ == "__main__":
    main()
