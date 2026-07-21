"""Seed the offline vision catalog from existing screen knowledge and templates.

This seeds structure, not live screenshots. Element coordinates are placeholders;
exact positions need the live-capture pass described in kb/31.
"""

from pathlib import Path
import tempfile

from screen_id import SCREENS
from vision_db import VisionDB


HERE = Path(__file__).resolve().parent
DISCONNECT_CAPTURE = Path(
    "/private/tmp/claude-501/-Users-sward-work-scratch/"
    "c2e71639-9f51-4ec5-b5ef-685684771afc/scratchpad/holo_test.png"
)

SCREEN_DETAILS = {
    "disconnect": (
        "Logged-in-elsewhere popup; verified by disconnect_popup. Stop and let the operator or relaunch logic decide.",
        {"on_detect": "raise DisconnectError; never tap Restart or Reconnect"},
    ),
    "exit_dialog": (
        "Exit-game confirmation dialog; verified by exit_dialog or exit-related OCR.",
        {"to_previous": "tap Cancel at (360,1134); never tap Quit or Confirm"},
    ),
    "speedup_modal": (
        "Training Speed Up modal; verified by modal_speedup_title. Recovery may only close it.",
        {"from_training_barracks": "tap active timer, then Speed Up", "to_training_barracks": "tap X at (1010,594)"},
    ),
    "radial_dial": (
        "Building radial action menu; barracks Train and Speed Up options have verified templates.",
        {"from_city": "tap a matched building sprite", "to_city": "tap outside the ring or press back"},
    ),
    "training_barracks": (
        "Barracks training screen, covering kb/31 training_idle and training_busy states.",
        {"from_city": "barracks radial, Train (179,679), then tier icon (135,1237)", "to_radial_dial": "press back", "to_speedup_modal": "tap active timer, then Speed Up"},
    ),
    "search_panel": (
        "World-map search panel with Monster and Resource tabs and a level stepper; capture still required.",
        {"from_world_map": "tap the left-edge magnifier", "to_world_map": "press back or X"},
    ),
    "rally_list": (
        "Classifier label for kb/31 alliance_war, the ongoing rally list with Join buttons; capture still required.",
        {"from_city": "open Alliance, then War", "to_alliance": "press back"},
    ),
    "watchtower": (
        "Classifier label for kb/31 watchtower_list, titled Military Info and showing incoming marches; capture still required.",
        {"from_city": "tap the matched watchtower building", "to_city": "press back or X"},
    ),
    "academy_research": (
        "Classifier label for kb/31 research, the Academy research tree; capture still required.",
        {"from_city": "tap the matched Academy, then Research", "to_city": "press back"},
    ),
    "shield_truce": (
        "Truce Agreements are reached through Items and the War tab; City Buff is an alternate view that can overwrite an active shield.",
        {"from_city": "open Items, then War, then Truce Agreements", "alternate": "Keep radial, then City Buff", "to_city": "press back"},
    ),
    "keep_menu": (
        "Classifier label for kb/31 keep_radial, with Upgrade, Detail, Levy, City Buff, Cultures, and Decorate; capture still required.",
        {"from_city": "tap the matched Keep building", "to_city": "tap outside the ring or press back"},
    ),
    "world_map": (
        "World map identified by the city-toggle and alliance-button anchor combination; capture still required.",
        {"from_city": "tap the globe", "to_city": "tap the home or castle toggle"},
    ),
    "resources": (
        "Food-scoped resource inventory verified by food_1m_label.",
        {"from_city": "tap food amount at (200,33)", "to_city": "tap X at (1010,594)"},
    ),
    "alliance": (
        "Alliance panel with roster and Help, Science, Gift, War, and Store sub-screens; capture still required.",
        {"from_city": "tap the Alliance bottom-bar button", "to_city": "tap X"},
    ),
    "monster": (
        "Classifier label for a world-map monster tile-info popup with level, stamina, and Attack; capture still required.",
        {"from_world_map": "tap a monster sprite", "to_world_map": "tap X or press back", "to_march_deploy": "tap Attack"},
    ),
    "mail": (
        "Mail and Reports panel; the bird icon can flash red for an incoming attack; capture still required.",
        {"from_city": "tap the Mail bird on the bottom bar", "to_city": "press back or X"},
    ),
    "city": (
        "Home city hub, verified by barracks_bldg with the Keep-level tag as a future second anchor.",
        {"to_world_map": "tap the globe", "to_resources": "tap food amount at (200,33)", "to_alliance": "tap the Alliance bottom-bar button"},
    ),
}

TEMPLATE_MAP = {
    "back_arrow.png": ("global", "back"),
    "barracks_bldg.png": ("city", "barracks"),
    "cap_popup.png": ("cap_popup", "cap_popup"),
    "disconnect_popup.png": ("disconnect", "disconnect_popup"),
    "exit_dialog.png": ("exit_dialog", "exit_dialog"),
    "finish_all_btn.png": ("speedup_modal", "finish_all"),
    "food_1m_label.png": ("resources", "food_1m_label"),
    "food_1m_use_btn.png": ("resources", "food_1m_use"),
    "instant_train_btn.png": ("speedup_modal", "instant_train"),
    "modal_speedup_title.png": ("speedup_modal", "modal_speedup_title"),
    "radial_speedup.png": ("radial_dial", "speedup"),
    "radial_train.png": ("radial_dial", "train"),
    "slider_minus.png": ("cap_popup", "slider_minus"),
    "slider_plus.png": ("cap_popup", "slider_plus"),
    "speedup_btn.png": ("training_busy", "speedup"),
    "train_btn_idle.png": ("training_barracks", "train"),
    "use_btn.png": ("resources", "use"),
    "warrior_t1_icon.png": ("training_barracks", "warrior_t1"),
    "warriors_title.png": ("training_barracks", "warriors_title"),
}

PLACEHOLDER_NOTE = "Coordinates are placeholders; exact positions require the kb/31 live-capture pass."
SAFETY_NOTES = {
    "finish_all_btn.png": " Catalog only: Finish All is unsafe in recovery because stacked batches can spend gems.",
    "instant_train_btn.png": " Catalog only: Instant Train is not marked safe and must not be used by recovery.",
}


def seed(db_path="game_brain/vision.db"):
    db = VisionDB(db_path)
    try:
        for label, keywords in SCREENS:
            description, nav = SCREEN_DETAILS[label]
            db.upsert_screen(label, description=description, keywords=" ".join(keywords), nav=nav)

        for filename, (screen_label, element_name) in TEMPLATE_MAP.items():
            db.add_element(
                screen_label,
                element_name,
                cx=0,
                cy=0,
                template_path=f"templates/{filename}",
                description=PLACEHOLDER_NOTE + SAFETY_NOTES.get(filename, ""),
            )

        if DISCONNECT_CAPTURE.exists():
            db.record_capture(
                image_path=str(DISCONNECT_CAPTURE),
                phash=VisionDB.phash(DISCONNECT_CAPTURE),
                screen_label="disconnect",
                holo_desc="Real disconnect-popup screenshot.",
                elements=[{"name": "disconnect_popup"}],
            )
        else:
            print(f"Capture skipped: {DISCONNECT_CAPTURE} is absent")

        stats = db.stats()
        catalog = db.catalog()
        print("Seeded:", " ".join(f"{name}={count}" for name, count in stats.items()))
        print("Example disconnect:", [item["name"] for item in catalog["disconnect"]["elements"]])
        print("Example city:", [item["name"] for item in catalog["city"]["elements"]], catalog["city"]["nav"])
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    ok = True
    try:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_db = Path(temporary) / "vision.db"
            temporary_stats = seed(temporary_db)
            check_db = VisionDB(temporary_db)
            try:
                temporary_catalog = check_db.catalog()
                assert temporary_stats["screens"] > 0
                assert temporary_stats["elements"] > 0
                assert "disconnect" in temporary_catalog
                assert any(
                    element["name"] == "disconnect_popup"
                    for element in temporary_catalog["disconnect"]["elements"]
                )
            finally:
                check_db.close()
            print("TEMP DB:", temporary_stats)
    except Exception as error:
        ok = False
        print("TEMP DB: FAIL", repr(error))

    try:
        real_path = HERE / "game_brain" / "vision.db"
        real_path.parent.mkdir(parents=True, exist_ok=True)
        real_stats = seed(real_path)
        print("REAL DB:", real_stats)
    except Exception as error:
        ok = False
        print("REAL DB: FAIL", repr(error))

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
