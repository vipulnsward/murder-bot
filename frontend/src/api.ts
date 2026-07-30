// API base: same-origin by default; on Cloudflare Pages set VITE_API_BASE to the
// backend URL (e.g. https://murderbot.gg or the Hetzner box) at build time.
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export type CounterPlan = {
  action?: string;
  lead_type?: string | null;
  reasoning?: string;
  confidence?: number | null;
  expected_loss_pct?: number | null;
};

export async function demoCounter(power: number, lead: string): Promise<CounterPlan> {
  const r = await fetch(
    `${API_BASE}/api/demo-counter?power=${encodeURIComponent(power)}&lead=${encodeURIComponent(lead)}`
  );
  return r.json();
}

export async function auth(path: "login" | "signup", email: string, password: string) {
  const r = await fetch(`${API_BASE}/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, data };
}
