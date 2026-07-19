---
title: "Evony — Automation & Botting Techniques"
tags: [evony, gaming, automation, botting, adb, reference, evony-bot]
type: reference
source: "web research (Evony ToS, emulatorautomation) + project experience"
---

# Evony: The King's Return — Automation & Botting

> ToS note: Evony's Terms of Service explicitly prohibit "cheats, exploits, automation software, bots, hacks, mods or any unauthorized third-party software" and "automated use of the system." Automation risks account enforcement. Use on accounts you accept the risk of losing.

## Control methods
- **ADB** — `input tap/text/swipe/keyevent`, `exec-out screencap`. Foundation of the working bot.
- **scrcpy** — mirror + manual override.
- **Emulator macros** — BlueStacks / LDPlayer / MEmu recorders (most detectable).
- **Auto.js / AutoX.js, Tasker** — on-device automation.

## Why vision is mandatory
- Evony is a **Unity** app (`com.topgamesinc.evony.flexion` / `UnityActivity`). Unity renders to a single `SurfaceView`, so there is **no accessibility tree**. Appium/UiAutomator2/Maestro can't read it.
- Therefore: **screenshot -> OpenCV template matching + Tesseract OCR -> tap** is the required approach.

## Tasks players automate
- **Auto-train troops** (esp. mass T1) — implemented; see 05-bot-project.md.
- **Auto-gather** resources, **auto-collect** production, **auto-heal** hospital.
- **Auto-use items** (food/resource top-up), **monster hunting**, **alliance help**, daily task collection.

## Robust architecture (stability)
- State machine: screenshot -> classify state via templates/OCR -> act; verify each transition; recover to a known screen when lost.
- Borrow patterns from long-running game bots: **ALAS (AzurLaneAutoScript)**, **MAA / maaFramework** (JSON task graphs, retries, reconnect, stuck detection).

## LLM / vision GUI-agent frameworks (future, self-improving)
- **UI-TARS** (ByteDance) — GUI grounding model, screenshot -> action; local.
- **Qwen2.5-VL** — GUI grounding, local via Ollama.
- **OmniParser** (Microsoft) — screenshot -> labeled elements (great for no-a11y Unity).
- **Mobile-Agent / Mobile-Agent-E** (self-evolving memory), **AppAgent** (learned element KB), **Midscene.js**, **droidrun**.
- Android automation **MCP servers** (screenshot/coordinate mode) to let an LLM drive on demand.

## Ban-risk reduction
- **Randomized human-like timing** (jittered delays), **real device > emulator** for detection, **don't run 24/7**, avoid obviously superhuman cadence.

## Sources
- https://m.evony.com/Terms.html
- https://emulatorautomation.com/
