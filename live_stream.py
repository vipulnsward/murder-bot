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
FPS = 3.0
WIDTH = 640
QUALITY = 80
HERE = os.path.dirname(os.path.abspath(__file__))
QTY = 269228
TARGET = 1_500_000_000
SESSION_START = 685_654_504

try:
    from gen_dashboard import FRAG
except Exception:
    FRAG = ""

BG_JS = r"""(function(){
 var cvs=document.getElementById('core'); if(!cvs)return;
 var reduce=matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches;
 var gl=null; try{gl=cvs.getContext('webgl')||cvs.getContext('experimental-webgl');}catch(e){}
 var frag=document.getElementById('frag').textContent;
 var vert='attribute vec2 p;void main(){gl_Position=vec4(p,0.0,1.0);}';
 var prog,uR,uT,uM,uPIX,uMO,scale=0.58,mo=[0,0],moT=[0,0],start=null,pixStart=null;
 function sh(t,s){var o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
  if(!gl.getShaderParameter(o,gl.COMPILE_STATUS)){console.warn(gl.getShaderInfoLog(o));return null;}return o;}
 function resize(){var w=Math.max(2,Math.floor(innerWidth*scale)),h=Math.max(2,Math.floor(innerHeight*scale));cvs.width=w;cvs.height=h;gl.viewport(0,0,w,h);}
 function init(){if(!gl)return false;var vs=sh(gl.VERTEX_SHADER,vert),fs=sh(gl.FRAGMENT_SHADER,frag);if(!vs||!fs)return false;
  prog=gl.createProgram();gl.attachShader(prog,vs);gl.attachShader(prog,fs);gl.linkProgram(prog);
  if(!gl.getProgramParameter(prog,gl.LINK_STATUS)){console.warn(gl.getProgramInfoLog(prog));return false;}gl.useProgram(prog);
  var buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);
  var loc=gl.getAttribLocation(prog,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
  uR=gl.getUniformLocation(prog,'R');uT=gl.getUniformLocation(prog,'T');uM=gl.getUniformLocation(prog,'M');
  uPIX=gl.getUniformLocation(prog,'PIX');uMO=gl.getUniformLocation(prog,'MO');resize();return true;}
 function pixNow(ts){if(reduce)return 1;if(pixStart===null)pixStart=ts;var k=Math.min((ts-pixStart)/1300,1);k=1-Math.pow(1-k,3);return 1+46*(1-k);}
 function frame(ts){if(start===null)start=ts;var tsec=(ts-start)/1000;moT[0]+=(mo[0]-moT[0])*0.05;moT[1]+=(mo[1]-moT[1])*0.05;
  gl.uniform2f(uR,cvs.width,cvs.height);gl.uniform1f(uT,tsec);gl.uniform1f(uM,reduce?0:1);gl.uniform1f(uPIX,pixNow(ts)*scale);gl.uniform2f(uMO,moT[0],moT[1]);
  gl.drawArrays(gl.TRIANGLES,0,3);requestAnimationFrame(frame);}
 if(init()){addEventListener('resize',resize);addEventListener('pointermove',function(e){mo[0]=(e.clientX/innerWidth-0.5)*2;mo[1]=-(e.clientY/innerHeight-0.5)*2;});requestAnimationFrame(frame);}
 else{cvs.style.display='none';}
})();"""

_latest = {"jpg": None, "food": None, "own": None, "seq": 0}


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
        t0 = time.monotonic()
        img = grab_raw()
        if img is not None:
            h, w = img.shape[:2]
            small = cv2.resize(img, (WIDTH, int(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode(".jpg", small,
                                   [cv2.IMWRITE_JPEG_QUALITY, QUALITY, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
            if ok:
                _latest["jpg"] = jpg.tobytes()
                _latest["seq"] += 1
            if t0 - last >= 10:
                f = read_food(img)
                if f:
                    _latest["food"] = f
                o = ocr_own(img)
                if o:
                    _latest["own"] = o
                last = t0
        dt = time.monotonic() - t0
        time.sleep(max(0.0, 1.0 / FPS - dt))


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
:root{--navy:#070d18;--panel:rgba(16,30,54,.66);--panel2:rgba(20,34,60,.58);--bd:rgba(230,197,104,.24);--ink:#f3ecda;--muted:#c2cfe2;--gold:#f0d27e;--good:#8be0a6;--bad:#e2745e;--track:rgba(6,14,26,.78)}
*{box-sizing:border-box}body{margin:0;background:#070d18;color:var(--ink);font-family:system-ui,sans-serif;line-height:1.5;overflow-x:hidden}
#core{position:fixed;inset:0;width:100vw;height:100vh;z-index:-2;display:block}
.scrim{position:fixed;inset:0;z-index:-1;pointer-events:none;background:radial-gradient(130% 100% at 50% 40%,transparent 30%,rgba(4,7,15,.4)),linear-gradient(180deg,rgba(6,10,20,.14),rgba(6,10,20,.34))}
.wrap{max-width:900px;margin:0 auto;padding:22px 16px 46px;position:relative;z-index:1}
.top,.cap,.tag{text-shadow:0 1px 4px rgba(0,0,0,.78)}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.av{position:relative;width:54px;height:54px}.av img{width:54px;height:54px;border-radius:11px;object-fit:cover;border:1px solid rgba(230,197,104,.6)}
.bdg{position:absolute;right:-6px;bottom:-6px;width:24px;height:24px;border-radius:6px;border:1px solid var(--gold)}
.brand{flex:1 1 auto;min-width:0}
.name{font:600 1.2rem/1.1 "Iowan Old Style",Palatino,Georgia,serif;color:var(--gold);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{font-size:.72rem;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill{flex:0 0 auto}
@media(max-width:460px){.top{gap:9px}.av{width:44px;height:44px}.av img{width:44px;height:44px}
 .name{font-size:1.02rem}.sub{font-size:.58rem;letter-spacing:.04em}
 .pill{padding:6px 9px;font-size:.6rem;letter-spacing:.06em}.wrap{padding:16px 12px 40px}}
.pill{margin-left:auto;font:600 .7rem/1 ui-monospace,monospace;letter-spacing:.1em;padding:7px 12px;border-radius:999px;border:1px solid}
.run{color:var(--good);border-color:rgba(116,212,147,.5);background:rgba(116,212,147,.12)}
.stop{color:var(--bad);border-color:rgba(226,116,94,.5);background:rgba(226,116,94,.12)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:currentColor;margin-right:6px;animation:p 1.7s infinite}@keyframes p{50%{opacity:.3}}
.grid{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;align-items:start}@media(max-width:680px){.grid{grid-template-columns:1fr}}
.feed{background:var(--panel);border:1px solid var(--bd);border-radius:16px;padding:10px;backdrop-filter:blur(13px) saturate(1.15);box-shadow:0 18px 50px rgba(0,0,0,.4)}
.feed img,.feed video{width:100%;border-radius:10px;display:block;border:1px solid var(--bd);background:#05070d}
.cap{text-align:center;font-size:.66rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;padding:7px 0 3px}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:16px;padding:20px;backdrop-filter:blur(13px) saturate(1.15);box-shadow:0 18px 50px rgba(0,0,0,.4)}
.eye{font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);font-weight:600}
.own{font:600 clamp(2rem,7vw,3rem)/1 ui-monospace,monospace;color:var(--gold);font-variant-numeric:tabular-nums;margin:6px 0 3px}
.own small{color:var(--muted);font-size:.34em}
.sl{color:var(--muted);font-size:.86rem;margin-bottom:14px}.sl b{color:var(--ink)}
.track{height:12px;background:var(--track);border:1px solid var(--bd);border-radius:999px;overflow:hidden}
.fill{height:100%;background:linear-gradient(90deg,#caa03a,var(--gold));border-radius:999px;transition:width .6s}
.pr{display:flex;justify-content:space-between;margin-top:8px;font:600 .78rem/1 ui-monospace,monospace;color:var(--muted)}.pr b{color:var(--gold)}
.mini{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px}
.st{background:var(--panel2);border:1px solid var(--bd);border-radius:11px;padding:11px 13px;backdrop-filter:blur(9px)}
.st .l{font-size:.6rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.st .v{font:600 1.05rem/1.1 ui-monospace,monospace;color:var(--ink)}
.tag{margin-top:14px;padding-top:12px;border-top:1px solid var(--bd);text-align:center;color:#caa03a;letter-spacing:.13em;font-size:.68rem;text-transform:uppercase}
.road{margin-top:14px;display:flex;flex-direction:column;gap:7px}
.ph{display:flex;align-items:center;gap:8px;font:600 .76rem/1.2 system-ui;color:var(--muted);padding:9px 12px;border:1px solid var(--bd);border-radius:10px;background:var(--panel2)}
.ph.act{color:var(--ink);border-color:rgba(230,197,104,.45);box-shadow:0 0 14px rgba(230,197,104,.1)}
.phn{font:700 .72rem/1 ui-monospace,monospace;color:#caa03a}
.phs{margin-left:auto;font-size:.56rem;letter-spacing:.09em;text-transform:uppercase;color:var(--gold);border:1px solid rgba(230,197,104,.35);border-radius:999px;padding:2px 8px}
</style></head><body><canvas id=core></canvas><div class=scrim></div><div class=wrap>
<div class=top>
 <div class=av><img src=\"""" + av + """\">""" + (f'<img class=bdg src="{crest}">' if (av and crest and av != crest) else "") + """</div>
 <div class=brand><div class=name>NeoIsTlatoani</div><div class=sub>[NFG] &middot; K49 &middot; Live Command</div></div>
 <div id=pill class="pill run"><span class=dot></span>LIVE</div>
</div>
<div class=grid>
 <div class=feed><video id=vid autoplay muted playsinline loop></video><div class=cap>BlueStacks &middot; live feed &middot; HD 30fps</div></div>
 <div class=card>
  <div class=eye>T1 Warriors &middot; goal 1.5B <span style="color:#f2d885;font-weight:700">&#9733; 1B done</span></div>
  <div class=own id=own>&mdash;<small> / 1.5B</small></div>
  <div class=sl id=sl>&nbsp;</div>
  <div class=track><div class=fill id=fill style=width:0></div></div>
  <div class=pr><span id=pct><b>&mdash;</b></span><span id=rate></span></div>
  <div class=mini>
   <div class=st><div class=l>Batches</div><div class=v id=b>&mdash;</div></div>
   <div class=st><div class=l>Food</div><div class=v id=f>&mdash;</div></div>
   <div class=st><div class=l>This session</div><div class=v id=se>&mdash;</div></div>
   <div class=st><div class=l>To go</div><div class=v id=tg>&mdash;</div></div>
  </div>
  <div class=road>
   <div class="ph act"><span class=phn>01</span> T1 Warriors &rarr; 1.5B <span class=phs>Now</span></div>
   <div class=ph><span class=phn>02</span> T2 Ground &rarr; 1B <span class=phs>Next</span></div>
  </div>
  <div class=tag>Together we build &middot; Together we conquer</div>
 </div>
</div></div>
<script>
function h(n){if(n==null)return'\\u2014';if(n>=1e9)return(n/1e9).toFixed(2)+'B';if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return''+Math.round(n)}
async function up(){try{let s=await(await fetch('/stats')).json();
document.getElementById('own').innerHTML=s.own.toLocaleString()+'<small> / 1.5B</small>';
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
V.muted=true;V.defaultMuted=true;V.setAttribute('playsinline','');V.setAttribute('autoplay','');
var HLSURL='/hls/stream.m3u8',hls=null,native=V.canPlayType('application/vnd.apple.mpegurl');
function tryplay(){var p=V.play();if(p&&p.catch)p.catch(function(){});}
['click','touchstart','keydown'].forEach(function(e){document.addEventListener(e,tryplay,{once:true,passive:true});});
function attach(){
 if(!(window.Hls&&Hls.isSupported()))return;
 if(hls){try{hls.destroy();}catch(e){}}
 hls=new Hls({lowLatencyMode:true,liveSyncDurationCount:2,liveMaxLatencyDurationCount:6,maxBufferLength:6,backBufferLength:4,manifestLoadingMaxRetry:8,levelLoadingMaxRetry:8,fragLoadingMaxRetry:8});
 hls.loadSource(HLSURL);hls.attachMedia(V);
 hls.on(Hls.Events.MANIFEST_PARSED,function(){V.play().catch(function(){});});
 hls.on(Hls.Events.ERROR,function(ev,d){if(!d.fatal)return;
  if(d.type==='networkError'){setTimeout(function(){try{hls.startLoad();}catch(e){start();}},1500);}
  else if(d.type==='mediaError'){try{hls.recoverMediaError();}catch(e){start();}}
  else{setTimeout(start,2500);}});
}
function start(){
 if(native){V.src=HLSURL;V.play().catch(function(){});return;}
 if(window.Hls){attach();}
 else{var s=document.createElement('script');s.src='/hls.js';s.onload=attach;s.onerror=function(){setTimeout(start,3000);};document.head.appendChild(s);}
}
start();
function resync(){if(native){V.load();V.play().catch(function(){});}else if(hls){try{hls.startLoad();}catch(e){start();}V.play().catch(function(){});}else{start();}up();}
V.addEventListener('stalled',function(){setTimeout(resync,1200);});
V.addEventListener('error',function(){setTimeout(start,2000);});
document.addEventListener('visibilitychange',function(){if(!document.hidden)resync();});
window.addEventListener('focus',resync);
window.addEventListener('online',resync);
window.addEventListener('pageshow',function(e){if(e.persisted)resync();});
</script>
<script type="x-shader/x-fragment" id="frag">""" + FRAG + """</script>
<script>""" + BG_JS + """</script>
</body></html>""").encode()


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            last_seq = -1
            try:
                while True:
                    s = _latest["seq"]
                    j = _latest["jpg"]
                    if j is not None and s != last_seq:
                        last_seq = s
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(j)).encode() + b"\r\n\r\n" + j + b"\r\n")
                        self.wfile.flush()
                    else:
                        time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
        elif self.path.startswith("/seq"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                self.wfile.write(str(_latest["seq"]).encode())
            except OSError:
                pass
        elif self.path.startswith("/hls.js"):
            try:
                data = open(os.path.join(HERE, "hls.min.js"), "rb").read()
            except OSError:
                self.send_response(404); self.end_headers(); return
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            try:
                self.wfile.write(data)
            except OSError:
                pass
        elif self.path.startswith("/hls/"):
            name = self.path.split("?")[0].split("/")[-1]
            p = os.path.join(HERE, "hls", name)
            if not re.match(r"^[\w.\-]+$", name) or not os.path.exists(p):
                self.send_response(404); self.end_headers(); return
            try:
                data = open(p, "rb").read()
            except OSError:
                self.send_response(404); self.end_headers(); return
            self.send_response(200)
            self.send_header("Content-Type",
                             "application/vnd.apple.mpegurl" if name.endswith(".m3u8") else "video/mp2t")
            self.send_header("Cache-Control", "no-cache" if name.endswith(".m3u8") else "max-age=15")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(data)
            except OSError:
                pass
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
