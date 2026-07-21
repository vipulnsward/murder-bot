import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { API_BASE_URL, api } from '../api'
import { SafetyBadges } from '../components/SafetyBadges'

const number = new Intl.NumberFormat('en-US')

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return String(n)
}

export function Dashboard() {
  const query = useQuery({
    queryKey: ['status'],
    queryFn: api.getStatus,
    retry: false,
    refetchInterval: 5_000,
  })
  const status = query.data
  const city = useQuery({ queryKey: ['city'], queryFn: api.getCity, retry: false, refetchInterval: 10_000 })

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Murder Bot</p><h1>Dashboard</h1></div>
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
            <Metric label="Power" value={fmt(status?.game?.power)} />
            <Metric label="Gems" value={fmt(status?.game?.gems)} />
            <Metric label="VIP" value={status?.game?.vip != null ? String(status.game.vip) : '—'} />
            <Metric label="Food" value={fmt(status?.game?.resources?.food)} />
          </div>
          <div className="mt-5 grid grid-cols-4 gap-2 text-center">
            {(['wood', 'stone', 'gold', 'refined'] as const).map((k) => (
              <div key={k} className="rounded-lg border border-border bg-surface-2 py-2">
                <p className="text-[10px] uppercase tracking-wide text-muted">{k}</p>
                <p className="mt-0.5 font-mono text-sm tabular-nums">{fmt(status?.game?.resources?.[k])}</p>
              </div>
            ))}
          </div>
          <div className="mt-6"><SafetyBadges safety={status?.safety} /></div>
        </section>

        <section className="card">
          <div className="mb-3 flex items-center justify-between"><div><p className="eyebrow">Live</p><h2 className="mt-1 text-lg font-semibold">Screen preview</h2></div><span className="font-mono text-xs text-muted">{status?.screen ?? 'no frame'}</span></div>
          <Link className="block overflow-hidden rounded-lg border border-border bg-surface-2" title="Open the full Live view" to="/live">
            <img alt="Live emulator screen" className="block aspect-video h-full w-full object-contain" src={`${API_BASE_URL}/api/screen.mjpeg`} />
          </Link>
        </section>

        <section className="card xl:col-span-2">
          <div className="mb-4 flex items-center justify-between"><div><p className="eyebrow">Vision</p><h2 className="mt-1 text-lg font-semibold">Mapped city</h2></div><span className="font-mono text-xs text-muted">{city.data?.stats?.elements != null ? `${number.format(city.data.stats.elements)} elements` : '—'}</span></div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-lg border border-border bg-surface-2 py-3"><p className="text-[10px] uppercase tracking-wide text-muted">Buildings</p><p className="mt-0.5 font-mono text-xl font-semibold tabular-nums">{city.data?.buildings?.length ?? '—'}</p></div>
            <div className="rounded-lg border border-border bg-surface-2 py-3"><p className="text-[10px] uppercase tracking-wide text-muted">Screens</p><p className="mt-0.5 font-mono text-xl font-semibold tabular-nums">{city.data?.stats?.screens ?? '—'}</p></div>
            <div className="rounded-lg border border-border bg-surface-2 py-3"><p className="text-[10px] uppercase tracking-wide text-muted">Captures</p><p className="mt-0.5 font-mono text-xl font-semibold tabular-nums">{city.data?.stats?.captures ?? '—'}</p></div>
          </div>
          {city.data?.priority ? (
            <div className="mt-4">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="uppercase tracking-wide text-muted">Key buildings</span>
                <span className="font-mono tabular-nums text-muted">{city.data.priority.found.length}/{city.data.priority.total}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full rounded-full bg-good transition-[width] duration-500" style={{ width: `${city.data.priority.total ? (city.data.priority.found.length / city.data.priority.total) * 100 : 0}%` }} />
              </div>
              {city.data.priority.missing.length ? (
                <p className="mt-1.5 text-xs text-muted">Still hunting: <span className="text-warn">{city.data.priority.missing.map((b) => b.replace(/_/g, ' ')).join(', ')}</span></p>
              ) : <p className="mt-1.5 text-xs text-good">All key buildings mapped ✓</p>}
            </div>
          ) : null}
          {city.data?.buildings?.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {city.data.buildings.map((b) => (
                <span key={b} className="rounded-full border border-border bg-surface-2 px-2.5 py-1 text-xs capitalize text-muted">{b.replace(/_/g, ' ')}</span>
              ))}
            </div>
          ) : null}
          <div className="mt-4 rounded-lg bg-surface-2 p-3 text-sm text-muted">
            {status?.last_event ? <><time className="mr-2 font-mono tabular-nums">{new Date(status.last_event.ts).toLocaleTimeString([], { hour12: false })}</time>{status.last_event.msg}</> : 'The mapper is sweeping the city; new buildings appear here as they are found.'}
          </div>
        </section>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs uppercase tracking-[0.06em] text-muted">{label}</p><p className="mt-1 font-mono text-xl font-semibold tabular-nums">{value}</p></div>
}
