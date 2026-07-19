import glob
import http.server
import json
import os
import re
import socketserver
import subprocess
import threading
import time

import cv2
import numpy as np

DEVICE = "127.0.0.1:5555"
PORT = 8088
FPS = 1.3
HERE = os.path.dirname(os.path.abspath(__file__))
QTY = 269228
TARGET = 1_500_000_000
SESSION_START = 685_654_504

_latest = {"jpg": None, "food": None, "own": None}


def grab_raw():
    raw = subprocess.run(["adb", "-s", DEVICE, "exec-out", "screencap", "-p"],
                         capture_output=True).stdout
    if not raw:
        return None
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def read_food(img):
    g = cv2.cvtColor(img[8:64, 150:300], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3)
    _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    p = os.path.join(HERE, "_lfd.png")
    cv2.imwrite(p, t)
    o = subprocess.run(["tesseract", p, "stdout", "--psm", "7",
                        "-c", "tessedit_char_whitelist=0123456789.KMB"],
                       capture_output=True, text=True).stdout.strip().replace(" ", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KMB])", o)
    return float(m.group(1)) * {"B": 1e9, "M": 1e6, "K": 1e3}[m.group(2)] if m else None


def ocr_own(img):
    g = cv2.cvtColor(img[1070:1140, 330:760], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2.5, fy=2.5)
    _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p = os.path.join(HERE, "_lown.png")
    cv2.imwrite(p, t)
    o = subprocess.run(["tesseract", p, "stdout", "--psm", "7",
                        "-c", "tessedit_char_whitelist=0123456789,"],
                       capture_output=True, text=True).stdout
    m = re.findall(r"[\d,]{4,}", o)
    if m:
        v = int(max(m, key=len).replace(",", ""))
        if 800_000_000 <= v <= 1_600_000_000:
            return v
    return None


def capture_loop():
    last = 0.0
    while True:
        img = grab_raw()
        if img is not None:
            h, w = img.shape[:2]
            small = cv2.resize(img, (460, int(h * 460 / w)))
            ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 68])
            if ok:
                _latest["jpg"] = jpg.tobytes()
            now = time.monotonic()
            if now - last >= 10:
                f = read_food(img)
                if f:
                    _latest["food"] = f
                o = ocr_own(img)
                if o:
                    _latest["own"] = o
                last = now
        time.sleep(1.0 / FPS)


def stats():
    logs = sorted(glob.glob(os.path.join(HERE, "run_*.log")), key=os.path.getmtime)
    own = batches = 0
    rows = []
    if logs:
        for l in open(logs[-1]):
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
        if rows:
            own = rows[-1][1]
    rate = None
    if len(rows) >= 2:
        ts = lambda s: time.strptime(s, "%H:%M:%S")
        import calendar
        secs = calendar.timegm(ts(rows[-1][0])) - calendar.timegm(ts(rows[0][0])) or 1
        rate = (len(rows) * 10) * QTY / secs * 60
    running = subprocess.run(["pgrep", "-f", "train_to_1b.py"],
                             capture_output=True).returncode == 0
    food = _latest["food"]
    if _latest.get("own"):
        own = max(own, _latest["own"])
    return {"own": own, "batches": batches, "rate": rate, "food": food,
            "running": running, "pct": own / TARGET * 100 if own else 0,
            "to_go": TARGET - own if own else TARGET,
            "session": own - SESSION_START if own else 0}


def asset(n):
    p = os.path.join(HERE, "assets", n)
    return open(p).read().strip() if os.path.exists(p) else ""


def page():
    av = asset("avatar_b64.txt") or asset("crest_b64.txt")
    crest = asset("crest_b64.txt")
    return ("""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>NFG - Live Command</title>
<style>
:root{--navy:#0a1322;--panel:#12233d;--panel2:#16294a;--bd:#274063;--ink:#ece4cf;--muted:#9db0cb;--gold:#e6c568;--good:#74d493;--bad:#e2745e;--track:#0c1a2e}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1000px 500px at 50% -10%,rgba(230,197,104,.09),transparent 60%),var(--navy);color:var(--ink);font-family:system-ui,sans-serif;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:22px 16px 46px}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.av{position:relative;width:54px;height:54px}.av img{width:54px;height:54px;border-radius:11px;object-fit:cover;border:1px solid rgba(230,197,104,.6)}
.bdg{position:absolute;right:-6px;bottom:-6px;width:24px;height:24px;border-radius:6px;border:1px solid var(--gold)}
.name{font:600 1.2rem/1.1 "Iowan Old Style",Palatino,Georgia,serif;color:var(--gold)}
.sub{font-size:.72rem;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
.pill{margin-left:auto;font:600 .7rem/1 ui-monospace,monospace;letter-spacing:.1em;padding:7px 12px;border-radius:999px;border:1px solid}
.run{color:var(--good);border-color:rgba(116,212,147,.5);background:rgba(116,212,147,.12)}
.stop{color:var(--bad);border-color:rgba(226,116,94,.5);background:rgba(226,116,94,.12)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:currentColor;margin-right:6px;animation:p 1.7s infinite}@keyframes p{50%{opacity:.3}}
.grid{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;align-items:start}@media(max-width:680px){.grid{grid-template-columns:1fr}}
.feed{background:var(--panel);border:1px solid var(--bd);border-radius:16px;padding:10px}
.feed img{width:100%;border-radius:10px;display:block;border:1px solid var(--bd)}
.cap{text-align:center;font-size:.66rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;padding:7px 0 3px}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:16px;padding:20px}
.eye{font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);font-weight:600}
.own{font:600 clamp(2rem,7vw,3rem)/1 ui-monospace,monospace;color:var(--gold);font-variant-numeric:tabular-nums;margin:6px 0 3px}
.own small{color:var(--muted);font-size:.34em}
.sl{color:var(--muted);font-size:.86rem;margin-bottom:14px}.sl b{color:var(--ink)}
.track{height:12px;background:var(--track);border:1px solid var(--bd);border-radius:999px;overflow:hidden}
.fill{height:100%;background:linear-gradient(90deg,#caa03a,var(--gold));border-radius:999px;transition:width .6s}
.pr{display:flex;justify-content:space-between;margin-top:8px;font:600 .78rem/1 ui-monospace,monospace;color:var(--muted)}.pr b{color:var(--gold)}
.mini{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px}
.st{background:var(--panel2);border:1px solid var(--bd);border-radius:11px;padding:11px 13px}
.st .l{font-size:.6rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.st .v{font:600 1.05rem/1.1 ui-monospace,monospace;color:var(--ink)}
.tag{margin-top:14px;padding-top:12px;border-top:1px solid var(--bd);text-align:center;color:#caa03a;letter-spacing:.13em;font-size:.68rem;text-transform:uppercase}
</style></head><body><div class=wrap>
<div class=top>
 <div class=av><img src=\"""" + av + """\">""" + (f'<img class=bdg src="{crest}">' if (av and crest and av != crest) else "") + """</div>
 <div><div class=name>NeoIsTlatoani</div><div class=sub>[NFG] &middot; K49 &middot; Live Command</div></div>
 <div id=pill class="pill run"><span class=dot></span>LIVE</div>
</div>
<div class=grid>
 <div class=feed><img id=vid src="/stream" alt="live game"><div class=cap>BlueStacks &middot; live feed</div></div>
 <div class=card>
  <div class=eye>T1 Warriors &middot; goal 1B</div>
  <div class=own id=own>&mdash;<small> / 1B</small></div>
  <div class=sl id=sl>&nbsp;</div>
  <div class=track><div class=fill id=fill style=width:0></div></div>
  <div class=pr><span id=pct><b>&mdash;</b></span><span id=rate></span></div>
  <div class=mini>
   <div class=st><div class=l>Batches</div><div class=v id=b>&mdash;</div></div>
   <div class=st><div class=l>Food</div><div class=v id=f>&mdash;</div></div>
   <div class=st><div class=l>This session</div><div class=v id=se>&mdash;</div></div>
   <div class=st><div class=l>To go</div><div class=v id=tg>&mdash;</div></div>
  </div>
  <div class=tag>Together we build &middot; Together we conquer</div>
 </div>
</div></div>
<script>
function h(n){if(n==null)return'\\u2014';if(n>=1e9)return(n/1e9).toFixed(2)+'B';if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return''+Math.round(n)}
async function up(){try{let s=await(await fetch('/stats')).json();
document.getElementById('own').innerHTML=s.own.toLocaleString()+'<small> / 1B</small>';
document.getElementById('sl').innerHTML='<b>'+s.to_go.toLocaleString()+'</b> to go &middot; <b>'+Math.floor(s.to_go/269228).toLocaleString()+'</b> batches';
document.getElementById('fill').style.width=s.pct+'%';
document.getElementById('pct').innerHTML='<b>'+s.pct.toFixed(1)+'%</b> to goal';
document.getElementById('rate').textContent=s.rate?h(s.rate)+' / min':'';
document.getElementById('b').textContent=s.batches.toLocaleString();
document.getElementById('f').textContent=h(s.food);
document.getElementById('se').textContent='+'+h(s.session);
document.getElementById('tg').textContent=h(s.to_go);
let p=document.getElementById('pill');p.className='pill '+(s.running?'run':'stop');
p.innerHTML='<span class=dot></span>'+(s.running?'LIVE':'PAUSED');
}catch(e){}}
up();setInterval(up,10000);
var V=document.getElementById('vid');
function rc(){V.src='/stream?t='+Date.now();}
V.onerror=function(){setTimeout(rc,1200);};
document.addEventListener('visibilitychange',function(){if(!document.hidden){rc();up();}});
window.addEventListener('focus',rc);
window.addEventListener('online',rc);
</script></body></html>""").encode()


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    j = _latest["jpg"]
                    if j:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(j)).encode() + b"\r\n\r\n" + j + b"\r\n")
                    time.sleep(1.0 / FPS)
            except (BrokenPipeError, ConnectionResetError):
                return
        elif self.path.startswith("/stats"):
            body = json.dumps(stats()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(page())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=capture_loop, daemon=True).start()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), H) as srv:
        print(f"live dashboard on :{PORT}", flush=True)
        srv.serve_forever()
