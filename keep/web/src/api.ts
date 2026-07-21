export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export type EngineState = 'running' | 'paused' | 'stopped' | 'disconnected' | 'starting'
export type MacroState = 'active' | 'micro_break' | 'sleep'

export interface StatusResponse {
  engine: EngineState
  account: string
  device: string
  device_ok: boolean
  current_task: string | null
  macro: { state: MacroState; seconds_until_change: number }
  screen: string | null
  uptime_s: number
  ticks: number
  counts: {
    own: number
    food: number
    gems: number
    batches: number
    rate_per_min: number
  }
  safety: {
    gem_spend: false
    disconnect_safe: boolean
    humanized: boolean
    macro_on: boolean
  }
  last_event: { ts: string; level: string; msg: string } | null
  reload_pending: boolean
}

export interface TaskRuntime {
  name: string
  enabled: boolean
  interval: number
  priority: number
  wired: boolean
  runs: number
  fails: number
  last_run: string | null
  next_run: string | null
  state: string
  guard: Record<string, unknown>
}

export interface TaskConfig {
  enabled: boolean
  interval: number
  priority: number
  [key: string]: unknown
}

export interface KeepConfig {
  version: number
  safety: {
    gem_spend: false
    disconnect_policy: 'stop_only'
    humanize_required: boolean
    macro_required: boolean
    reclaim_requires_confirm?: boolean
    [key: string]: unknown
  }
  humanize: {
    delay_between_taps: NumberRange
    tap_duration_ms: NumberRange
    deliberate_tap_prob: number
    same_button_max: number
    [key: string]: unknown
  }
  macro: {
    enabled: boolean
    sleep_len_h: NumberRange
    sleep_anchor_h: NumberRange
    micro_break_every_min: NumberRange
    micro_break_len_min: NumberRange
    [key: string]: unknown
  }
  tasks: Record<string, TaskConfig>
  vision: {
    ocr_first: boolean
    holo_model: string
    holo_fallback_on: boolean
    holo_max_long_side: number
    template_match_threshold: number
    [key: string]: unknown
  }
  notify: {
    mac_banner: boolean
    slack_webhook: string | null
    discord_webhook: string | null
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface NumberRange {
  lo: number
  hi: number
}

export type ControlAction = 'start' | 'pause' | 'resume' | 'panic_stop' | 'reclaim_session'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly details?: unknown[],
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const error = body?.error
    throw new ApiError(error?.message ?? `Request failed (${response.status})`, response.status, error?.code, error?.details)
  }
  return body as T
}

export const api = {
  getStatus: () => request<StatusResponse>('/api/status'),
  getConfig: () => request<KeepConfig>('/api/config'),
  putConfig: (config: KeepConfig) =>
    request<{ config: KeepConfig; version_id: string; reload: 'queued' }>('/api/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),
  getTasks: () => request<{ tasks: TaskRuntime[] }>('/api/tasks'),
  toggleTask: (name: string) =>
    request<{ name: string; enabled: boolean; reload: 'queued'; warning?: string }>(
      `/api/tasks/${encodeURIComponent(name)}/toggle`,
      { method: 'POST' },
    ),
  control: (action: ControlAction, confirm = false) =>
    request<{ engine: EngineState; action: ControlAction }>('/api/control', {
      method: 'POST',
      body: JSON.stringify({ action, confirm }),
    }),
}
