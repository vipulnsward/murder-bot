"""Validated YAML configuration for Murder Bot."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CONFIG_VERSION = 1


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Range(ConfigModel):
    lo: float
    hi: float

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if self.hi < self.lo:
            raise ValueError(f"range hi ({self.hi}) < lo ({self.lo})")
        return self

    def as_tuple(self) -> tuple[float, float]:
        return self.lo, self.hi


class Account(ConfigModel):
    name: str
    adb_serial: str = "127.0.0.1:5555"
    enabled: bool = False
    features: list[str] = Field(default_factory=list)
    notes: str = ""


class Fleet(ConfigModel):
    active_account: str = "main"
    accounts: list[Account] = Field(
        default_factory=lambda: [Account(name="main", enabled=True)]
    )

    @model_validator(mode="after")
    def _active_exists(self) -> Fleet:
        names = {account.name for account in self.accounts}
        if self.active_account not in names:
            raise ValueError(
                f"active_account {self.active_account!r} not in accounts {names}"
            )
        return self


class Safety(ConfigModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    gem_spend: bool = Field(default=False, frozen=True)
    humanize_required: bool = Field(default=True, frozen=True)
    macro_required: bool = True
    reclaim_requires_confirm: bool = Field(default=True, frozen=True)
    disconnect_policy: str = "stop_only"

    @field_validator("gem_spend")
    @classmethod
    def _no_gems(cls, value: bool) -> bool:
        if value:
            raise ValueError("gem_spend is a locked invariant and can never be true")
        return value

    @field_validator("disconnect_policy")
    @classmethod
    def _only_stop(cls, value: str) -> str:
        if value != "stop_only":
            raise ValueError(
                "disconnect_policy is locked to 'stop_only' (never taps Quit/Restart)"
            )
        return value


class WindMouse(ConfigModel):
    G0: float = 9.0
    W0: float = 3.0
    M0: float = 15.0
    D0: float = 12.0


class Humanize(ConfigModel):
    jitter_samples: int = 3
    tap_box_shrink_px: int = 6
    delay_between_taps: Range = Field(default_factory=lambda: Range(lo=0.30, hi=0.80))
    delay_after_menu: Range = Field(default_factory=lambda: Range(lo=0.80, hi=2.50))
    delay_between_tasks: Range = Field(default_factory=lambda: Range(lo=3.0, hi=15.0))
    reaction_floor: float = 0.25
    tap_duration_ms: Range = Field(default_factory=lambda: Range(lo=40, hi=120))
    deliberate_tap_ms: Range = Field(default_factory=lambda: Range(lo=150, hi=400))
    deliberate_tap_prob: float = Field(default=0.10, ge=0.0, le=1.0)
    windmouse: WindMouse = Field(default_factory=WindMouse)
    swipe_segment_px: int = 12
    click_window: int = 15
    same_button_max: int = 12
    alt_button_max: int = 6


class MacroSchedule(ConfigModel):
    enabled: bool = True
    sleep_len_h: Range = Field(default_factory=lambda: Range(lo=6.0, hi=9.0))
    sleep_anchor_h: Range = Field(default_factory=lambda: Range(lo=1.0, hi=4.0))
    micro_break_every_min: Range = Field(
        default_factory=lambda: Range(lo=20.0, hi=60.0)
    )
    micro_break_len_min: Range = Field(default_factory=lambda: Range(lo=2.0, hi=8.0))
    idle_poll_cap_s: float = 300.0
    seed_salt: int = 0


class TaskBase(ConfigModel):
    enabled: bool
    interval: float = Field(gt=0)
    priority: int
    jitter: float = 0.0


class TrainingTask(TaskBase):
    enabled: bool = True
    interval: float = 6.0
    priority: int = 10
    target_own: int = 1_000_000_000
    train_qty: int = 269_228
    use_finish_all: bool = True


class AutoShieldTask(TaskBase):
    enabled: bool = False
    interval: float = 20.0
    priority: int = 1
    react_within_s: float = 900.0
    reshield_margin_s: float = 600.0
    desired_cover_s: float = 28_800.0
    proactive: bool = False


class DailySource(ConfigModel):
    key: str
    min_interval_s: int
    priority: int
    enabled: bool = True


def _daily_sources() -> list[DailySource]:
    return [
        DailySource(key="alliance_help", min_interval_s=120, priority=9),
        DailySource(key="city_resources", min_interval_s=600, priority=8),
        DailySource(key="mail", min_interval_s=300, priority=7),
        DailySource(key="tax", min_interval_s=3600, priority=7),
        DailySource(key="daily_quest_chest", min_interval_s=43200, priority=7),
        DailySource(key="bounty", min_interval_s=1800, priority=6),
        DailySource(key="eggs", min_interval_s=3600, priority=6),
        DailySource(key="patrol", min_interval_s=3600, priority=6),
        DailySource(key="wheel", min_interval_s=86400, priority=6),
        DailySource(key="free_chest", min_interval_s=14400, priority=5),
    ]


class DailyCollectTask(TaskBase):
    enabled: bool = False
    interval: float = 600.0
    priority: int = 30
    max_per_tick: int = 3
    sources: list[DailySource] = Field(default_factory=_daily_sources)


class AllianceTask(TaskBase):
    enabled: bool = False
    interval: float = 1800.0
    priority: int = 25
    donations_per_day: int = 20
    help_cooldown_s: float = 60.0


class BaseDevTask(TaskBase):
    enabled: bool = False
    interval: float = 300.0
    priority: int = 20
    preferred_speedup_item: str | None = None
    min_speedup_remaining_s: float = 300.0


class GatherTask(TaskBase):
    enabled: bool = False
    interval: float = 120.0
    priority: int = 15
    reserved_for_rallies: int = Field(default=1, ge=0)
    preferred_min_level: int = 1
    preferred_resource_types: tuple[str, ...] = ("ore", "stone", "lumber", "food")


class RallyJoinTask(TaskBase):
    enabled: bool = False
    interval: float = 60.0
    priority: int = 12
    only_boss: bool = True
    max_seconds_left: int = 300
    require_feasible: bool = True
    reserved_free_marches: int = Field(default=0, ge=0)


class MonsterTask(TaskBase):
    enabled: bool = False
    interval: float = 90.0
    priority: int = 14
    preferred_types: tuple[str, ...] = ()
    max_level: int = 0
    min_stamina_reserve: int = 0


class Tasks(ConfigModel):
    training: TrainingTask = Field(default_factory=TrainingTask)
    auto_shield: AutoShieldTask = Field(default_factory=AutoShieldTask)
    daily_collect: DailyCollectTask = Field(default_factory=DailyCollectTask)
    alliance: AllianceTask = Field(default_factory=AllianceTask)
    base_dev: BaseDevTask = Field(default_factory=BaseDevTask)
    gather: GatherTask = Field(default_factory=GatherTask)
    rally_join: RallyJoinTask = Field(default_factory=RallyJoinTask)
    monster: MonsterTask = Field(default_factory=MonsterTask)


class Vision(ConfigModel):
    ocr_first: bool = True
    holo_model: str = "mlx-community/holo1.5-7b-mlx"
    holo_fallback_on: bool = False
    holo_max_long_side: int = 960
    holo_max_tokens: int = 256
    template_match_threshold: float = 0.82
    llm_fallback: bool = False


class Notify(ConfigModel):
    mac_banner: bool = True
    slack_webhook: str | None = None
    discord_webhook: str | None = None


class Engine(ConfigModel):
    stuck_threshold: int = 6
    watchdog: bool = True
    idle_cap_s: float | None = None
    scheduler_retry_delay_s: float = 30.0


class KeepConfig(ConfigModel):
    version: int = CONFIG_VERSION
    fleet: Fleet = Field(default_factory=Fleet)
    safety: Safety = Field(default_factory=Safety)
    humanize: Humanize = Field(default_factory=Humanize)
    macro_schedule: MacroSchedule = Field(default_factory=MacroSchedule)
    tasks: Tasks = Field(default_factory=Tasks)
    vision: Vision = Field(default_factory=Vision)
    notify: Notify = Field(default_factory=Notify)
    engine: Engine = Field(default_factory=Engine)


def default_config() -> KeepConfig:
    return KeepConfig()


def load_config(path: str | Path = "config.yaml") -> KeepConfig:
    config_path = Path(path)
    if not config_path.exists():
        return default_config()
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return KeepConfig.model_validate({} if data is None else data)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"Invalid config {config_path}: {error}") from error


def save_config(cfg: KeepConfig, path: str | Path) -> None:
    Path(path).write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def _self_test() -> bool:
    ok = True

    try:
        cfg = default_config()
        case = (
            cfg.safety.gem_spend is False
            and cfg.humanize.delay_between_taps.as_tuple() == (0.3, 0.8)
            and cfg.macro_schedule.sleep_len_h.as_tuple() == (6.0, 9.0)
            and cfg.tasks.gather.reserved_for_rallies == 1
            and cfg.tasks.training.interval == 6.0
        )
    except Exception as error:
        case = False
        print(f"1 defaults: FAIL ({error})")
    else:
        print(f"1 defaults: {'PASS' if case else 'FAIL'}")
    ok &= case

    with TemporaryDirectory() as directory:
        config_path = Path(directory) / "config.yaml"
        try:
            save_config(default_config(), config_path)
            case = load_config(config_path) == default_config()
        except Exception as error:
            case = False
            print(f"2 round-trip: FAIL ({error})")
        else:
            print(f"2 round-trip: {'PASS' if case else 'FAIL'}")
        ok &= case

        gem_path = Path(directory) / "gem.yaml"
        gem_path.write_text("safety:\n  gem_spend: true\n", encoding="utf-8")
        try:
            load_config(gem_path)
        except ValueError as error:
            case = "gem_spend is a locked invariant" in str(error)
            print(f"3 gem lock: {'PASS' if case else 'FAIL'} ({error})")
        else:
            case = False
            print("3 gem lock: FAIL (true was accepted)")
        ok &= case

        edit_path = Path(directory) / "edited.yaml"
        try:
            edited = default_config()
            edited.tasks.gather.interval = 321.0
            save_config(edited, edit_path)
            case = load_config(edit_path).tasks.gather.interval == 321.0
        except Exception as error:
            case = False
            print(f"4 task edit: FAIL ({error})")
        else:
            print(f"4 task edit: {'PASS' if case else 'FAIL'}")
        ok &= case

    return ok


if __name__ == "__main__":
    success = _self_test()
    print("SELF-TEST:", "PASS" if success else "FAIL")
    raise SystemExit(0 if success else 1)
