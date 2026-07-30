import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardTitle, CardContent } from "@/components/ui/card";
import { demoCounter, auth, type CounterPlan } from "@/api";
import { Swords, Brain, Radar, Check, Minus } from "lucide-react";

const LEADS = ["SIEGE", "GROUND", "RANGED", "MOUNTED"];

function Crest() {
  return (
    <svg viewBox="0 0 120 120" className="mx-auto mb-3 h-24 w-24 drop-shadow-[0_6px_20px_rgba(230,195,92,.4)]" aria-hidden>
      <defs>
        <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f7dd8f" />
          <stop offset=".55" stopColor="#e6c35c" />
          <stop offset="1" stopColor="#b8902f" />
        </linearGradient>
      </defs>
      <g stroke="url(#cg)" strokeWidth="4" strokeLinecap="round" opacity=".88">
        <path d="M26 26 L84 84" /><path d="M94 26 L36 84" />
        <circle cx="26" cy="26" r="4" fill="url(#cg)" /><circle cx="94" cy="26" r="4" fill="url(#cg)" />
      </g>
      <path d="M60 16 L98 30 V58 C98 80 80 94 60 102 C40 94 22 80 22 58 V30 Z" fill="#140f08" stroke="url(#cg)" strokeWidth="4" />
      <path d="M60 34 C52 42 52 54 60 62 C68 54 68 42 60 34 Z" fill="url(#cg)" />
      <path d="M48 68 Q60 80 72 68 Q60 74 48 68 Z" fill="url(#cg)" />
    </svg>
  );
}

function Section({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section className="relative z-10 border-b border-gold/10 py-12">
      <div className="mx-auto w-[min(1000px,92vw)]">
        <div className="text-xs font-bold uppercase tracking-[0.16em] text-gold">{eyebrow}</div>
        <h2 className="mb-6 mt-1.5 font-display text-2xl font-extrabold text-gold-bright md:text-3xl">{title}</h2>
        {children}
      </div>
    </section>
  );
}

function BrainDemo() {
  const [power, setPower] = useState(60);
  const [lead, setLead] = useState("SIEGE");
  const [plan, setPlan] = useState<CounterPlan | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try { setPlan(await demoCounter(power, lead)); } catch { setPlan(null); }
    setLoading(false);
  };
  useEffect(() => { run(); /* auto-run on mount */ }, []); // eslint-disable-line

  return (
    <Card className="shadow-[inset_0_0_0_1px_rgba(230,195,92,.16),0_0_56px_-16px_rgba(230,195,92,.3)] before:hidden">
      <div className="relative z-10 flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-[130px] text-sm text-muted-foreground">
          Incoming power (M)
          <input type="number" min={1} max={5000} value={power}
            onChange={(e) => setPower(Number(e.target.value))}
            className="mt-1.5 w-full rounded-lg border border-gold/25 bg-[rgba(8,6,4,.7)] px-3 py-2.5 text-foreground" />
        </label>
        <label className="flex-1 min-w-[130px] text-sm text-muted-foreground">
          Their lead
          <select value={lead} onChange={(e) => setLead(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-gold/25 bg-[rgba(8,6,4,.7)] px-3 py-2.5 text-foreground">
            {LEADS.map((l) => <option key={l}>{l}</option>)}
          </select>
        </label>
        <Button onClick={run} disabled={loading}>{loading ? "Running…" : "Counter it →"}</Button>
      </div>
      <div className="relative z-10 mt-4 min-h-[48px] rounded-xl border border-gold/20 bg-[rgba(8,6,4,.72)] p-4">
        {plan ? (
          <>
            <div className="text-xl font-extrabold uppercase tracking-wide text-gold-bright drop-shadow-[0_0_22px_rgba(230,195,92,.45)]">
              {plan.action ?? "—"}{plan.lead_type ? ` · counter-lead ${plan.lead_type}` : ""}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">{plan.reasoning}</div>
            {plan.confidence != null && (
              <div className="mt-2 font-bold text-gold">{Math.round(plan.confidence * 100)}% confidence</div>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">Set an attack and hit <b>Counter it</b>.</span>
        )}
      </div>
    </Card>
  );
}

const CMP: [string, boolean | string, boolean | string][] = [
  ["Price / user / mo", "$8", "from $5"],
  ["Auto rally-join, farm, stamina", true, true],
  ["Battle-report parsing", true, true],
  ["AI counter engine (sim-backed)", false, true],
  ["Enemy intel database", false, true],
  ["Attack / favorable-trade planner", false, true],
  ["Learns the meta 24/7", false, true],
];

function Cell({ v, us }: { v: boolean | string; us?: boolean }) {
  if (typeof v === "string") return <span className={us ? "font-bold text-gold-bright" : ""}>{v}</span>;
  return v ? <Check className="mx-auto h-4 w-4 text-emerald-400" /> : <Minus className="mx-auto h-4 w-4 text-muted-foreground/50" />;
}

function AuthForm() {
  const [msg, setMsg] = useState("");
  const submit = async (path: "signup" | "login", e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const { ok, data } = await auth(path, String(f.get("email")), String(f.get("password")));
    if (ok) location.href = "/home";
    else setMsg((data as any)?.detail || "Request failed");
  };
  const field = "mt-1.5 w-full rounded-lg border border-gold/25 bg-[rgba(8,6,4,.7)] px-3 py-2.5 text-foreground";
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 max-w-2xl">
        <Card>
          <CardTitle className="mb-3 text-lg">Create account</CardTitle>
          <form onSubmit={(e) => submit("signup", e)} className="relative z-10 grid gap-2.5">
            <label className="text-sm text-muted-foreground">Email<input name="email" type="email" required className={field} /></label>
            <label className="text-sm text-muted-foreground">Password<input name="password" type="password" minLength={8} required className={field} /></label>
            <Button type="submit" className="mt-1">Start free →</Button>
          </form>
        </Card>
        <Card>
          <CardTitle className="mb-3 text-lg">Log in</CardTitle>
          <form onSubmit={(e) => submit("login", e)} className="relative z-10 grid gap-2.5">
            <label className="text-sm text-muted-foreground">Email<input name="email" type="email" required className={field} /></label>
            <label className="text-sm text-muted-foreground">Password<input name="password" type="password" minLength={8} required className={field} /></label>
            <Button type="submit" variant="outline" className="mt-1">Log in</Button>
          </form>
        </Card>
      </div>
      {msg && <p className="mt-3 text-sm text-ember">{msg}</p>}
    </>
  );
}

export default function App() {
  return (
    <div>
      <header className="relative z-10 border-b border-gold/20 py-16 text-center"
        style={{ background: "radial-gradient(1100px 480px at 12% -12%,rgba(230,195,92,.15),transparent 60%),radial-gradient(900px 400px at 100% -4%,rgba(192,57,43,.20),transparent 55%)" }}>
        <div className="mx-auto w-[min(1000px,92vw)]">
          <Crest />
          <span className="inline-flex items-center gap-2 rounded-full border border-gold/30 bg-[rgba(22,18,11,.8)] px-3 py-1.5 text-xs uppercase tracking-[0.12em] text-gold">
            <span className="h-1.5 w-1.5 animate-pulseGlow rounded-full bg-gold" /> Live · trusted by NFG
          </span>
          <h1 className="mx-auto mt-5 max-w-3xl font-display text-4xl font-extrabold text-gold-gradient md:text-6xl">
            The Evony bot that <span className="text-ember">thinks.</span>
          </h1>
          <p className="mx-auto mt-3.5 max-w-[60ch] text-lg text-muted-foreground">
            Everything Easy Bot does — auto-rally, farm, reports — <b className="text-foreground">cheaper</b>, plus a real
            battle-sim AI that tells you exactly how to counter every attacker.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Button size="lg" onClick={() => document.getElementById("start")?.scrollIntoView({ behavior: "smooth" })}>Start free →</Button>
            <Button size="lg" variant="outline" onClick={() => document.getElementById("demo")?.scrollIntoView({ behavior: "smooth" })}>See the brain counter</Button>
          </div>
        </div>
      </header>

      <Section eyebrow="Why switch" title="Automation, plus an intelligence Easy Bot doesn't have">
        <div className="grid gap-4 md:grid-cols-3">
          {[
            { i: <Swords className="h-5 w-5 text-gold" />, t: "Full automation", d: "Joins rallies every minute, tops stamina, farms, scans reports, auto-reclaims after a kickout. 24/7." },
            { i: <Brain className="h-5 w-5 text-gold" />, t: "AI PvP brain", d: "Paste an attack — a real battle sim + learned meta says defend / rally / ghost / bubble and the exact lead." },
            { i: <Radar className="h-5 w-5 text-gold" />, t: "Enemy intel + planner", d: "A live database on every player — troops, buffs, generals, W/L — and a planner that ranks favorable trades." },
          ].map((c) => (
            <Card key={c.t}>
              <div className="relative z-10 mb-2.5">{c.i}</div>
              <CardTitle>{c.t}</CardTitle>
              <CardContent className="mt-1.5">{c.d}</CardContent>
            </Card>
          ))}
        </div>
      </Section>

      <div id="demo">
        <Section eyebrow="Live demo · no signup" title="Watch the brain counter an attack">
          <p className="mb-5 max-w-[64ch] text-muted-foreground">The exact battle-sim AI that runs on your account — the thing Easy Bot can't do.</p>
          <BrainDemo />
        </Section>
      </div>

      <Section eyebrow="Murder Bot vs Easy Bot" title="Same automation. Lower price. A brain.">
        <div className="overflow-x-auto rounded-2xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground/70">
                <th className="p-3.5">Feature</th><th className="p-3.5 text-center">Easy Bot</th><th className="p-3.5 text-center">Murder Bot</th>
              </tr>
            </thead>
            <tbody>
              {CMP.map(([f, ez, us], i) => (
                <tr key={i} className="border-t border-border">
                  <td className="p-3.5">{f}</td>
                  <td className="p-3.5 text-center"><Cell v={ez} /></td>
                  <td className="p-3.5 text-center"><Cell v={us} us /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section eyebrow="Pricing" title="Cheaper than Easy Bot, at every tier">
        <div className="grid gap-4 md:grid-cols-3">
          {[
            { n: "Brain", p: "$5", hot: true, f: ["Unlimited AI counters", "Enemy intel", "Attack planner", "Works instantly"] },
            { n: "Auto", p: "$9", f: ["Everything in Brain", "24/7 account run", "Rally + farm + reports"] },
            { n: "Alliance", p: "$29", f: ["Up to 5 accounts", "Fleet dashboard", "Intel on everyone"] },
          ].map((t) => (
            <Card key={t.n} className={t.hot ? "border-gold/50 shadow-[0_0_0_1px_rgba(230,195,92,.5),0_0_44px_-8px_rgba(230,195,92,.3)]" : ""}>
              <div className={`relative z-10 text-xs uppercase tracking-wide ${t.hot ? "text-gold-bright" : "text-muted-foreground"}`}>{t.n}</div>
              <div className="relative z-10 mt-1 text-3xl font-extrabold text-gold-bright">{t.p}<span className="text-sm text-muted-foreground/70">/mo</span></div>
              <ul className="relative z-10 mt-3 space-y-1 text-[13px] text-muted-foreground">
                {t.f.map((x) => <li key={x} className="before:mr-1.5 before:text-ember before:content-['▸']">{x}</li>)}
              </ul>
            </Card>
          ))}
        </div>
      </Section>

      <div id="start">
        <Section eyebrow="Switching from Easy Bot?" title="Migrate in under a minute">
          <p className="mb-5 max-w-[64ch] text-muted-foreground">Create an account, connect your Evony login, and Murder Bot takes it from there. No downtime, no lock-in.</p>
          <AuthForm />
        </Section>
      </div>

      <footer className="relative z-10 py-9 text-center text-xs text-muted-foreground/60">
        Murder Bot · the Evony bot that thinks. Everything Easy Bot does, cheaper — plus a brain.
      </footer>
    </div>
  );
}
