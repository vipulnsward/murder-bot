import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { SafetyBadges } from '../components/SafetyBadges'

const number = new Intl.NumberFormat('en-US')

export function Dashboard() {
  const query = useQuery({
    queryKey: ['status'],
    queryFn: api.getStatus,
    retry: false,
    refetchInterval: 5_000,
  })
  const status = query.data

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Keep Console</p><h1>Dashboard</h1></div>
        <span className="text-sm text-muted">{status?.account ?? 'main'} · {status?.device ?? 'backend offline'}</span>
      </div>

      {query.isError && <div className="offline-banner">Backend unavailable. Showing the safe empty dashboard; reconnecting via the status strip.</div>}
      {query.isPending && <div className="mb-4 text-sm text-muted">Loading engine status…</div>}

      <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.8fr)_minmax(420px,1.2fr)]">
        <section className="card">
          <div className="mb-5 flex items-center justify-between">
            <div><p className="eyebrow">Engine</p><h2 className="mt-1 text-lg font-semibold capitalize">{status?.engine ?? 'Disconnected'}</h2></div>
            <span className={`h-3 w-3 rounded-full ${status?.engine === 'running' ? 'bg-good' : 'bg-bad'}`} />
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Metric label="Own" value={status ? number.format(status.counts.own) : '—'} />
            <Metric label="Food" value={status ? number.format(status.counts.food) : '—'} />
            <Metric label="Batches" value={status ? number.format(status.counts.batches) : '—'} />
            <Metric label="Rate / min" value={status ? number.format(status.counts.rate_per_min) : '—'} />
          </div>
          <div className="mt-6"><SafetyBadges safety={status?.safety} /></div>
        </section>

        <section className="card">
          <div className="mb-3 flex items-center justify-between"><div><p className="eyebrow">Live</p><h2 className="mt-1 text-lg font-semibold">Screen preview</h2></div><span className="font-mono text-xs text-muted">{status?.screen ?? 'no frame'}</span></div>
          <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-border bg-surface-2 text-sm text-muted">
            Live MJPEG screen placeholder
          </div>
        </section>

        <section className="card xl:col-span-2">
          <div className="mb-4 flex items-center justify-between"><div><p className="eyebrow">Task summary</p><h2 className="mt-1 text-lg font-semibold">{status?.current_task ?? 'No active task'}</h2></div><span className="font-mono text-xs text-muted">{status ? `${number.format(status.ticks)} ticks` : '—'}</span></div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="mini-chart"><span>Own</span><span className="tracking-[0.3em] text-accent">▁▂▃▄▅▆▇</span></div>
            <div className="mini-chart"><span>Food</span><span className="tracking-[0.3em] text-warn">▇▆▅▄▃▂▁</span></div>
          </div>
          <div className="mt-4 rounded-lg bg-surface-2 p-3 text-sm text-muted">
            {status?.last_event ? <><time className="mr-2 font-mono tabular-nums">{new Date(status.last_event.ts).toLocaleTimeString([], { hour12: false })}</time>{status.last_event.msg}</> : 'Recent events will appear here.'}
          </div>
        </section>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs uppercase tracking-[0.06em] text-muted">{label}</p><p className="mt-1 font-mono text-xl font-semibold tabular-nums">{value}</p></div>
}
