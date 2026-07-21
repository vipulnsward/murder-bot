import type { KeepConfig, TaskRuntime } from './api'

const task = (name: string, interval: number, priority: number, guard: Record<string, unknown> = {}): TaskRuntime => ({
  name,
  enabled: name === 'training',
  interval,
  priority,
  wired: name === 'training',
  runs: 0,
  fails: 0,
  last_run: null,
  next_run: null,
  state: 'unavailable',
  guard,
})

export const DEFAULT_TASKS: TaskRuntime[] = [
  task('training', 6, 10, { target_own: 1_000_000_000, train_qty: 269_228 }),
  task('auto_shield', 20, 1, { desired_cover_s: 28_800, react_within_s: 900 }),
  task('daily_collect', 600, 30, { max_per_tick: 3 }),
  task('alliance', 1800, 25, { donations_per_day: 20 }),
  task('base_dev', 300, 20, { min_speedup_remaining_s: 300 }),
  task('gather', 120, 15, { reserved_for_rallies: 1, preferred_min_level: 1 }),
  task('rally_join', 60, 12, { only_boss: true, reserved_free_marches: 0 }),
  task('monster', 90, 14, { max_level: 0, min_stamina_reserve: 0 }),
]

export const DEFAULT_CONFIG: KeepConfig = {
  version: 1,
  safety: {
    gem_spend: false,
    disconnect_policy: 'stop_only',
    humanize_required: true,
    macro_required: true,
    reclaim_requires_confirm: true,
  },
  humanize: {
    delay_between_taps: { lo: 0.3, hi: 0.8 },
    tap_duration_ms: { lo: 40, hi: 120 },
    deliberate_tap_prob: 0.1,
    same_button_max: 12,
  },
  macro: {
    enabled: true,
    sleep_len_h: { lo: 6, hi: 9 },
    sleep_anchor_h: { lo: 1, hi: 4 },
    micro_break_every_min: { lo: 20, hi: 60 },
    micro_break_len_min: { lo: 2, hi: 8 },
  },
  tasks: Object.fromEntries(DEFAULT_TASKS.map(({ name, enabled, interval, priority, guard }) => [
    name,
    { enabled, interval, priority, ...guard },
  ])),
  vision: {
    ocr_first: true,
    holo_model: 'mlx-community/holo1.5-7b-mlx',
    holo_fallback_on: false,
    holo_max_long_side: 960,
    template_match_threshold: 0.82,
  },
  notify: {
    mac_banner: true,
    slack_webhook: null,
    discord_webhook: null,
  },
}
