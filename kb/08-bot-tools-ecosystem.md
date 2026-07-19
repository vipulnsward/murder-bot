---
title: "Evony — Third-Party Bot Tools (ecosystem)"
tags: [evony, evony-bot, automation, tools, reference]
type: reference
source: "web research (emulatorautomation, bestmobilebots, gnbots, boostbot, primebot, rage.systems)"
---

# Evony — Third-Party Bot Tools (ecosystem)

> All violate Evony's ToS; vendors' "no ban" claims are self-reported. Context for what's out there vs. our own local bot.

## Providers
- **ESB-TKR / EmulatorAutomation** — Android emulator + Windows macro app, "machine learning to play"; auto rally/farm/boss. Claims no proven bans.
- **BoostBot** — since 2015, 10k+ users; automates Research, Daily Chest, Collect Resources, Buffs, **Troop Training**, tile farming; runs 24/7; fast script execution.
- **GnBots (Evony Auto)** — **cloud-based, no emulator/download**; "**humanized clicking**" anti-ban; multi-account; claims zero bans.
- **PrimeBot** — 30+ tasks, multi-account simultaneously.
- **Ragebot TKR** (rage.systems) — auto rally/farm.

## Common feature set
Auto **join boss rallies**, farm resource tiles, **troop training**, healing, daily tasks, reward collection, map scan, auto-shield, multi-account management.

## Anti-ban approaches they advertise
- **Humanized / randomized clicking** (timing jitter) — same principle we use.
- **Cloud execution** (GnBots) — no local emulator fingerprint.

## How our bot compares
- **Ours:** local ADB + OpenCV template matching + Tesseract, self-hosted, free, fully transparent/editable, single account, vision-based (no game-file tampering).
- **Theirs:** paid subscriptions, broader task coverage (multi-account, cloud, map scan, rallies), turnkey.
- Takeaways to adopt: humanized timing (done), and their task list (rally-join, tile-farm, daily-collect, auto-heal) is a good **roadmap** for extending our bot beyond training.

## Sources
- https://emulatorautomation.com/
- https://bestmobilebots.com/evony-kings-return-bot/
- https://www.gnbots.com/evony-kings-return-bot/
- https://boostbot.org/evony-kings-return-bot/
- https://primebot.org/evony-the-kings-return-bot/
