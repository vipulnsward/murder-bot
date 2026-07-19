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

CSS = r"""
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{background:#070d18;color:#ece4cf;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
 line-height:1.5;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.serif{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
:root{--gold:#f0d27e;--gold2:#d8ad46;--ink:#f4eddc;--muted:#c3d0e3;--good:#8be0a6;--bad:#e2745e;
 --glass:rgba(14,26,48,.64);--glass2:rgba(18,32,58,.56);--line:rgba(230,197,104,.26)}
#core{position:fixed;inset:0;width:100vw;height:100vh;z-index:-2;display:block}
.scrim{position:fixed;inset:0;z-index:-1;pointer-events:none;
 background:radial-gradient(120% 90% at 50% 0%,rgba(4,8,16,.14) 22%,rgba(4,8,16,.62) 100%),
 linear-gradient(180deg,rgba(6,11,22,.44),rgba(6,11,22,.72))}
.top,.foot,.sect{text-shadow:0 1px 4px rgba(0,0,0,.75)}
.wrap{max-width:960px;margin:0 auto;padding:30px 20px 60px;position:relative;z-index:1}
.rise{opacity:0;transform:translateY(14px);animation:rise .7s cubic-bezier(.2,.7,.2,1) forwards;animation-delay:var(--d,0s)}
@keyframes rise{to{opacity:1;transform:none}}
.top{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.crest{width:58px;height:58px;border-radius:12px;object-fit:cover;border:1px solid var(--line);box-shadow:0 6px 22px rgba(0,0,0,.5)}
.ava{position:relative;width:64px;height:64px;flex:0 0 auto}
.portrait{width:64px;height:64px;border-radius:14px;object-fit:cover;border:1px solid rgba(230,197,104,.5);
 box-shadow:0 6px 22px rgba(0,0,0,.55)}
.crestbadge{position:absolute;right:-7px;bottom:-7px;width:30px;height:30px;border-radius:8px;object-fit:cover;
 border:1px solid var(--gold);box-shadow:0 2px 8px rgba(0,0,0,.6)}
.brand .name{font-size:1.5rem;font-weight:600;color:var(--gold);line-height:1.1;letter-spacing:.01em;
 text-shadow:0 2px 18px rgba(230,197,104,.35)}
.brand .sub{font-size:.72rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-top:3px}
.pill{font:600 .7rem/1 ui-monospace,Menlo,monospace;letter-spacing:.12em;padding:8px 13px;border-radius:999px;
 border:1px solid;backdrop-filter:blur(8px)}
.pill.run{color:var(--good);border-color:rgba(116,212,147,.45);background:rgba(116,212,147,.12)}
.pill.stop{color:var(--bad);border-color:rgba(226,116,94,.45);background:rgba(226,116,94,.12)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:currentColor;margin-right:7px;box-shadow:0 0 8px currentColor}
.pill.run .dot{animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.updated{margin-left:auto;color:var(--muted);font:500 .78rem/1 ui-monospace,monospace}
.empire{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
.chip{background:var(--glass);border:1px solid var(--line);border-radius:12px;padding:9px 15px;
 display:flex;flex-direction:column;gap:2px;min-width:78px;backdrop-filter:blur(10px)}
.chip .cv{font:600 1.02rem/1.1 ui-monospace,Menlo,monospace;color:var(--gold)}
.chip .cl{font-size:.6rem;letter-spacing:.11em;text-transform:uppercase;color:var(--muted)}
.hero{position:relative;overflow:hidden;border-radius:20px;border:1px solid var(--line);padding:30px 32px 26px;
 margin-bottom:16px;background:linear-gradient(180deg,var(--glass),var(--glass2));backdrop-filter:blur(16px) saturate(1.15);
 box-shadow:0 20px 60px rgba(0,0,0,.4);transition:transform .2s ease-out;will-change:transform}
.hero .bg{position:absolute;inset:0;background-size:cover;background-position:center 28%;opacity:.12;
 mask-image:linear-gradient(180deg,#000,transparent 85%)}
.hero .in{position:relative}
.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:.66rem;font-weight:600;color:var(--gold2);
 display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{color:#0a1322;background:linear-gradient(180deg,#f2d885,#d9b24e);border-radius:999px;padding:3px 10px;
 font-size:.6rem;letter-spacing:.06em;font-weight:700;box-shadow:0 2px 10px rgba(230,197,104,.4)}
.own{font-weight:600;font-size:clamp(2.6rem,8.5vw,4.4rem);line-height:1;color:var(--gold);
 font-variant-numeric:tabular-nums;margin:10px 0 4px;text-shadow:0 3px 26px rgba(230,197,104,.4)}
.own small{color:var(--muted);font-size:.3em;font-weight:500}
.subline{color:var(--muted);font-size:.92rem;margin-bottom:16px}
.subline b{color:var(--ink);font-variant-numeric:tabular-nums}
.track{height:14px;background:rgba(6,14,26,.7);border-radius:999px;overflow:hidden;border:1px solid var(--line);
 box-shadow:inset 0 2px 5px rgba(0,0,0,.5)}
.fill{height:100%;width:0;border-radius:999px;background:linear-gradient(90deg,var(--gold2),var(--gold),#fff2cf);
 box-shadow:0 0 16px rgba(230,197,104,.6);transition:width 1.4s cubic-bezier(.2,.7,.2,1)}
.pctrow{display:flex;justify-content:space-between;margin-top:10px;font:600 .8rem/1 ui-monospace,monospace;
 color:var(--muted);font-variant-numeric:tabular-nums}
.pctrow b{color:var(--gold)}
.tagline{margin-top:16px;padding-top:15px;border-top:1px solid var(--line);text-align:center;
 color:var(--gold2);letter-spacing:.15em;font-size:.7rem;text-transform:uppercase}
.warn{margin-top:14px;padding:11px 15px;border-radius:12px;font-size:.86rem;color:var(--gold);
 border:1px solid rgba(230,197,104,.4);background:rgba(230,197,104,.1)}
.cols{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;align-items:start}
@media(max-width:660px){.cols{grid-template-columns:1fr}}
.sect{font-size:.64rem;letter-spacing:.15em;text-transform:uppercase;color:var(--gold2);font-weight:600;
 margin:2px 2px 10px;display:flex;align-items:center;gap:7px}
.sect svg{width:14px;height:14px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.stat{background:var(--glass);border:1px solid var(--line);border-radius:14px;padding:15px 16px;
 display:flex;flex-direction:column;gap:4px;backdrop-filter:blur(10px);transition:transform .15s,border-color .15s}
.stat:hover{transform:translateY(-2px);border-color:rgba(230,197,104,.4)}
.stat .lbl{text-transform:uppercase;letter-spacing:.08em;font-size:.62rem;color:var(--muted);font-weight:600}
.stat .val{font:600 1.32rem/1.1 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;color:var(--ink)}
.stat .sub{font-size:.68rem;color:var(--muted)}
.shot{background:var(--glass);border:1px solid var(--line);border-radius:16px;padding:12px;
 display:flex;flex-direction:column;gap:9px;backdrop-filter:blur(10px)}
.shot img{width:100%;border-radius:11px;display:block;border:1px solid var(--line)}
.shot .cap{text-align:center;font-size:.66rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase}
.noimg{color:var(--muted);text-align:center;padding:44px 0}
.foot{margin-top:24px;text-align:center;color:var(--muted);font-size:.72rem}
.foot b{color:var(--gold2)}
.road{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
@media(max-width:660px){.road{grid-template-columns:1fr}}
.phase{background:var(--glass);border:1px solid var(--line);border-radius:14px;padding:15px 17px;
 backdrop-filter:blur(10px);position:relative;overflow:hidden}
.phase.active{border-color:rgba(230,197,104,.45);box-shadow:0 0 22px rgba(230,197,104,.12)}
.phase.active::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;
 background:linear-gradient(180deg,var(--gold),var(--gold2))}
.ph-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}
.ph-n{font:700 .9rem/1 ui-monospace,monospace;color:var(--gold2);letter-spacing:.05em}
.ph-st{font-size:.58rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700;color:var(--good);
 border:1px solid rgba(116,212,147,.4);background:rgba(116,212,147,.1);border-radius:999px;padding:2px 9px}
.ph-st.queued{color:var(--muted);border-color:var(--line);background:rgba(159,178,205,.08)}
.ph-name{font:600 1.02rem/1.2 system-ui;color:var(--ink);margin-bottom:9px}
.ph-bar{height:9px;background:rgba(6,14,26,.7);border-radius:999px;overflow:hidden;border:1px solid var(--line)}
.ph-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--gold2),var(--gold));
 box-shadow:0 0 10px rgba(230,197,104,.5)}
.ph-sub{font:600 .68rem/1.3 ui-monospace,monospace;color:var(--muted);margin-top:8px;font-variant-numeric:tabular-nums}
@media(prefers-reduced-motion:reduce){.rise{animation:none;opacity:1;transform:none}.pill.run .dot{animation:none}
 .fill{transition:none}.hero{transition:none}}
"""

FRAG = r"""precision highp float;
uniform vec2 R; uniform float T; uniform float M; uniform float PIX; uniform vec2 MO;
float hash(vec2 p){p=fract(p*vec2(123.34,345.45));p+=dot(p,p+34.345);return fract(p.x*p.y);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 float a=hash(i),b=hash(i+vec2(1.,0.)),c=hash(i+vec2(0.,1.)),d=hash(i+vec2(1.,1.));
 return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}
float fbm(vec2 p){float s=0.,a=.5;for(int i=0;i<5;i++){s+=a*noise(p);p=p*2.02+vec2(1.7);a*=.5;}return s;}
mat3 rotY(float a){float c=cos(a),s=sin(a);return mat3(c,0.,s,0.,1.,0.,-s,0.,c);}
mat3 rotX(float a){float c=cos(a),s=sin(a);return mat3(1.,0.,0.,0.,c,-s,0.,s,c);}
void main(){
 vec2 fc=gl_FragCoord.xy;
 if(PIX>1.5){fc=(floor(fc/PIX)+0.5)*PIX;}
 vec2 uv=(fc-0.5*R)/R.y;
 float t=T*M;
 vec3 navy=vec3(0.03,0.065,0.13), navy2=vec3(0.013,0.028,0.065);
 vec3 gold=vec3(0.86,0.70,0.36), gold2=vec3(1.0,0.86,0.55);
 vec2 q=uv*1.5+MO*0.15;
 float n=fbm(q+vec2(t*0.03,-t*0.02));
 n=fbm(q+n*1.4+vec2(0.0,t*0.02));
 vec3 col=mix(navy2,navy,smoothstep(0.15,0.95,n));
 col+=gold*pow(max(n-0.55,0.0),2.0)*0.55;
 col*=1.0-0.5*dot(uv,uv);
 vec3 ro=vec3(0.0,0.0,3.2);
 vec3 rd=normalize(vec3(uv+MO*0.05,-1.6));
 mat3 rot=rotY(t*0.22)*rotX(0.5+sin(t*0.13)*0.14);
 float rad=1.12;
 float b=dot(ro,rd), c2=dot(ro,ro)-rad*rad, h=b*b-c2;
 if(h>0.0){
  h=sqrt(h); float tH=-b-h; vec3 p=ro+rd*tH; vec3 nr=normalize(p); vec3 pl=rot*p;
  float e=fbm(pl.xy*2.1+pl.z*1.2+vec2(t*0.18)); e+=0.5*fbm(pl.yz*3.6-vec2(t*0.14));
  float fres=pow(1.0-max(dot(nr,-rd),0.0),2.4);
  float lat=abs(fract(pl.y*6.0)-0.5);
  float lon=abs(fract((atan(pl.x,pl.z)/6.2831+0.5)*18.0)-0.5);
  float grid=smoothstep(0.055,0.0,min(lat,lon))*0.55;
  vec3 core=mix(gold*0.22,gold2,clamp(e,0.,1.));
  core+=gold2*fres*1.35; core+=gold2*grid; core*=0.55+0.65*e;
  core*=0.85+0.22*sin(t*1.1);
  col=mix(col,core,clamp(0.28+0.85*e+fres,0.0,1.0));
 }
 float d=length(uv);
 col+=gold*smoothstep(1.25,0.0,d)*0.05;
 vec2 dp=uv*3.0;
 for(int i=0;i<3;i++){float fi=float(i);
  vec2 g=fract(dp*(1.0+fi*0.7)+vec2(t*(0.05+fi*0.03),t*0.02))-0.5;
  col+=gold2*smoothstep(0.03,0.0,length(g))*0.28; dp*=1.7;}
 col=pow(max(col,0.0),vec3(0.88));
 gl_FragColor=vec4(col,1.0);
}"""

JS = r"""(function(){
 var D=window.DATA||{};
 var cvs=document.getElementById('core');
 var reduce=matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches;
 var gl=null; try{gl=cvs.getContext('webgl')||cvs.getContext('experimental-webgl');}catch(e){}
 var frag=document.getElementById('frag').textContent;
 var vert='attribute vec2 p;void main(){gl_Position=vec4(p,0.0,1.0);}';
 var prog,uR,uT,uM,uPIX,uMO,scale=0.62,mo=[0,0],moT=[0,0],start=null,pixStart=null;
 function sh(t,s){var o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
  if(!gl.getShaderParameter(o,gl.COMPILE_STATUS)){console.warn(gl.getShaderInfoLog(o));return null;}return o;}
 function resize(){var w=Math.max(2,Math.floor(innerWidth*scale)),h=Math.max(2,Math.floor(innerHeight*scale));
  cvs.width=w;cvs.height=h;gl.viewport(0,0,w,h);}
 function init(){if(!gl)return false;var vs=sh(gl.VERTEX_SHADER,vert),fs=sh(gl.FRAGMENT_SHADER,frag);
  if(!vs||!fs)return false;prog=gl.createProgram();gl.attachShader(prog,vs);gl.attachShader(prog,fs);gl.linkProgram(prog);
  if(!gl.getProgramParameter(prog,gl.LINK_STATUS)){console.warn(gl.getProgramInfoLog(prog));return false;}
  gl.useProgram(prog);var buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);
  var loc=gl.getAttribLocation(prog,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
  uR=gl.getUniformLocation(prog,'R');uT=gl.getUniformLocation(prog,'T');uM=gl.getUniformLocation(prog,'M');
  uPIX=gl.getUniformLocation(prog,'PIX');uMO=gl.getUniformLocation(prog,'MO');resize();return true;}
 function pixNow(ts){if(reduce)return 1;if(pixStart===null)pixStart=ts;
  var k=Math.min((ts-pixStart)/1300,1);k=1-Math.pow(1-k,3);return 1+46*(1-k);}
 function frame(ts){if(start===null)start=ts;var tsec=(ts-start)/1000;
  moT[0]+=(mo[0]-moT[0])*0.05;moT[1]+=(mo[1]-moT[1])*0.05;
  gl.uniform2f(uR,cvs.width,cvs.height);gl.uniform1f(uT,tsec);gl.uniform1f(uM,reduce?0:1);
  gl.uniform1f(uPIX,pixNow(ts)*scale);gl.uniform2f(uMO,moT[0],moT[1]);
  gl.drawArrays(gl.TRIANGLES,0,3);requestAnimationFrame(frame);}
 if(init()){addEventListener('resize',resize);
  addEventListener('pointermove',function(e){mo[0]=(e.clientX/innerWidth-0.5)*2;mo[1]=-(e.clientY/innerHeight-0.5)*2;});
  requestAnimationFrame(frame);}
 else{cvs.style.display='none';
  document.body.style.background='radial-gradient(1000px 600px at 50% -10%,rgba(230,197,104,.12),transparent 60%),#070d18';}
 function fmt(n){return Math.round(n).toLocaleString('en-US');}
 function countUp(el,from,to,dur){if(!el)return;if(reduce){el.textContent=fmt(to);return;}var s=null;
  function step(ts){if(s===null)s=ts;var k=Math.min((ts-s)/dur,1);k=1-Math.pow(1-k,3);
   el.textContent=fmt(from+(to-from)*k);if(k<1)requestAnimationFrame(step);}requestAnimationFrame(step);}
 var ov=document.getElementById('ownval');if(ov)countUp(ov,+ov.dataset.start,+ov.dataset.end,1600);
 var tg=document.getElementById('togo');if(tg){var te=+tg.dataset.end;countUp(tg,te*1.03,te,1400);}
 var pv=document.getElementById('pctv');if(pv){var pe=+pv.dataset.end;if(reduce){pv.textContent=pe.toFixed(1)+'%';}
  else{var s2=null;(function pstep(){requestAnimationFrame(function(ts){if(s2===null)s2=ts;
   var k=Math.min((ts-s2)/1400,1);k=1-Math.pow(1-k,3);pv.textContent=(pe*k).toFixed(1)+'%';if(k<1)pstep();});})();}}
 var fl=document.getElementById('fill');if(fl){var pct=(D.pct||0);
  setTimeout(function(){fl.style.width=(reduce?pct:pct).toFixed(2)+'%';},reduce?0:160);}
 var hero=document.getElementById('hero');
 if(hero&&!reduce){addEventListener('pointermove',function(e){
  var rx=(e.clientY/innerHeight-0.5)*-4,ry=(e.clientX/innerWidth-0.5)*4;
  hero.style.transform='perspective(1000px) rotateX('+rx+'deg) rotateY('+ry+'deg)';});}
})();"""

ICON_ROAD = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round"><path d="M4 22V4l1-1h9l-1 4 1 3H5"/>'
             '<circle cx="12" cy="15" r="6"/><circle cx="12" cy="15" r="2"/></svg>')
ICON_SWORDS = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 17.5 3 6V3h3l11.5 11.5"/>'
               '<path d="m13 19 6-6"/><path d="m16 16 4 4"/><path d="M19 21l2-2"/>'
               '<path d="M9.5 17.5 21 6V3h-3L6.5 14.5"/><path d="m5 14 4 4"/><path d="M5 19l-2-2"/></svg>')
ICON_FEED = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="15" rx="2"/>'
             '<path d="m10 9 5 3-5 3z" fill="currentColor"/><path d="M8 21h8"/></svg>')


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
    import json
    log = newest_log()
    own, batches, rate = read_stats(log) if log else (None, 0, None)
    running = subprocess.run(["pgrep", "-f", "train_to_1b.py"],
                             capture_output=True).returncode == 0
    food = read_food()
    own = own or 0
    to_go = max(TARGET - own, 0)
    pct = (own / TARGET * 100) if own else 0
    eta_h = (to_go / rate / 60) if (to_go and rate) else None
    food_batches = int(food / 43_500_000) if food else None
    sess = (own - SESSION_START) if own else 0
    now = datetime.datetime.now().strftime("%b %d · %H:%M:%S")
    crest, banner, shot = asset("crest_b64.txt"), asset("banner_b64.txt"), shot_b64()
    state = "TRAINING" if running else "PAUSED"
    scls = "run" if running else "stop"
    warn = food is not None and food < 600_000_000
    past1b = own >= 1_000_000_000
    P = PROFILE
    trained_run = batches * QTY
    start_own = max(own - trained_run, int(own * 0.985))

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
        stat("Trained this run", f"+{trained_run/1e6:.1f}M"),
        stat("Trained this session", f"+{sess/1e6:.1f}M", "since 685.7M"),
        stat("Rate", (human(rate) + "/min") if rate else "—", f"{3600/(rate/QTY):.1f}s / batch" if rate else ""),
        stat("Food reserve", human(food), f"~{food_batches} batches" if food_batches else ""),
        stat("ETA to 1.5B", f"{eta_h:.1f} h" if eta_h else "—", "at current pace"),
    ])
    shot_html = (f'<img alt="Live game" src="{shot}">' if shot
                 else '<div class="noimg">screenshot unavailable</div>')
    warn_html = ('<div class="warn">⚠ Food reserve under 600M — an automated resupply is due shortly.</div>'
                 if warn else "")
    badge = ('<span class="badge">★ 1B reached</span>' if past1b else "")
    mon = asset("avatar_b64.txt")
    if mon:
        avatar = (f'<div class="ava"><img class="portrait" alt="Monarch" src="{mon}">'
                  + (f'<img class="crestbadge" alt="NFG" src="{crest}">' if crest else "")
                  + '</div>')
    else:
        avatar = (f'<img class="crest" alt="NFG crest" src="{crest}">' if crest
                  else '<div class="crest"></div>')

    p1 = min(own / 1_500_000_000 * 100, 100) if own else 0
    roadmap = f"""
 <div class="sect">{ICON_ROAD} Campaign Roadmap</div>
 <div class="road rise" style="--d:.14s">
  <div class="phase active">
   <div class="ph-top"><span class="ph-n">01</span><span class="ph-st">In progress</span></div>
   <div class="ph-name">T1 Warriors → 1.5B</div>
   <div class="ph-bar"><div class="ph-fill" style="width:{p1:.1f}%"></div></div>
   <div class="ph-sub">{own:,} / 1,500,000,000 · {p1:.1f}%</div>
  </div>
  <div class="phase">
   <div class="ph-top"><span class="ph-n">02</span><span class="ph-st queued">Queued</span></div>
   <div class="ph-name">T2 Ground → 1B</div>
   <div class="ph-bar"><div class="ph-fill" style="width:0%"></div></div>
   <div class="ph-sub">0 / 1,000,000,000 · begins after Phase 01</div>
  </div>
 </div>"""

    data = json.dumps({
        "own": own, "startOwn": start_own, "target": TARGET, "pct": round(pct, 2),
        "toGo": to_go, "qty": QTY,
    })

    body = f"""<canvas id="core"></canvas><div class="scrim"></div>
<div class="wrap">
 <div class="top rise" style="--d:0s">
  {avatar}
  <div class="brand">
   <div class="name serif">{P['name']}</div>
   <div class="sub">[{P['alliance']}] · Server {P['server']} · {P['troop']}</div>
  </div>
  <div class="pill {scls}"><span class="dot"></span>{state}</div>
  <div class="updated">{now}</div>
 </div>

 <div class="empire rise" style="--d:.06s">{empire}</div>

 <div class="hero rise" style="--d:.12s" id="hero">
  <div class="bg" style="background-image:url('{banner}')"></div>
  <div class="in">
   <div class="eyebrow">T1 Warriors mustered · goal 1,500,000,000 {badge}</div>
   <div class="own"><span id="ownval" data-start="{start_own}" data-end="{own}">{own:,}</span><small> / 1.5B</small></div>
   <div class="subline"><b id="togo" data-end="{to_go}">{to_go:,}</b> to go · <b>{(to_go//QTY) if to_go else 0:,}</b> batches remaining</div>
   <div class="track"><div class="fill" id="fill" style="--pct:{pct:.2f}"></div></div>
   <div class="pctrow"><span><b id="pctv" data-end="{pct:.1f}">{pct:.1f}%</b> to goal</span><span>{(human(rate)+" / min") if rate else ""}</span></div>
   {warn_html}
   <div class="tagline">Together we build · Together we conquer</div>
  </div>
 </div>

{roadmap}

 <div class="cols rise" style="--d:.18s">
  <div>
   <div class="sect">{ICON_SWORDS} Training Session</div>
   <div class="grid">{session}</div>
  </div>
  <div class="shot">
   <div class="sect" style="margin-bottom:2px">{ICON_FEED} Live Feed</div>
   {shot_html}
   <div class="cap">BlueStacks · real-time</div>
  </div>
 </div>

 <div class="foot rise" style="--d:.24s"><b>NFG</b> Vision Bot · ADB + OpenCV + Tesseract · auto-refreshed each minute</div>
</div>
"""

    html = ("<title>NFG · NEO — Empire Core</title>\n<style>\n" + CSS + "\n</style>\n"
            + body
            + '\n<script type="x-shader/x-fragment" id="frag">\n' + FRAG + '\n</script>\n'
            + "<script>window.DATA=" + data + ";</script>\n"
            + "<script>\n" + JS + "\n</script>\n")
    for uni, ent in [("·", "&middot;"), ("→", "&rarr;"), ("—", "&mdash;"),
                     ("…", "&hellip;"), ("⚠", "&#9888;"), ("★", "&#9733;")]:
        html = html.replace(uni, ent)
    with open(os.path.join(HERE, "evony_status.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote evony_status.html | own={own} batches={batches} food={human(food)} running={running}")


if __name__ == "__main__":
    main()
