"""Deterministic, advisory-only strategy decisions for Evony GameState snapshots.

This module only recommends allowlisted orchestrator tasks. It performs no UI
operations and never recommends gem, instant-finish, or gem-speedup actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from state_reader import GameState


MODES = {"survive", "defend", "expand", "idle"}
PRIORITIES = {
    "training",
    "auto_shield",
    "daily_collect",
    "alliance",
    "base_dev",
    "gather",
    "rally_join",
    "monster",
    "stop",
    "refill_or_gather",
}
UNSAFE_WORDS = ("gem", "finish-now", "finish now", "instant", "speed-up", "speedup")


@dataclass
class StrategyDecision:
    mode: str
    priority: str
    reasons: list[str] = field(default_factory=list)
    escalate: bool = False
    scores: dict | None = None


class Strategist:
    def __init__(self, cfg=None):
        cfg = vars(cfg) if cfg is not None and not isinstance(cfg, dict) else (cfg or {})
        self.food_low = cfg.get("food_low", 100_000)
        self.min_idle_marches_to_gather = cfg.get("min_idle_marches_to_gather", 1)
        self.reserve = cfg.get("reserve", 1)
        self.min_screen_score = cfg.get("min_screen_score", 1)

    def decide(self, state, history=None) -> StrategyDecision:
        ambiguity = self._ambiguity(state)
        food = self._food(state)

        if getattr(state, "disconnect", None) is True:
            return self._make(state, "survive", "stop", "disconnect detected; stop without acting", ambiguity)

        if getattr(state, "under_attack", None) is True:
            return self._make(state, "defend", "auto_shield", "incoming attack detected", ambiguity)

        if food is not None and food < self.food_low:
            return self._make(
                state,
                "survive",
                "refill_or_gather",
                f"food {food} is below critical threshold {self.food_low}",
                ambiguity,
            )

        red_dots = getattr(state, "red_dots", None)
        if isinstance(red_dots, dict) and any(bool(value) for value in red_dots.values()):
            names = ", ".join(sorted(str(key) for key, value in red_dots.items() if value))
            return self._make(state, "expand", "daily_collect", f"red dots present: {names}", ambiguity)

        if self._build_slot_free(state):
            return self._make(state, "expand", "base_dev", "a build slot is free", ambiguity)

        idle = getattr(state, "idle_marches", None)
        if isinstance(idle, (int, float)) and not isinstance(idle, bool):
            available = idle - self.reserve
            if available >= self.min_idle_marches_to_gather:
                if self._opportunity(state):
                    return self._make(
                        state,
                        "expand",
                        "rally_join",
                        f"{idle} idle marches leave {available} above reserve and an opportunity is visible",
                        ambiguity,
                    )
                return self._make(
                    state,
                    "expand",
                    "gather",
                    f"{idle} idle marches leave {available} available above reserve",
                    ambiguity,
                )

        mode = "idle" if ambiguity else "expand"
        return self._make(state, mode, "training", "no higher-priority condition matched", ambiguity)

    def decide_strategic(self, state, describe_fn=None, kb_lookup=None, history=None) -> StrategyDecision:
        decision = self.decide(state, history=history)
        if describe_fn is None or not decision.escalate:
            return self._safe(decision, state)
        if getattr(state, "disconnect", None) is True or getattr(state, "under_attack", None) is True:
            return self._safe(decision, state)

        try:
            subject = getattr(state, "raw", None) or state
            try:
                scene = describe_fn(subject, "Describe threats, safety, resources, rallies, and monsters.")
            except TypeError:
                scene = describe_fn(subject)
            knowledge = ""
            if kb_lookup is not None:
                try:
                    knowledge = kb_lookup(scene, history)
                except TypeError:
                    knowledge = kb_lookup(scene)
            context = f"{scene} {knowledge} {history or ''}".lower()
        except Exception as error:
            return self._safe(StrategyDecision(
                decision.mode,
                decision.priority,
                decision.reasons + [f"strategic refinement unavailable: {type(error).__name__}"],
                True,
                decision.scores,
            ), state)

        if any(word in context for word in ("under attack", "pvp", "siege", "hostile", "turtle")):
            decision = StrategyDecision(
                "defend",
                "auto_shield",
                decision.reasons + ["strategic context indicates sustained PvP pressure"],
                True,
                decision.scores,
            )
        elif "safe" in context and any(word in context for word in ("resource-rich", "resource rich", "abundant")):
            decision = StrategyDecision(
                "expand",
                "base_dev",
                decision.reasons + ["strategic context indicates a safe, resource-rich position"],
                False,
                decision.scores,
            )
        return self._safe(decision, state)

    def _make(self, state, mode, priority, reason, ambiguity):
        return self._safe(StrategyDecision(
            mode,
            priority,
            [reason, *ambiguity],
            bool(ambiguity),
        ), state)

    def _safe(self, decision, state=None):
        if state is not None and getattr(state, "disconnect", None) is True:
            reasons = list(decision.reasons)
            if not any("disconnect" in reason.lower() for reason in reasons):
                reasons.append("disconnect safety post-check forced stop")
            return StrategyDecision("survive", "stop", reasons, decision.escalate, decision.scores)

        mode = decision.mode if isinstance(decision.mode, str) and decision.mode in MODES else "idle"
        priority = decision.priority
        unsafe = (not isinstance(priority, str) or priority not in PRIORITIES
                  or any(word in priority.lower() for word in UNSAFE_WORDS))
        if mode == decision.mode and not unsafe:
            return decision
        reasons = list(decision.reasons)
        if mode != decision.mode:
            reasons.append("unsupported mode rejected by safety post-check")
        if unsafe:
            priority = "training"
            reasons.append("unsafe or unsupported priority rejected by safety post-check")
        return StrategyDecision(mode, priority, reasons, True, decision.scores)

    def _ambiguity(self, state):
        reasons = []
        screen = getattr(state, "screen", None)
        if screen is None or str(screen).lower() == "unknown":
            reasons.append("screen is unknown")

        raw = getattr(state, "raw", None)
        if isinstance(raw, dict):
            score = raw.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool) and score < self.min_screen_score:
                reasons.append(f"screen confidence {score} is below {self.min_screen_score}")
            if raw.get("classify_error"):
                reasons.append("screen classification failed")

        fields = (
            self._food(state),
            getattr(state, "idle_marches", None),
            getattr(state, "timers", None),
            getattr(state, "red_dots", None),
            getattr(state, "under_attack", None),
            getattr(state, "disconnect", None),
        )
        if all(value is None for value in fields):
            reasons.append("all key decision fields are unknown")
        return reasons

    @staticmethod
    def _food(state):
        resources = getattr(state, "resources", None)
        food = resources.get("food") if isinstance(resources, dict) else None
        return food if isinstance(food, (int, float)) and not isinstance(food, bool) else None

    @staticmethod
    def _build_slot_free(state):
        raw = getattr(state, "raw", None)
        raw = raw if isinstance(raw, dict) else {}
        containers = [raw]
        if isinstance(raw.get("base_dev"), dict):
            containers.append(raw["base_dev"])
        for values in containers:
            for key in ("free_build_slots", "build_slots_free"):
                value = values.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                    return True
            for key in ("build_slot_free", "builder_free"):
                if values.get(key) is True or str(values.get(key, "")).lower() in {"free", "idle", "ready"}:
                    return True

        timers = getattr(state, "timers", None)
        if isinstance(timers, dict):
            for key, value in timers.items():
                if any(word in str(key).lower() for word in ("build", "builder", "construction")):
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 0:
                        return True
                    if str(value).lower() in {"free", "idle", "ready", "complete", "done"}:
                        return True
        return False

    @staticmethod
    def _opportunity(state):
        if getattr(state, "screen", None) in {"rally_list", "monster"}:
            return True
        raw = getattr(state, "raw", None)
        timers = getattr(state, "timers", None)
        for values in (raw, timers):
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if any(word in str(key).lower() for word in ("rally", "monster", "boss")) and bool(value):
                    return True
        description = raw.get("description", "") if isinstance(raw, dict) else ""
        return any(word in str(description).lower() for word in ("rally", "monster", "boss"))


# Offline self-test
if __name__ == "__main__":
    ok = True
    strategist = Strategist({"food_low": 100, "reserve": 1})
    decisions = []

    def run_case(name, state, expected):
        decision = strategist.decide(state)
        decisions.append(decision)
        summary = {
            "screen": state.screen,
            "disconnect": state.disconnect,
            "under_attack": state.under_attack,
            "food": state.resources.get("food") if isinstance(state.resources, dict) else None,
            "red_dots": state.red_dots,
            "idle_marches": state.idle_marches,
        }
        passed = expected(decision)
        print(f"{name}: input={summary} decision={decision} ok={passed}")
        return passed

    ok &= run_case(
        "disconnect wins",
        GameState(screen="disconnect", disconnect=True, under_attack=True),
        lambda decision: decision.mode == "survive" and decision.priority == "stop",
    )
    ok &= run_case(
        "under attack",
        GameState(screen="watchtower", disconnect=False, under_attack=True),
        lambda decision: decision.mode == "defend" and decision.priority == "auto_shield",
    )
    ok &= run_case(
        "critical food",
        GameState(screen="city", resources={"food": 99}, disconnect=False, under_attack=False),
        lambda decision: decision.priority == "refill_or_gather",
    )
    ok &= run_case(
        "red dots",
        GameState(screen="city", resources={"food": 500}, red_dots={"mail": True}, disconnect=False, under_attack=False),
        lambda decision: decision.priority == "daily_collect",
    )
    ok &= run_case(
        "idle marches",
        GameState(screen="world_map", resources={"food": 500}, idle_marches=4, red_dots={}, timers={}, disconnect=False, under_attack=False),
        lambda decision: decision.priority in {"gather", "rally_join"},
    )
    ok &= run_case(
        "nothing notable",
        GameState(screen="city", resources={"food": 500}, idle_marches=1, red_dots={}, timers={"building": 3600}, disconnect=False, under_attack=False),
        lambda decision: decision.priority == "training",
    )
    ok &= run_case(
        "ambiguous",
        GameState(screen="unknown"),
        lambda decision: decision.priority == "training" and decision.escalate,
    )

    hostile_describe = lambda *_args: {"mode": "expand", "priority": "spend_gems", "advice": "finish now instantly"}
    hostile_kb = lambda *_args: "buy gems and speed-up immediately"
    strategic_disconnect = strategist.decide_strategic(
        GameState(screen="unknown", disconnect=True, under_attack=True),
        describe_fn=hostile_describe,
        kb_lookup=hostile_kb,
    )
    decisions.append(strategic_disconnect)
    strategic_attack = strategist.decide_strategic(
        GameState(screen="unknown", disconnect=False, under_attack=True),
        describe_fn=hostile_describe,
        kb_lookup=hostile_kb,
    )
    decisions.append(strategic_attack)
    hostile_ambiguous = strategist.decide_strategic(
        GameState(screen="unknown"),
        describe_fn=hostile_describe,
        kb_lookup=hostile_kb,
    )
    decisions.append(hostile_ambiguous)
    print(f"strategic hostile disconnect: input=disconnect+attack decision={strategic_disconnect}")
    print(f"strategic hostile attack: input=attack decision={strategic_attack}")
    print(f"strategic hostile ambiguous: input=unknown decision={hostile_ambiguous}")
    ok &= strategic_disconnect.priority == "stop" and strategic_disconnect.mode == "survive"
    ok &= strategic_attack.priority == "auto_shield" and strategic_attack.mode == "defend"
    ok &= hostile_ambiguous.priority in PRIORITIES

    rejected = strategist._safe(StrategyDecision("expand", "spend_gems_finish_now", ["hostile upstream"]))
    decisions.append(rejected)
    print(f"safety rejection: input=spend_gems_finish_now decision={rejected}")
    ok &= rejected.priority == "training" and rejected.escalate
    ok &= all(decision.priority in PRIORITIES for decision in decisions)
    ok &= all(not any(word in decision.priority.lower() for word in UNSAFE_WORDS) for decision in decisions)

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
