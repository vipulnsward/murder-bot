# Vision Backend Decision — OCR + LLM for screen understanding & grounding

For robust screen understanding + click grounding (beyond brittle template matching), the answer
is a **layered stack**, not one model. Two research passes (local models + hosted APIs) + live
tests on our own Evony frames drove this.

## The task splits in two (this decides everything)

- **Screen ID = classification** — easy; OCR-of-the-text or any modern VLM nails it.
- **Click coordinate = visual grounding** — the hard part; most cheap chat VLMs are mediocre at
  it. Only grounding-tuned families (Qwen-VL, Gemini) or OCR-box lookup do it well.

## Layered design (cheap → expensive, most work stays cheap)

1. **Deterministic templates + FSM** (`screen_fsm.py`) — known screens, ~free, fastest. Hot path.
2. **OCR (PaddleOCR / RapidOCR — Baidu's models, local & free)** — the key add:
   - **Number reading** (troops/food/gems/timers) — better than Tesseract (which failed on the
     gem count).
   - **Screen classification by text** — "disconnected because someone login" → disconnect;
     "Finish All"/"Use" → speedup modal. Deterministic, local, reliable.
   - **Zoom-robust button grounding** — find the *text label* ("Use","Train") and tap its box.
     Text is readable at any camera zoom → sidesteps the template-scale fragility (kb/12) for
     text-labeled controls. This is the biggest single robustness win and needs no LLM.
3. **Vision-LLM fallback** — only for the long tail (novel/iconographic screens OCR+templates
   can't resolve). `llm_agent.py`, KB-grounded, code-enforced safety.

## Vision-LLM picks (tested / researched)

**Local (free, private) — validated live on our frames:**
- **`qwen2.5vl:7b` via Ollama** — the pick. Fast (~2–3s on this Mac), correctly IDs the
  **disconnect screen → stop** (llava:7b hallucinated it) and the speedup modal; shaky on the
  training screen. Good for classification + coarse grounding. `ollama pull qwen2.5vl:7b` (done).
- `llava:7b` — too weak; rejected (only the code safety-net kept it safe).
- Stronger if needed: Qwen2.5-VL-32B, or GUI-grounding specialists (Holo1.5-7B, OS-Atlas,
  UGround) — higher ScreenSpot accuracy, more RAM/latency.

**Hosted API (cheap, fast) — for a rarely-fired fallback, an API beats local:**
- **Gemini 2.5 Flash-Lite** — best cheap grounding: native point/box output (normalized 0–1000),
  ~$0.00005/screenshot, sub-second, **free tier** via AI Studio. **Default API pick.**
- **Qwen3-VL-Flash (DashScope) / Qwen2.5-VL (DeepInfra)** — highest grounding accuracy
  (~89% ScreenSpot-v2 mobile), even cheaper; drop-in backup if Gemini coords drift.
- **Skip Kimi/Moonshot for grounding** — understands screenshots but the hosted API doesn't
  return tap coordinates (open-weights Kimi-VL does keypoints, but not the API).
- GPT-4.1-nano / Claude Haiku — great classification, weak raw coordinates; Haiku is also priciest.

**Verdict:** at fallback volumes (~pennies/day even at 1k calls/day), a hosted API's latency +
zero-setup wins; go **fully local (qwen2.5vl)** only for offline/privacy or if the fallback
becomes a hot path. `llm_agent` supports both (`EVONY_LLM_PROVIDER=ollama|anthropic`; Gemini is a
~20-line add of an OpenAI-compatible/Google endpoint).

## Recommendation

Wire **OCR (RapidOCR/PaddleOCR)** in first — it removes most template fragility for text UIs and
improves every number read, locally and free. Keep **qwen2.5vl** as the local fallback, and add
**Gemini Flash-Lite (free tier)** as the cheap hosted fallback. Reserve the LLM for the long tail;
log its decisions (kb/20) so recurring cases become OCR rules/templates and LLM volume trends to ~0.

Sources: ScreenSpot/-v2/-Pro grounding benchmarks; Gemini/OpenAI/Anthropic/DashScope/Groq/Zhipu
pricing pages; Ollama library. (Full source list in the research transcripts.)
