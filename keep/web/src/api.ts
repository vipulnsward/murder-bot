// Default to same-origin (empty) so the app works wherever it's served — localhost,
// a tunnel, or a deploy. Only set VITE_API_BASE_URL when the API is on a different host.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export type EngineState = 'idle' | 'running' | 'paused' | 'stopped' | 'disconnected' | 'starting'
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
  game: {
    ok: boolean
    resources: { food?: number; wood?: number; stone?: number; gold?: number; refined?: number }
    power: number | null
    gems: number | null
    vip: number | null
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

export interface ScheduleSegment {
  start: string
  end: string
  state: MacroState
}

export interface LogLine {
  ts: string
  level: 'debug' | 'info' | 'warn' | 'alert'
  task: string | null
  msg: string
  cursor: string
}

export interface EventItem {
  ts: string
  level: string
  channel_sent: string[]
  msg: string
}

export interface SafetyResponse {
  gem_spend: false
  locked: true
  disconnect_policy: 'stop_only'
  humanize_required: boolean
  reclaim_requires_confirm: boolean
}

export interface ScreenFrame {
  seq: number
  ts: string
  jpg_b64: string | null
  screen: string | null
  no_signal: boolean
}

export interface StreamStatus {
  running: boolean
  ready: boolean
  owns_adb: boolean
  device: string
  output_dir: string
  screenrecord_pid: number | null
  ffmpeg_pid: number | null
  worker_alive: boolean
  screenrecord_alive: boolean
  ffmpeg_alive: boolean
  screenrecord_restarts: number
  fps_line: string | null
  segment_duration_s: number
  error: string | null
}

export type GeneralType = 'ground' | 'mounted' | 'ranged' | 'siege' | 'wall' | 'subcity' | 'monster' | 'other'

export interface General {
  name: string
  gtype: string | null
  quality: string | null
  best_use: string | null
}

export interface GeneralRating {
  role: string
  tier: string | null
  rank: number | null
  context: string | null
}

export interface GeneralDetail extends General {
  ratings: GeneralRating[]
}

export interface GeneralRecommendation {
  name: string
  gtype: string | null
  tier: string | null
  rank: number | null
  best_use: string | null
}

export interface Guide {
  title: string
  url: string
  category: string | null
  summary: string | null
}

export interface GeneralQuery {
  q?: string
  gtype?: GeneralType
  limit?: number
}

export interface GeneralRecommendationQuery {
  role: string
  n?: number
  gtype?: GeneralType
}

export interface GuideQuery {
  q?: string
  category?: string
}

export interface CityMap {
  ok: boolean
  stats: { screens?: number; captures?: number; elements?: number }
  buildings: string[]
  priority?: { found: string[]; missing: string[]; total: number }
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

function withQuery(path: string, params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const search = query.toString()
  return search ? `${path}?${search}` : path
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
  getLogs: () => request<{ lines: LogLine[]; cursor: string }>('/api/logs'),
  getEvents: () => request<{ events: EventItem[] }>('/api/events'),
  getSchedule: () => request<ScheduleSegment[]>('/api/schedule'),
  getSafety: () => request<SafetyResponse>('/api/safety'),
  getStreamStatus: () => request<StreamStatus>('/api/stream/status'),
  startStream: () => request<StreamStatus>('/api/stream/start', { method: 'POST' }),
  stopStream: () => request<StreamStatus>('/api/stream/stop', { method: 'POST' }),
  getGenerals: ({ q, gtype, limit }: GeneralQuery = {}) =>
    request<{ generals: General[]; total: number }>(withQuery('/api/generals', { q, gtype, limit })),
  getGeneral: (name: string) => request<GeneralDetail>(`/api/generals/${encodeURIComponent(name)}`),
  recommendGenerals: ({ role, n, gtype }: GeneralRecommendationQuery) =>
    request<{ role: string; recommendations: GeneralRecommendation[] }>(
      withQuery('/api/generals-recommend', { role, n, gtype }),
    ),
  getGuides: ({ q, category }: GuideQuery = {}) =>
    request<{ guides: Guide[]; total: number }>(withQuery('/api/guides', { q, category })),
  getKnowledgeDocs: () => request<{ docs: string[] }>('/api/kb'),
  getCity: () => request<CityMap>('/api/city'),
  getKnowledgeDoc: (name: string) =>
    request<{ name: string; markdown: string }>(`/api/kb/${encodeURIComponent(name)}`),
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
