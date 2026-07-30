"""Regression + engine tests for Murder Bot / Easybot core modules."""
import importlib

import pytest
from conftest import DB_UP

VALID_ACTIONS = {"defend", "rally", "ghost", "bubble", "ignore"}


# ---- AI counter engine --------------------------------------------------- #
def test_counter_decide_megarally():
    import counter_ai
    d = counter_ai.decide({"incoming": {"kind": "rally", "lead_type": "siege",
                                        "total_millions": 130, "coordinated": True}})
    assert d["action"] in VALID_ACTIONS
    assert d["action"] == "bubble"                       # 130M coordinated → doctrine says bubble
    assert isinstance(d.get("ranked_plans"), list) and d["ranked_plans"]
    assert isinstance(d.get("learned"), list)            # self-evolving wiring present
    assert 0.0 <= float(d["confidence"]) <= 1.0


def test_counter_decide_solo_defense_wins():
    import counter_ai
    d = counter_ai.decide({"incoming": {"kind": "march", "lead_type": "ground",
                                        "total_millions": 8, "coordinated": False}})
    # a small solo hit is defendable, not a bubble
    assert d["action"] in {"defend", "ignore"}


@pytest.mark.skipif(not DB_UP, reason="murderbot DB not reachable")
def test_lookup_enemy_and_decide_vs():
    import counter_ai
    intel = counter_ai.lookup_enemy("Karu")
    assert intel is not None and intel["max_troops"] and intel["max_troops"] > 1_000_000
    d = counter_ai.decide_vs("Karu")
    assert d["intel_used"] is True
    assert d["action"] in VALID_ACTIONS


# ---- attack planner ------------------------------------------------------ #
@pytest.mark.skipif(not DB_UP, reason="murderbot DB not reachable")
def test_attack_planner_ranks_targets():
    import attack_planner
    tg = attack_planner.pick_targets()
    assert isinstance(tg, list)
    if tg:
        assert any(k in tg[0] for k in ("name", "target"))


# ---- knowledge / self-evolving brain ------------------------------------- #
@pytest.mark.skipif(not DB_UP, reason="murderbot DB not reachable")
def test_knowledge_stats():
    import knowledge_ingest
    s = knowledge_ingest.stats()
    assert s["total_docs"] >= 0 and s["total_chars"] >= 0


@pytest.mark.skipif(not DB_UP, reason="murderbot DB not reachable")
def test_knowledge_relevant_returns_list():
    import knowledge_synth
    r = knowledge_synth.relevant("bubble ghost rally defense", k=3)
    assert isinstance(r, list)


# ---- regression: every manager view module imports + exposes a router ----- #
@pytest.mark.parametrize("mod", [
    "reports_view", "generals_view", "counter_view", "map_view", "billing_view",
    "intel_view", "attack_view", "brain_view", "settings_view", "hub_view",
])
def test_view_module_imports_and_has_router(mod):
    m = importlib.import_module(mod)
    assert hasattr(m, "build_router") or hasattr(m, "router"), f"{mod} exposes no router"


# ---- selfcheck importable ------------------------------------------------ #
def test_selfcheck_importable():
    import selfcheck
    assert callable(selfcheck.main)
