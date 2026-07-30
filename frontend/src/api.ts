// API base: same-origin by default; on Cloudflare Pages set VITE_API_BASE to the
// backend URL (e.g. https://murderbot.gg or the Hetzner box) at build time.
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export type CounterPlan = {
  action?: string;
  lead_type?: string | null;
  reasoning?: string;
  confidence?: number | null;
  expected_loss_pct?: number | null;
  counter_generals?: CounterGeneral[];
};

export type CounterRole = "attack" | "defense";

export type CounterGeneral = {
  general: string;
  counter_type: string;
  role?: string;
  tier: string | null;
  rank?: number | null;
  why: string;
};

export type CounterGeneralsResponse = {
  enemy: string;
  enemy_type?: string;
  counter_types?: string[];
  role?: CounterRole;
  recommendations?: CounterGeneral[];
  error?: string;
};

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export async function demoCounter(power: number, lead: string): Promise<CounterPlan> {
  return getJson(
    `${API_BASE}/api/demo-counter?power=${encodeURIComponent(power)}&lead=${encodeURIComponent(lead)}`
  );
}

export async function counterGenerals(
  enemy: string,
  role: CounterRole = "attack",
  top = 5
): Promise<CounterGeneralsResponse> {
  const params = new URLSearchParams({ enemy, role, top: String(top) });
  return getJson(`${API_BASE}/api/counter-generals?${params}`);
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
