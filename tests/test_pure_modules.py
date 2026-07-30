import pytest

import counter_general
from alliance_view import ThreatInput, add_threat, list_threats
from game_kb import GameKB


@pytest.mark.parametrize(
    ("enemy_type", "expected_counters"),
    [
        ("ground", {"MOUNTED"}),
        ("mounted", {"RANGED"}),
        ("ranged", {"GROUND", "SIEGE"}),
        ("siege", {"GROUND", "MOUNTED"}),
    ],
)
def test_counter_recommendations(enemy_type, expected_counters):
    result = counter_general.recommend_counters(enemy_type)
    module_counters = set(counter_general.counter_types(enemy_type))

    assert module_counters == expected_counters
    assert set(result["counter_types"]) == module_counters
    assert result["recommendations"]
    assert {pick["counter_type"] for pick in result["recommendations"]} <= module_counters


def test_named_general_resolves_to_ground():
    result = counter_general.recommend_counters("Akechi Mitsuhide")

    assert result["enemy_type"] == "GROUND"
    assert result["recommendations"]


def test_alliance_threats_use_temporary_sqlite_database(tmp_path):
    db_path = tmp_path / "alliance.db"
    cases = [
        ("Siege Scout", 650, "siege", "high"),
        ("Critical Scout", 1_200, "mounted", "critical"),
        ("Low Scout", 50, "ground", "low"),
    ]

    for name, power_millions, lead_type, expected_level in cases:
        stored = add_threat(
            ThreatInput(
                name=name,
                alliance="TEST",
                power_millions=power_millions,
                lead_type=lead_type,
            ),
            db_path=db_path,
        )
        assert stored["threat"] == expected_level

    threats = {threat["name"]: threat for threat in list_threats(db_path=db_path)}
    assert "Siege Scout" in threats
    assert threats["Siege Scout"]["counters"]


def test_game_kb_stats(monkeypatch):
    monkeypatch.chdir(__file__.rsplit("/tests/", 1)[0])
    kb = GameKB("game_brain/game_kb.db")
    try:
        stats = kb.stats()
    finally:
        kb.close()

    assert stats["generals"] > 0
    assert stats["ratings"] > 0
    assert stats["skills"] > 0
