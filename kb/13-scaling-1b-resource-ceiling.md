# Scaling T2 to 1B — the Resource Ceiling

The T2 Conscripts campaign reached **500M** cleanly (final 501,481,135). Pushing on to **1B**
was requested and started, then paused: the bot works fine, but **food inventory runs out
long before 1B**. This doc records the math so the next attempt is planned, not surprised.

## Per-batch cost (T2 Conscripts, this account)

| | value |
|---|---|
| Troops per batch (`TRAIN_QTY`) | 271,766 |
| Food per batch | ~59,000,000 |
| Stone per batch | ~10,800,000 |
| Natural timer (Finish-All'd with items) | ~2d 16h |

## 500M → 1B budget

```
need  = 1,000,000,000 − 501,481,135 = 498,518,865 troops
batches = 498.5M / 271,766           ≈ 1,834
food  = 1,834 × 59M                  ≈ 108.2 B
stone = 1,834 × 10.8M                ≈  19.8 B
```

## What we actually have (binding constraint = FOOD)

| Resource | Stock | Covers | Troop headroom |
|----------|-------|--------|----------------|
| **1M Food** items (bot uses these) | ~8,065 (~8.1B) + ~1.3B top-bar ≈ **9.4B** | ~159 batches | **+43M → ~544M** |
| 1M **Safe** Food items (bot does NOT use) | ~19,364 (~19.4B) — *spendable-on-training unverified* | +475 batches if usable | +132M → ~630M |
| Stone | ~30B | ~2,778 batches | +755M |
| Gems | ~8.19M | — | (Instant-Finish only; not a food source) |

Food is short by **~99B** (108B needed vs ~9.4B usable). Stone is comfortable. So the honest
ceiling with current inventory is **~544M** (1M Food only), or **~630M** if the Safe Food
stash turns out to be spendable on training. **1B is not reachable without acquiring ~100B
more food.**

## Refill cadence (empirical, from the 500M run)

- Food burns ~**2.8B per ~32–48 batches**; the bot opens ~**2B** (≈2,010 × 1M Food) per refill.
- Expect **one auto-refill every 1–2 monitor ticks** — that is normal, not a fault.
- The 500M run (300M→500M, +79.9M troops, 294 batches) used **8 refills, 0 failures**.
- When 1M-Food items are exhausted the refill will throw **REFILL FAIL** — that, not a crash,
  is the signal the food ceiling was hit.

## Paths to actually fund 1B (see kb/14 for researched detail)

1. **Restock food** before resuming — gather food tiles / farms / resource packs to bank
   ~100B, then run `--target 1000000000`.
2. **Settle for the current-stock ceiling** (~544M, or ~630M with Safe Food wired in).
3. **Reduce per-troop food cost** (training-cost research/buffs/subordinate-city bonuses), if
   available — lowers the 108B requirement.

## Status at pause

Bot stopped by user at **511,125,257** (44 batches into the 1B attempt). No monitor loop
running. Resume is a one-liner once food is restocked.
