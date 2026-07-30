# Murder Bot — Cost Model & Break-Even

Goal: turn the manager into a real product that earns back a **~$1,000/mo Hetzner
budget within ~6 months** via subscriptions (`billing_view.py`).

> **All money numbers below are produced by the arithmetic in this file and were
> verified with a script — every derived figure is shown with its formula so it
> can be re-checked.** Hetzner list prices are *approximate, ex-VAT* and should
> be re-confirmed at <https://www.hetzner.com/cloud/> before committing spend.

---

## 1. Hetzner CAX (Arm64 / Ampere) pricing

Shared-vCPU Arm64 line, monthly, ex-VAT, 20 TB traffic included. Converted at
**EUR→USD = 1.08** (state your real rate at purchase time).

| Plan  | vCPU | RAM   | NVMe   | EUR/mo | USD/mo |
|-------|-----:|------:|-------:|-------:|-------:|
| CAX11 |    2 |  4 GB |  40 GB | €3.79  | $4.09  |
| CAX21 |    4 |  8 GB |  80 GB | €6.49  | $7.01  |
| CAX31 |    8 | 16 GB | 160 GB | €12.49 | $13.49 |
| CAX41 |   16 | 32 GB | 320 GB | €24.49 | $26.45 |

The project brief anchors on "CAX11 ~€4/mo" and a mid VM "~€13/mo" — those map to
**CAX11 ($4.09)** and **CAX31 ($13.49)** in the current ladder. Either way the
per-VM cost is €4–€13 / $4–$14 a month, which is the order of magnitude this
model uses.

**Optional GPU.** Hetzner Cloud has *no* GPU instances. The bot renders an
Android client (Redroid) in software, so it does not need one. If OCR/vision ever
needs a GPU, it means renting a dedicated GPU box (Hetzner dedicated **GEX44 /
RTX 4000**, ~€184/mo ≈ $199/mo) or a cloud GPU elsewhere — that is a *separate*
line item, ~15–20% of the whole $1K budget for a single card, and is **out of
scope** for the break-even below. Keep vision on CPU until proven otherwise.

---

## 2. Per-account infrastructure footprint

The heavy component is **one Redroid Android instance per Evony account** (each
runs a full game client: ~2 GB RAM + ~1.5 vCPU under load). Everything else
(manager, Postgres, Caddy) is shared.

**Assumptions (the model's dials):**

| Dial | Value | Note |
|------|------:|------|
| Control-plane VM (manager + Postgres + Caddy) | CAX21 = **$7.01/mo** | fixed, shared |
| Worker VM (Redroid + bot) | CAX31 = **$13.49/mo** | scales with accounts |
| **Accounts per worker VM** | **4** | key sensitivity — see §6 |
| Ops overhead (backups, bandwidth overage, snapshots, monitoring) | **+15%** | on infra |
| Payment processing (Razorpay) | **3%** | of gross revenue |

```
per-account infra = worker VM / accounts-per-VM = $13.49 / 4 = $3.37 /account/mo
```

### What does $1,000/mo of pure infra buy?

```
worker budget = ($1,000 − $7.01 control plane) / 1.15 overhead = $863.5
worker VMs    = $863.5 / $13.49                                ≈ 64 VMs
accounts      = 64 × 4                                          ≈ 256 accounts
```

**$1,000/mo runs ~256 automated accounts (~64 CAX31 VMs).** The binding
constraint is therefore **not** infrastructure — it is finding the **~50–70
paying users** (§4) needed to cover that spend. Compute is cheap; distribution
is the hard part.

---

## 3. Subscription plans → unit economics

Plans as defined in `billing_view.py`:

| Plan     | Price   | What they get                                   |
|----------|--------:|-------------------------------------------------|
| Free     | $0      | View-only: roster + map, 1 account, no bot      |
| Pro      | $19/mo  | Full bot + AI counter + reports, 1 account      |
| Alliance | $49/mo  | Multi-account (≤10) + intel on everyone         |

Margin per paying user (net of 3% fees and 15%-loaded infra):

```
Pro      : $19 × 0.97 = $18.43 net − ($3.37 × 1 × 1.15 = $3.88) infra  = $14.55 /mo
Alliance : $49 × 0.97 = $47.53 net − ($3.37 × 4 × 1.15 = $15.51) infra = $32.02 /mo
           (Alliance modeled at 4 concurrently-run accounts, not the 10 cap)
```

| Plan     | Gross | Net (−3%) | Infra (loaded) | **Contribution margin** |
|----------|------:|----------:|---------------:|------------------------:|
| Pro      | $19   | $18.43    | $3.88          | **$14.55/mo**           |
| Alliance | $49   | $47.53    | $15.51         | **$32.02/mo**           |

---

## 4. Break-even: users needed to earn back $1,000/mo

"Earn back the budget" = generate **$1,000/mo of contribution margin**.

```
users = $1,000 / margin-per-user
```

| Mix                        | Blended margin/user | **Users for $1,000/mo** |
|----------------------------|--------------------:|------------------------:|
| 100% Pro                   | $14.55              | **69**  (68.7)          |
| 100% Alliance              | $32.02              | **32**  (31.2)          |
| 80% Pro / 20% Alliance     | $18.04              | **56**  (55.4)          |
| 70% Pro / 30% Alliance     | $19.79              | **51**  (50.5)          |
| 50% Pro / 50% Alliance     | $23.28              | **43**  (42.9)          |

**Headline: ~56 subscribers (80/20 Pro-heavy mix) cover the $1,000/mo budget.**
That is ~22% of the ~256 accounts the same $1,000 could host — comfortable
headroom.

---

## 5. Six-month payback math

Cumulative budget over the ramp = **$1,000 × 6 = $6,000**. Two framings:

**(a) Flat — hit break-even in month 1 and hold.** 56 blended subs from day one:

```
56 users × $18.04/mo × 6 months = $6,063  ≥  $6,000   ✅ paid back at month 6
```

**(b) Realistic linear ramp — grow 0 → N over the 6 months** (average headcount
= N/2):

```
cumulative margin = 6 × (N/2) × $18.04 = 3N × $18.04
set ≥ $6,000  →  N = 2,000 / $18.04 ≈ 111 users by month 6
check: 3 × 111 × $18.04 = $6,009  ≥  $6,000   ✅
```

So under a from-zero ramp you need to **reach ~111 blended subscribers (or ~68
Alliance-only) by month 6** to recoup the cumulative $6,000; the *steady-state*
run-rate only needs ~56. Growing faster early (or an Alliance-heavier mix) pulls
payback in.

**Take-away:** the target is roughly **50–110 paying users in the first two
quarters** — a realistic goal for a niche Evony tool with an engaged alliance
audience, and well within the infra the budget already funds.

---

## 6. Sensitivity — accounts per worker VM (the biggest unknown)

Redroid density is the number most likely to be wrong. If each VM hosts fewer
accounts, per-account infra rises and break-even user count with it:

| Accounts/VM | Per-acct infra | Pro margin | Alliance margin | Blended 80/20 | Users for $1k/mo |
|------------:|---------------:|-----------:|----------------:|--------------:|-----------------:|
| 2 (safe)    | $6.74          | $10.67     | $16.50          | $11.84        | **85**           |
| 4 (base)    | $3.37          | $14.55     | $32.02          | $18.04        | **56**           |
| 6 (dense)   | $2.25          | $15.84     | $37.19          | $20.11        | **50**           |

Even in the pessimistic 2-per-VM case, **85 subscribers** cover the budget — the
model is not fragile to this dial. **Benchmark real Redroid density on a CAX31
before scaling** and update this row.

---

## 7. Risk flags — READ BEFORE CHARGING MONEY

These are material and are stated honestly rather than buried.

### 7.1 Terms-of-Service / ban risk (highest)
- **Automating Evony almost certainly violates Top Games Inc.'s Terms of
  Service.** Game ToS broadly prohibit bots, automation, emulija/scripted input,
  and unauthorized access to game systems. Enforcement is by **account ban**, and
  can extend to linked accounts / devices / payment identities.
- Selling a paid automation service **productizes** that ToS violation. That
  raises exposure beyond a single hobby account: it can invite a
  **cease-and-desist or DMCA-style action** from the publisher, and reputational
  and takedown risk for the hosting (Hetzner AUP) and payment provider.
- **Customer harm:** subscribers can lose accounts they've spent real money on.
  This must be disclosed *before* purchase. The billing page already carries an
  automation-risk notice; keep it, and add an explicit acceptance checkbox and
  ToS/refund policy before going live.
- **Mitigations (reduce, do not eliminate, risk):** human-like pacing
  (`humanize.py`), conservative action rates, no exploit/dupe behavior, per-user
  opt-in, clear disclosure, and a kill switch. None of these make automation
  ToS-compliant — they only lower detection/harm.

### 7.2 Payment-compliance risk
- **Razorpay (and card networks) can freeze/withhold funds** for businesses whose
  activity violates a third party's ToS or their own prohibited-use policy.
  Game-botting can be read as "facilitating ToS-violating / potentially
  IP-infringing activity." Onboarding may be rejected or the account terminated
  with funds held.
- **Razorpay is India-first.** Selling primarily to non-India customers in USD
  may require the right entity/account type; confirm cross-border and USD
  settlement are permitted for your account before pricing in dollars. The code
  defaults `RAZORPAY_CURRENCY=USD` — verify your account supports it or switch to
  INR-equivalent pricing.
- **Chargebacks:** a banned customer may dispute the charge. Budget for
  chargeback fees and a written refund policy.
- **Tax/registration:** subscription revenue is taxable; cross-border digital
  services can trigger GST/VAT/sales-tax registration duties. Out of scope here
  but real.

### 7.3 Technical / cost risk
- **Redroid density is unproven at scale** — §6 is a planning estimate. A bad
  density number (or a heavier game update) can double per-account cost.
- **Bandwidth/traffic overages** beyond the 20 TB/VM allowance are not modeled
  precisely; the 15% overhead is a buffer, not a measurement.
- **Support load** for a flaky game-automation product is real opex the margins
  above do not include.

### 7.4 Billing-code safety (already enforced in `billing_view.py`)
- Razorpay calls are **sandbox-only by default**: a live key (`rzp_live_…`) is
  **refused** unless `BILLING_LIVE=1` is explicitly set. No live plans/orders/
  payments are created by this codebase.
- Webhooks are **HMAC-SHA256 signature-verified** against
  `RAZORPAY_WEBHOOK_SECRET`; unsigned/invalid requests are rejected (400).
- Missing keys → a clear "billing not configured" stub, no network call.

---

## 8. Bottom line

| Question | Answer |
|----------|--------|
| What does $1,000/mo buy? | ~64 CAX31 VMs ≈ **256 automated accounts** |
| Steady-state break-even | **~56 subscribers** (80/20 Pro/Alliance) — or 69 all-Pro / 32 all-Alliance |
| 6-month payback (ramp) | reach **~111 blended subs by month 6** to recoup the cumulative $6,000 |
| Binding constraint | **customer acquisition, not compute** |
| Biggest risk | **ToS/ban + payment-freeze** — automation likely violates Evony's ToS; disclose and accept before charging |

*Re-verify Hetzner prices, the EUR→USD rate, and — most importantly — real
Redroid accounts-per-VM density before spending against this model.*
