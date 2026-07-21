import { useQuery } from '@tanstack/react-query'
import { api, type StatusResponse } from '../api'
import { useWS } from '../hooks/useWS'
import { PanicStop } from './PanicStop'

function isStatus(value: unknown): value is StatusResponse {
  return Boolean(value && typeof value === 'object' && 'engine' in value)
}

export function StatusStrip() {
  const query = useQuery({
    queryKey: ['status'],
    queryFn: api.getStatus,
    retry: false,
    refetchInterval: 5_000,
  })
  const socket = useWS<StatusResponse | { type: string }>('/ws/status')
  const status = isStatus(socket.data) ? socket.data : query.data
  const engine = status?.engine ?? 'disconnected'
  const dot = engine === 'running' ? 'bg-good' : engine === 'disconnected' ? 'bg-bad' : 'bg-warn'

  return (
    <header className="fixed left-rail right-0 top-0 z-20 flex h-strip items-center gap-3 border-b border-border bg-surface px-4 text-sm">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${dot} ${engine === 'running' ? 'engine-pulse' : ''}`} />
        <span className="capitalize text-text">{query.isPending && !status ? 'connecting' : engine}</span>
        <span className="hidden text-muted sm:inline">·</span>
        <span className="hidden min-w-0 truncate sm:inline">{status?.current_task ?? 'No current task'}</span>
        <span className="hidden text-muted md:inline">Macro: <strong className="font-medium text-text">{status?.macro.state ?? '—'}</strong></span>
        <span className="semantic-good whitespace-nowrap rounded-full border px-2 py-0.5 text-xs text-good">🔒 gem-safe</span>
        <span className="hidden whitespace-nowrap text-xs text-muted lg:inline">{socket.status === 'open' ? 'live' : 'REST fallback'}</span>
      </div>
      <PanicStop />
    </header>
  )
}
