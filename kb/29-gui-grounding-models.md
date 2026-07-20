# Local GUI-Grounding VLMs for the Evony Bot (Apple Silicon, 2026)

Screenshot + instruction → identify screen + output a **click coordinate**, run locally on M-series
Mac. **Bottom line: switch from `qwen2.5vl:7b` to `Holo1.5-7B`** — a Qwen2.5-VL-7B fine-tune, same
size/speed, ~2× grounding accuracy. Available as MLX today.

## The numbers (H Company's apples-to-apples table; Holo1.5 = Qwen2.5-VL fine-tuned)
| Model | ScreenSpot-v2 | ScreenSpot-Pro | Avg(6) |
|---|---|---|---|
| Holo1.5-72B | 94.41 | **63.25** | 80.54 |
| **Holo1.5-7B** | **93.31** | **57.94** | 77.32 |
| Holo1.5-3B | 91.66 | 51.49 | 72.81 |
| UI-TARS-1.5-7B | 94.00 | 39.0 indep / 61.6 self† | 70.45 |
| **Qwen2.5-VL-7B (current)** | 85.60 | **29.00** | 60.73 |

Same base model + same size + same speed, but Holo1.5-7B's dense-icon grounding (ScreenSpot-Pro
57.9) is ~2× Qwen2.5-VL-7B's (29.0). ScreenSpot-v2 (incl. mobile UI) is most representative for us.
† UI-TARS SS-Pro self-reports 61.6 but Holo's independent re-eval got 39.0 — disputed; also an
*action* model (heavier for pure "one coordinate"). Rows below UI-TARS (UGround/OS-Atlas/ShowUI/
SeeClick) are older/weaker — superseded by Holo1.5.

## Top picks
1. **Best accuracy (still fast) → Holo1.5-7B via MLX** (`mlx-community/holo1.5-7b-mlx`). Same
   ~2–3s as our current model, ~2× grounding. 72B is the ceiling (SS-Pro 63.25) but needs 64GB+.
2. **Fastest → Holo1.5-3B** (GGUF `SakaiSec/Holo1.5-3B-Q4_K_M-GGUF`, or convert to MLX) — SS-Pro
   51.5, still far above Qwen-7B. A/B alt: **`ollama pull qwen3-vl:4b`** (one-command, newer,
   grounding score unverified).
3. **Keep qwen2.5vl:7b? → Switch.** Not good enough for dense Evony buttons (SS-Pro 29 = half of
   Holo). Keep as fallback/sanity only.

## Run on Apple Silicon (MLX = cleanest/fastest for these)
```bash
pip install mlx-vlm
# one-shot:
python -m mlx_vlm.generate --model mlx-community/holo1.5-7b-mlx \
  --image evony.png --prompt "Point to the Train button; return its click coordinate." \
  --max-tokens 128 --temperature 0.0
# OpenAI-compatible server (point llm_agent at it):
python -m mlx_vlm.server --model mlx-community/holo1.5-7b-mlx    # :8080 /v1/chat/completions
```
- **Ollama** is easiest for the Qwen line (`qwen2.5vl:*`, `qwen3-vl:2b/4b/8b/30b/32b`; needs Ollama
  ≥0.7). **Holo1.5 has no official Ollama** — importing GGUF+mmproj via Modelfile is fiddly →
  **run Holo1.5 via MLX, not Ollama.**
- **Coordinate convention:** Holo returns a click point, community GGUF uses **normalized [0,1000]**
  (`px = x/1000 * width`) — confirm the exact prompt template + output space from the Holo1.5-7B
  card before wiring taps. Our `llm_agent` already scales coords + enforces safety, so swapping the
  endpoint is a small change.

## Action for the bot
Point `llm_agent` at an **MLX Holo1.5-7B server** (OpenAI-compatible) instead of Ollama qwen2.5vl;
keep qwen2.5vl as fallback. But note: **OCR (kb/21/22) handles most text-labeled buttons already**,
so the VLM is the long-tail fallback — Holo1.5 matters most for icon-only / dense screens.

Uncertainties: tok/s not benchmarked (tiers inferred, verify on the Mac); Qwen3-VL SS-Pro not
extractable from text sources (A/B test); UI-TARS SS-Pro disputed. Sources: HF cards Hcompany/
Holo1.5-{3B,7B}, Qwen/Qwen2.5-VL-7B, ByteDance UI-TARS-1.5-7B; ollama.com/library qwen2.5vl+qwen3-vl;
github Blaizzy/mlx-vlm; ScreenSpot-Pro repo.
