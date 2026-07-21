"""Recommend Evony generals for roles and orchestrator tasks using GameKB."""

from __future__ import annotations

from game_kb import GameKB


ROLE_ALIASES = {
    "rally": "monster",
    "boss": "monster",
    "monster_hunt": "monster",
    "defense": "wall_defense",
    "wall": "wall_defense",
    "ground": "ground_attack",
    "mounted": "mounted_attack",
    "ranged": "ranged_attack",
    "range": "ranged_attack",
    "archer": "ranged_attack",
    "siege": "siege_attack",
}

_TIER_ORDER = {tier: order for order, tier in enumerate("SABCD")}


class GeneralAdvisor:
    def __init__(self, db):
        self.db = db if isinstance(db, GameKB) else GameKB(db)

    @staticmethod
    def _role(role):
        if not isinstance(role, str):
            return role
        role = role.strip().lower().replace("-", "_").replace(" ", "_")
        return ROLE_ALIASES.get(role, role)

    def recommend(self, role, n=5, gtype=None) -> list[dict]:
        role = self._role(role)
        if not role:
            return []
        ratings = self.db.ratings(role=role)
        recommendations = []
        for rating in ratings:
            general = self.db.get_general(rating.get("general"))
            if general is None or (gtype is not None and general.get("gtype") != gtype):
                continue
            recommendations.append({
                "name": general.get("name"),
                "gtype": general.get("gtype"),
                "quality": general.get("quality"),
                "tier": rating.get("tier"),
                "rank": rating.get("rank"),
                "best_use": general.get("best_use"),
            })

        def order(item):
            tier = item["tier"]
            rank = item["rank"]
            return (
                _TIER_ORDER.get(str(tier).upper(), len(_TIER_ORDER)),
                rank if isinstance(rank, (int, float)) else float("inf"),
            )

        recommendations.sort(key=order)
        return recommendations[:max(0, n)]

    def best_for_task(self, task_name, n=3) -> list[dict]:
        if not isinstance(task_name, str):
            return []
        task = task_name.strip().lower().replace("-", "_").replace(" ", "_")
        role = {
            "monster": "monster",
            "rally_join": "monster",
            "auto_shield": "wall_defense",
            "base_dev": "wall_defense",
            "base_dev_defense": "wall_defense",
            "auto_shield/base_dev_defense": "wall_defense",
            "defense": "wall_defense",
            "gather": "gathering",
        }.get(task)
        return self.recommend(role, n) if role else []


if __name__ == "__main__":
    import sqlite3
    import tempfile
    from pathlib import Path

    import game_kb

    ok = False
    try:
        with tempfile.TemporaryDirectory() as temporary:
            db = game_kb.GameKB(Path(temporary) / "game_kb.db")
            try:
                generals = [
                    ("Boudica", "mounted", "historic", "wall defense"),
                    ("Leonidas", "ground", "epic", "wall defense"),
                    ("William", "ranged", "epic", "wall defense"),
                    ("Martinus", "mounted", "historic", "monster hunting"),
                    ("Hannibal", "mounted", "epic", "monster hunting"),
                ]
                for name, gtype, quality, best_use in generals:
                    db.upsert_general(name, quality=quality, gtype=gtype, best_use=best_use)

                db.add_rating("Boudica", "wall_defense", "S", 1)
                db.add_rating("Leonidas", "wall_defense", "S", 2)
                db.add_rating("William", "wall_defense", "A", 1)
                db.add_rating("Martinus", "monster", "S", 2)
                db.add_rating("Hannibal", "monster", "A", 1)

                advisor = GeneralAdvisor(db)
                wall = advisor.recommend("wall_defense")
                print("wall_defense:", wall)
                assert [item["name"] for item in wall] == ["Boudica", "Leonidas", "William"]
                assert wall[0]["tier"] == "S" and wall[0]["rank"] == 1

                ground = advisor.recommend("wall_defense", gtype="ground")
                print("gtype=ground:", ground)
                assert [item["name"] for item in ground] == ["Leonidas"]

                wall_alias = advisor.recommend("wall")
                print("alias wall:", wall_alias)
                assert wall_alias == wall

                monster = advisor.best_for_task("monster")
                print("task monster:", monster)
                assert monster == advisor.recommend("monster", n=3)

                missing = advisor.recommend("no_such_role")
                print("missing role:", missing)
                assert missing == []
            finally:
                db.close()
        ok = True
    except Exception as error:
        print(f"SELF-TEST ERROR: {error}")

    real_path = Path("/Users/sward/work/scratch/evony-bot/game_brain/game_kb.db")
    try:
        if real_path.exists():
            connection = sqlite3.connect(f"{real_path.resolve().as_uri()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            real_db = game_kb.GameKB.__new__(game_kb.GameKB)
            real_db._db = connection
            try:
                live = GeneralAdvisor(real_db)
                print("LIVE wall_defense:", live.recommend("wall_defense", n=3))
                print("LIVE monster:", live.recommend("monster", n=3))
            finally:
                connection.close()
    except Exception as error:
        print(f"LIVE recommendations unavailable: {error}")

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
