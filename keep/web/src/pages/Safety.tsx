import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { PanicStop } from '../components/PanicStop'

export function Safety() {
  const query = useQuery({ queryKey: ['safety'], queryFn: api.getSafety, retry: false, refetchInterval: 10_000 })
  const safety = query.data
  const invariants = [
    ['Gem spending disabled', safety ? !safety.gem_spend && safety.locked : false, 'Locked in backend validation'],
    ['Disconnect is stop-only', safety?.disconnect_policy === 'stop_only', 'Never taps Quit or Restart'],
    ['Humanization required', safety?.humanize_required, 'Humanized input cannot be disabled'],
    ['Reclaim requires confirmation', safety?.reclaim_requires_confirm, 'Session reclaim is never automatic'],
  ] as const

  return (
    <div>
      <div className="page-heading"><div><p className="eyebrow">Locked invariants</p><h1>Safety</h1></div><PanicStop /></div>
      {query.isError && <div className="offline-banner">Backend unavailable. Safety controls remain unavailable and no device action is attempted.</div>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section className="card">
          <p className="eyebrow">Enforced</p><h2 className="mb-4 mt-1 text-lg font-semibold">Invariant checklist</h2>
          <div className="space-y-3">
            {invariants.map(([label, active, detail]) => (
              <div className={`flex items-start gap-3 rounded-lg border p-4 ${active ? 'semantic-good' : 'border-border bg-surface-2'}`} key={label}>
                <span className={active ? 'text-good' : 'text-muted'}>{active ? '✓' : '—'}</span>
                <div><p className="font-medium">🔒 {label}</p><p className="mt-1 text-sm text-muted">{detail}</p></div>
              </div>
            ))}
          </div>
        </section>
        <aside className="space-y-4">
          <section className="card"><p className="eyebrow">Gem lock</p><p className="mt-2 text-2xl font-semibold text-good">Disabled</p><p className="mt-2 text-sm text-muted">The API rejects any config that enables gem spending.</p></section>
          <section className="card"><p className="eyebrow">Disconnect policy</p><p className="mt-2 font-mono tabular-nums">{safety?.disconnect_policy ?? 'unavailable'}</p><p className="mt-2 text-sm text-muted">A disconnect stops automation; reclaim requires explicit confirmation.</p></section>
        </aside>
      </div>
    </div>
  )
}
