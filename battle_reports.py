"""battle_reports — read-only report parsing, storage, and policy (kb/35).

Parsing and decisions are pure and tested offline. Report navigation and marking
remain injectable [LIVE-CAPTURE] operations; no gem-spend path exists here.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from itertools import islice
from pathlib import Path


@dataclass
class SideLosses:
    troops_sent: int = 0
    survived: int = 0
    wounded: int = 0
    dead: int = 0
    power_lost: int = 0
    kills: int = 0


@dataclass
class BattleReport:
    kind: str = "unknown"
    outcome: str = "n/a"
    target: dict = field(default_factory=dict)
    own: SideLosses = field(default_factory=SideLosses)
    enemy: SideLosses | None = None
    plunder: dict = field(default_factory=dict)
    rewards: dict = field(default_factory=dict)
    monster: dict | None = None
    participants: list = field(default_factory=list)
    scout: dict | None = None
    confidence: float = 0.0
    raw_text: str = ""
    ts: float = 0.0
    report_id: str = ""

    def to_dict(self):
        return asdict(self)


def _integer(value):
    if value is None or value == "":
        return 0
    try:
        return int(str(value).replace(",", "").replace(" ", ""))
    except (TypeError, ValueError):
        return 0


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _side(value):
    if isinstance(value, SideLosses):
        return value
    value = value if isinstance(value, dict) else {}
    return SideLosses(
        troops_sent=_integer(value.get("troops_sent")),
        survived=_integer(value.get("survived")),
        wounded=_integer(value.get("wounded")),
        dead=_integer(value.get("dead")),
        power_lost=_integer(value.get("power_lost")),
        kills=_integer(value.get("kills")),
    )


def _normalize_outcome(value):
    value = str(value or "").strip().lower()
    if value in {"victory", "win", "won", "success"}:
        return "win"
    if value in {"defeat", "loss", "lost", "failed"}:
        return "loss"
    if value in {"draw", "scouted", "n/a"}:
        return value
    return ""


def _power_outcome(own, enemy):
    if not isinstance(own, dict) or not isinstance(enemy, dict):
        return ""
    if own.get("power_lost") is None or enemy.get("power_lost") is None:
        return ""
    own_lost = _integer(own["power_lost"])
    enemy_lost = _integer(enemy["power_lost"])
    return "win" if own_lost < enemy_lost else "loss" if own_lost > enemy_lost else "draw"


def parse_report(fields) -> BattleReport:
    """Turn tolerant, already-read report fields into a normalized BattleReport."""

    fields = fields or {}
    kind = str(fields.get("kind") or "unknown").strip().lower()
    own_fields = fields.get("own")
    enemy_fields = fields.get("enemy")
    own = _side(own_fields)
    enemy = _side(enemy_fields) if enemy_fields is not None else None
    explicit = _normalize_outcome(
        fields.get("outcome") or fields.get("result") or fields.get("banner")
    )
    inferred = _power_outcome(own_fields, enemy_fields)
    outcome = explicit or inferred or ("scouted" if kind == "scout" else "n/a")
    target = fields.get("target") or {}
    target = dict(target) if isinstance(target, dict) else {"name": str(target)}
    if isinstance(target.get("coords"), list):
        target["coords"] = tuple(target["coords"])
    ts = _float(fields.get("ts"), time.time())
    special = any(
        fields.get(name) is not None
        for name in ("enemy", "monster", "scout", "participants")
    )
    if fields.get("confidence") is None:
        confidence = sum(
            (
                kind != "unknown",
                bool(explicit or inferred),
                own_fields is not None,
                fields.get("target") is not None,
                special,
            )
        ) / 5
        if explicit and inferred and explicit != inferred:
            confidence = min(confidence, 0.4)
    else:
        confidence = max(0.0, min(1.0, _float(fields["confidence"])))
    report_id = str(fields.get("report_id") or "")
    if not report_id:
        identity = json.dumps(
            {
                "ts": ts,
                "kind": kind,
                "target": target,
                "own_power_lost": own.power_lost,
                "enemy_power_lost": enemy.power_lost if enemy else None,
                "raw_text": fields.get("raw_text") or "",
            },
            sort_keys=True,
            default=str,
        )
        report_id = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return BattleReport(
        kind=kind,
        outcome=outcome,
        target=target,
        own=own,
        enemy=enemy,
        plunder=dict(fields.get("plunder") or {}),
        rewards=dict(fields.get("rewards") or {}),
        monster=dict(fields["monster"]) if fields.get("monster") else None,
        participants=list(fields.get("participants") or []),
        scout=dict(fields["scout"]) if fields.get("scout") else None,
        confidence=confidence,
        raw_text=str(fields.get("raw_text") or ""),
        ts=ts,
        report_id=report_id,
    )


class ReportPolicy:
    """Accumulate report outcomes and expose monster/PvP decision hooks."""

    def __init__(self, loss_threshold=0.05, monster_history=5, pvp_threshold=3,
                 pvp_window_s=3600, clock=None):
        self.loss_threshold = loss_threshold
        self.monster_history = monster_history
        self.pvp_threshold = pvp_threshold
        self.pvp_window_s = pvp_window_s
        self.clock = time.time if clock is None else clock
        self.reports = []
        self._report_ids = set()

    def observe(self, report):
        if report.report_id and report.report_id in self._report_ids:
            return False
        self.reports.append(report)
        if report.report_id:
            self._report_ids.add(report.report_id)
        return True

    def _monster_rates(self):
        samples = defaultdict(list)
        for report in self.reports:
            if not report.monster or report.own.troops_sent <= 0:
                continue
            monster_type = str(report.monster.get("type") or "")
            level = _integer(report.monster.get("level"))
            if monster_type:
                samples[(monster_type, level)].append(
                    (report.own.dead + report.own.wounded) / report.own.troops_sent
                )
        return {
            key: sum(values[-self.monster_history:]) / len(values[-self.monster_history:])
            for key, values in samples.items()
        }

    def monster_backoff(self, monster_type=None):
        suggestions = {}
        for (kind, level), loss_rate in self._monster_rates().items():
            if loss_rate > self.loss_threshold:
                suggested = max(0, level - 1)
                suggestions[kind] = min(suggestions.get(kind, suggested), suggested)
        return suggestions if monster_type is None else suggestions.get(monster_type)

    def pvp_pressure(self, now=None):
        now = self.clock() if now is None else now
        incoming = sum(
            report.kind == "pvp_defense"
            and now - self.pvp_window_s <= report.ts <= now
            for report in self.reports
        )
        return {
            "recommend_shield": incoming >= self.pvp_threshold,
            "attacks_incoming": incoming,
        }

    def summarize(self):
        loss_fields = tuple(SideLosses.__dataclass_fields__)
        own_losses = {
            name: sum(getattr(report.own, name) for report in self.reports)
            for name in loss_fields
        }
        plunder = defaultdict(int)
        for report in self.reports:
            for resource, amount in report.plunder.items():
                plunder[resource] += _integer(amount)
        return {
            "kd_ratio": (
                own_losses["kills"] / own_losses["dead"]
                if own_losses["dead"] else None
            ),
            "plunder_total": dict(plunder),
            "own_losses_total": own_losses,
            "wins": sum(report.outcome == "win" for report in self.reports),
            "losses": sum(report.outcome == "loss" for report in self.reports),
            "attacks_incoming_1h": self.pvp_pressure()["attacks_incoming"],
            "per_monster_loss_rate": self._monster_rates(),
        }


def load(path="battle_reports.jsonl"):
    """Load JSONL records as BattleReport objects."""

    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [parse_report(json.loads(line)) for line in handle if line.strip()]


def append(report, path="battle_reports.jsonl"):
    """Append a report unless its report_id already exists; return whether stored."""

    if not report.report_id:
        report = parse_report(report.to_dict())
    if any(existing.report_id == report.report_id for existing in load(path)):
        return False
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report.to_dict(), sort_keys=True) + "\n")
    return True


def _not_wired(*_a, **_k):
    raise NotImplementedError(
        "[LIVE-CAPTURE] battle_reports perceive/mark_read not wired — see kb/35."
    )


def make_task(perceive=None, parse=None, mark_read=None, policy=None, store=None,
              notify=None, max_per_tick=5):
    """Return run(ctx) for capped, read-only ingestion of unread reports."""

    perceive = _not_wired if perceive is None else perceive
    parse = parse_report if parse is None else parse
    mark_read = _not_wired if mark_read is None else mark_read
    policy = ReportPolicy() if policy is None else policy
    store = append if store is None else store

    def run(ctx):
        for fields in islice(perceive(ctx), max(0, int(max_per_tick))):
            report = parse(fields)
            stored = store(report) if callable(store) else store.append(report)
            if stored is not False:
                policy.observe(report)
                if notify and report.confidence < 0.5:
                    notify(f"battle_reports: low confidence {report.report_id}", "info")
            mark_read(ctx, fields)
            ctx.log(
                f"battle_reports: {report.kind} {report.outcome} ({report.report_id})"
            )
        return None

    run.policy = policy
    return run


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    ok = True
    NOW = 1_000_000.0
    pvp_fields = {
        "report_id": "pvp-1",
        "ts": NOW - 100,
        "kind": "pvp_defense",
        "result": "Victory",
        "target": {"name": "Raider", "coords": (100, 200), "keep_level": 35},
        "own": {
            "troops_sent": 1000,
            "survived": 900,
            "wounded": 50,
            "dead": 50,
            "power_lost": 1000,
            "kills": 300,
        },
        "enemy": {
            "troops_sent": 1200,
            "survived": 800,
            "wounded": 100,
            "dead": 300,
            "power_lost": 3000,
            "kills": 50,
        },
        "plunder": {"food": 500},
        "raw_text": "Victory over Raider",
    }
    monster_fields = {
        "report_id": "monster-1",
        "ts": NOW - 50,
        "kind": "monster",
        "outcome": "win",
        "target": {"name": "Ymir L5"},
        "own": {
            "troops_sent": 1000,
            "survived": 940,
            "wounded": 60,
            "dead": 0,
            "power_lost": 600,
        },
        "monster": {"type": "Ymir", "level": 5, "damage_dealt": 100000},
        "rewards": {"items": [{"name": "Ymir Chest", "qty": 1}]},
    }

    pvp = parse_report(pvp_fields)
    monster = parse_report(monster_fields)
    parsed = (
        pvp.outcome == "win"
        and pvp.enemy.dead == 300
        and pvp.confidence == 1.0
        and monster.monster["level"] == 5
        and monster.own.wounded == 60
    )
    print(f"1 parse PvP + monster -> {parsed}")
    ok &= parsed

    risky = ReportPolicy(loss_threshold=0.05, clock=lambda: NOW)
    risky.observe(monster)
    safe = ReportPolicy(loss_threshold=0.05, clock=lambda: NOW)
    safe.observe(parse_report({
        **monster_fields,
        "report_id": "monster-safe",
        "own": {"troops_sent": 1000, "wounded": 50},
    }))
    backoff = risky.monster_backoff("Ymir") == 4
    not_below = safe.monster_backoff("Ymir") is None
    print(f"2 monster backoff threshold -> above={backoff} not_below={not_below}")
    ok &= backoff and not_below

    pressure_policy = ReportPolicy(pvp_threshold=2, clock=lambda: NOW)
    pressure_policy.observe(pvp)
    pressure_policy.observe(parse_report({
        **pvp_fields,
        "report_id": "pvp-2",
        "ts": NOW - 10,
    }))
    pressure = pressure_policy.pvp_pressure()
    pressured = pressure["recommend_shield"] and pressure["attacks_incoming"] == 2
    print(f"3 repeated incoming recommends shield -> {pressured}")
    ok &= pressured

    with TemporaryDirectory() as directory:
        path = Path(directory) / "reports.jsonl"
        first = append(pvp, path)
        duplicate = append(pvp, path)
        round_trip = load(path)
        stored_once = (
            first and not duplicate and len(round_trip) == 1
            and round_trip[0] == pvp
        )
    print(f"4 JSONL round-trip + dedup -> {stored_once}")
    ok &= stored_once

    unread = [pvp_fields, monster_fields, {**pvp_fields, "report_id": "pvp-3"}]
    stored = []
    marked = []

    class FakeCtx:
        def log(self, message):
            return None

    task_policy = ReportPolicy(clock=lambda: NOW)
    run = make_task(
        perceive=lambda ctx: unread,
        mark_read=lambda ctx, fields: marked.append(fields["report_id"]),
        policy=task_policy,
        store=stored,
        max_per_tick=2,
    )
    run(FakeCtx())
    capped = len(stored) == 2 and len(marked) == 2 and len(task_policy.reports) == 2
    print(f"5 make_task processes unread + caps -> {capped}")
    ok &= capped

    raised = False
    try:
        make_task()(FakeCtx())
    except NotImplementedError as error:
        raised = str(error) == (
            "[LIVE-CAPTURE] battle_reports perceive/mark_read not wired — see kb/35."
        )
    print(f"6 unwired raises LIVE-CAPTURE = {raised}")
    ok &= raised

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
