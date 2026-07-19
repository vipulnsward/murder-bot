---
title: "Evony Bot — Adaptive / Self-Healing Design (research → adaptations)"
tags: [evony, evony-bot, self-healing, llm, vision-agent, reference]
type: project
source: "web research (UiPath/Keysight/qaskills self-healing 2026; Mobile-Agent-E arXiv 2501.11733; AppAgentX; self-healing test automation) + our stall experience"
---

# Adaptive / Self-Healing Design for the Evony Bot

## The problem we're solving
The bot trains reliably for ~100–140 batches, then an **event popup / capacity dialog / exit dialog / update splash** knocks it off the T1 Warriors screen, and the current recovery (back-only, no blind taps) can't climb back → 10-fail STOP. We want it to **self-heal**.

## What the research says (2026 self-healing)
- Two tiers: **locator fallback** (rule-based; multiple selectors ranked) heals ~40–70% of failures; **intent-based resolution** (a vision-LLM re-derives *which element satisfies the intent* — "the primary Train button") heals **75–90%+**, especially on layout changes. [UiPath Healing Agent, Keysight 2026, qaskills].
- **CV fallback**: when selectors fail, switch to image-based recognition over a saved screenshot.
- **Mobile-Agent-E** (arXiv 2501.11733): hierarchical agents — **Manager / Perceptor / Operator / Action Reflector / Notetaker** — with a **self-evolution memory of Tips (learned rules) + Shortcuts (reusable verified action sequences)** updated after each task. **AppAgentX** evolves reusable higher-level actions from exploration.

## How it maps to us
| Research concept | Our implementation |
|---|---|
| Locator fallback (ranked selectors) | Template matching (`train_btn_idle`, `speedup_btn`, …) + `barracks_bldg` template that matches ~0.95 across camera positions |
| Intent-based / CV fallback | **NEW: local vision-LLM fallback** (moondream / Qwen2.5-VL via Ollama) — when no template matches, ask "what screen is this + where is the Train/Confirm/close button?" and act |
| Tips (learned recovery rules) | **NEW: recovery playbook** — popup → known dismissal (below) |
| Shortcuts (verified sequences) | Our verified train cycle + food top-up; formalize as callable routines |
| Action Reflector (error verify) | We already verify each step (Own +269,228, template scores); keep |

## Recovery playbook (Tips) — known state → action
- `cap_popup` (exceeded capacity) → tap **Confirm** (714,1134). *(happens every cycle now — handled)*
- `exit_dialog` (quit game?) → tap **Cancel** (360,1134). NEVER Quit.
- `modal_speedup_title` open unexpectedly → **Finish All** (locate `finish_all_btn`) or close X.
- Update splash ("newer version available") → **refresh app**: `am force-stop com.topgamesinc.evony.flexion` then relaunch; wait for load. *(verified 2026-07 works)*
- Generic event popup (unknown modal over training) → tap the **close X** (locate a `close_x` template; top-right of the modal). Do NOT press back (back-on-city opens the exit dialog).
- Lost on city → locate `barracks_bldg` (0.95 match) → tap → **verify the IDLE radial** (Train present, no "Instant Finish" gem text) → tap Train at its matched position → select T1. Never blind-tap the radial (busy radial has Instant Finish = gems at the Train spot).

## Intent-based fallback (the new piece)
When template matching fails for N cycles, before giving up:
1. `screencap`, send to local VLM (moondream/Qwen2.5-VL): *"Is this Evony's T1 Warriors training screen? If not, name the popup and give the pixel location of its close/confirm/cancel button."*
2. Parse the answer; tap the returned location; re-check.
3. **Self-evolve**: if the VLM resolves a new popup, save a template + the action to the playbook so next time it's handled deterministically (deterministic hot path, LLM only for the long tail — keeps it fast + cheap).

## Reliability fixes learned from failures
- **Locate buttons by template, not fixed coordinates** — the food modal's Use button missed because the modal anchors at varying y; match `use_btn`/`finish_all_btn` and tap the matched center.
- **Wait for popups to render** (~0.7s) before reading/confirming (the capacity-popup race).
- **Verify outcomes** (food increased, Own increased) and retry the specific step, not a full re-navigation.

## Sources
- https://www.uipath.com/blog/product-and-updates/technical-tuesday-how-healing-agent-solves-ui-automation-challenges
- https://www.keysight.com/blogs/en/tech/software-testing/2026-self-healing-test-automation-beyond-locator-patching
- https://arxiv.org/abs/2501.11733 (Mobile-Agent-E)
- https://huggingface.co/papers/2503.02268 (AppAgentX)
