# LLM-Assisted Orchestrator (hybrid vision control + self-improvement)

Template matching is fast but brittle — it breaks on camera zoom, banner overlays, and novel
screens (see kb/12, kb/19). The fix: a **hybrid** controller. The deterministic FSM handles the
fast, cheap hot path; a **vision LLM** handles the stuck/unknown path, grounded in this KB. The
LLM only fires when stuck, so it's cheap, and every decision is logged so successful recoveries
can be distilled back into templates/procedures — the bot **self-improves**.

## Shape

```
loop:
  frame = fast screenshot
  if disconnect screen -> STOP (never tap)          # deterministic guard
  run the most-due deterministic task (scheduler)   # hot path, ~free
  if stuck for N ticks and llm_fallback:
     act = llm_agent.decide(frame)  # vision LLM, KB-grounded, safety-enforced
     execute act (tap/swipe/back) ; log to llm_decisions.jsonl
```

- `llm_agent.py` — dependency-free (stdlib `urllib`) call to the Anthropic Messages API with the
  frame (down-scaled 540×960 to cut tokens) + a **KB-grounded system prompt**: the screen catalog,
  the goal, and the hard safety rules. Returns ONE structured action as JSON.
- `orchestrator.py` — `run(..., llm_fallback=True)` escalates to `llm_resolve()` after
  `stuck_threshold` unproductive ticks; executes the returned safe action; appends the decision to
  `llm_decisions.jsonl`.

## Safety model (defense in depth — this is the point)

The LLM is **never trusted blindly**. Safety is enforced in **code**, independent of the model:

1. **System prompt** tells it: never tap gem-spend controls (Finish All / Instant Finish / Spend N
   Gems / Buy); never tap Quit/Restart on the disconnect screen — return `stop`; when unsure, `stop`.
2. **`_enforce_safety()` code net** re-checks every response: a disconnect screen, or any gem word
   in the screen/reason, is forced to `action: stop` regardless of what the model said. Verified
   offline: a model reply of "tap Restart" or "tap Finish All" is converted to `stop` (0 taps).
3. Coordinates are returned in the 540×960 image space and **scaled back ×2** in code.

So the LLM can propose, but it can never make the bot spend gems or reclaim the account.

## Self-improvement loop

Every LLM decision + the state it resolved is appended to `llm_decisions.jsonl`. Offline, distill
recurring successful recoveries into the deterministic layer: capture the screen as a new template,
add a `screen_fsm` anchor + handler, or a new `Task`. The LLM handles the long tail; the cheap
deterministic layer absorbs whatever recurs — so LLM call volume (and cost) trends down over time.
This KB (`kb/*`) is both the LLM's grounding *and* where distilled learnings land.

## Status / blocker

Built and safety-verified offline (parser + `_enforce_safety` self-test PASS; orchestrator
self-test PASS with the escalation wired). **Live vision calls are blocked:** the environment's
`ANTHROPIC_API_KEY` has no credit balance ("credit balance is too low"). The API is reachable and
the models list (claude-sonnet-5, haiku-4-5, …) resolves — it just needs credits, or an alternate
provider. The call is ~20 lines of stdlib HTTP, so it's trivial to repoint at:
- an Anthropic key **with credits**,
- an **OpenAI-compatible** endpoint (change URL + headers + payload shape), or
- a **local vision model** (Ollama llava/Qwen-VL, LM Studio) via its OpenAI-compatible API — zero
  cost, fully local, matches the "run locally" goal. Recommended next step for the LLM path.

## Run

```bash
python llm_agent.py                                   # tests vision on saved frames (needs credits)
python -c "import orchestrator; orchestrator.run(llm_fallback=True)"   # hybrid live (needs credits)
```

Default `llm_fallback=False` keeps the orchestrator fully deterministic and free until an LLM
endpoint is wired.
