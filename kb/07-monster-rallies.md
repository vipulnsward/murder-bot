---
title: "Evony — Monster Rallies, Bosses & Rally Mechanics"
tags: [evony, gaming, rally, boss, monster, pve, reference, evony-bot]
type: reference
source: "web research (Fandom Boss Monsters/War Hall/Rally Spot, evonyguidewiki, evonytkrguide, onechilledgamer, evony-server)"
---

# Evony — Monster Rallies, Bosses & Rally Mechanics

## Boss monsters
- **Levels 1–23**; stronger bosses spawn nearer the **map center**; more spawn during **Boss Monster events**.
- **Normal monsters** = fought solo; **Bosses** = alliance **rallies**.
- **Tier requirements:** L2 boss needs ≥**T5**; **event bosses need ≥T10**.
- **Rewards** scale with level: material chests (L1–3), **medals** (up to L10), **speed-ups** (30/60-min), **general EXP**, gems. In a top alliance, one high-level boss kill can clear **~5 days** of timers.

## Leading a rally
- Attack → **Alliance** → pick a **rally time** → screen shows monster strength vs. your march strength.
- **Rally capacity** (total troops across all joiners) is set by **War Hall level** + Alliance research (**Rallying Capacity**, **Super Rallying Capacity**).
- Send **mounted only, a single tier** (highest attack; same tier so all troops attack the same round). **Do NOT send mixed types/tiers** — it increases wounded and can cause a loss.
- **Best boss (mounted) generals:** Aethelflaed, Ii Naomasa, Prince Eugene, Mordred, Hannibal; **Sanada** as a boss-killer main (highest attack).

## Joining a rally
- Send just **1 general + 1 troop** (or 1–10 archers) to get **full loot + general EXP** without taking wounded or losing power.
- Only match the leader's tier/type if you're genuinely helping fill the rally.

## Rally mechanics
- **War Hall** → **rally capacity** (max allied troops in your rally + max participants). Low War Hall caps the rally regardless of Rally Spot.
- **Rally Spot** → your own **march size**; keep it at Keep level.
- **March size** increased by: Academy / Military Academy research, **Monarch Gear (War Horn)**, general march-size skills/specialties, and VIP.
- **Reinforcement** (Embassy) → send troops to defend allies.

## Automation angle (for the bot)
- Boss rallies are the **#1 source of speed-up items** — which are the real bottleneck for mass T1 training (the bot burns ~2d10h of speed-ups per Finish-All batch). Automating **"join alliance boss rallies with 1 general + 1 troop"** would continuously farm the speed-ups that feed the training loop.
- Natural next automation target: open Alliance/Rally list → detect an open rally → join with minimum troops → repeat. Ties directly into `05-bot-project.md`.

## Sources
- https://evony-the-kings-return.fandom.com/wiki/Boss_Monsters
- https://evony-the-kings-return.fandom.com/wiki/War_Hall
- https://evonyguidewiki.com/en/rally-spot-en/
- https://evonyguidewiki.com/en/best-boss-monster-general-en/
- https://onechilledgamer.com/evony-boss-monster-guide/
- https://www.evonytkrguide.com/guides/evony-tkr-guide-best-mounted-cavalry-generals
