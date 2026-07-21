import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type General, type GeneralType } from '../api'

type GeneralTypeFilter = GeneralType | 'all'

const generalTypes: GeneralTypeFilter[] = ['all', 'ground', 'mounted', 'ranged', 'siege', 'wall', 'subcity', 'monster', 'other']
const roles = ['monster', 'wall_defense', 'ground_attack', 'mounted_attack', 'ranged_attack', 'siege_attack', 'gathering']

export function Generals() {
  const [search, setSearch] = useState('')
  const [gtype, setGtype] = useState<GeneralTypeFilter>('all')
  const [selected, setSelected] = useState<string | null>(null)
  const [role, setRole] = useState('monster')
  const type = gtype === 'all' ? undefined : gtype
  const list = useQuery({
    queryKey: ['generals', search, type],
    queryFn: () => api.getGenerals({ q: search.trim(), gtype: type }),
  })
  const detail = useQuery({
    queryKey: ['general', selected],
    queryFn: () => api.getGeneral(selected!),
    enabled: selected !== null,
  })
  const recommendations = useQuery({
    queryKey: ['generals-recommend', role, type],
    queryFn: () => api.recommendGenerals({ role, n: 5, gtype: type }),
  })
  const generals = list.data?.generals ?? []

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Roster intelligence</p><h1>Generals</h1></div>
        <span className="text-sm text-muted tabular-nums">{list.data?.total ?? 0} generals</span>
      </div>

      <section className="card mb-4 grid gap-4 sm:grid-cols-[minmax(0,1fr)_180px]">
        <label className="field-label">Search
          <input className="field" onChange={(event) => setSearch(event.target.value)} placeholder="Name, skill, or best use" type="search" value={search} />
        </label>
        <label className="field-label">Type
          <select className="field capitalize" onChange={(event) => setGtype(event.target.value as GeneralTypeFilter)} value={gtype}>
            {generalTypes.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </section>

      {list.isError && <div className="offline-banner">Generals are unavailable. Check the backend connection and try again.</div>}
      <section className="overflow-hidden rounded-card border border-border bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead className="border-b border-border bg-surface-2 text-xs uppercase tracking-[0.06em] text-muted">
              <tr><th className="px-4 py-3 font-medium">Name</th><th className="px-3 py-3 font-medium">Type</th><th className="px-3 py-3 font-medium">Quality</th><th className="px-3 py-3 font-medium">Best use</th></tr>
            </thead>
            <tbody className="divide-y divide-border">
              {generals.map((general) => <GeneralRow general={general} key={general.name} onSelect={setSelected} selected={selected === general.name} />)}
            </tbody>
          </table>
        </div>
        {!generals.length && <div className="m-4 empty-state">{list.isPending ? 'Loading generals…' : list.isError ? 'No general data available.' : 'No generals match these filters.'}</div>}
      </section>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <section className="card">
          <p className="eyebrow">Selected general</p>
          <h2 className="mb-4 mt-1 text-lg font-semibold">{selected ?? 'Ratings'}</h2>
          {!selected && <p className="text-sm text-muted">Select a general to inspect its ratings.</p>}
          {selected && detail.isPending && <p className="text-sm text-muted">Loading ratings…</p>}
          {selected && detail.isError && <div className="error-banner mb-0">Could not load this general’s details.</div>}
          {detail.data && (detail.data.ratings.length ? (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="bg-surface-2 text-xs uppercase tracking-[0.06em] text-muted"><tr><th className="px-3 py-2 font-medium">Role</th><th className="px-3 py-2 font-medium">Tier</th><th className="px-3 py-2 font-medium">Rank</th><th className="px-3 py-2 font-medium">Context</th></tr></thead>
                <tbody className="divide-y divide-border">{detail.data.ratings.map((rating, index) => (
                  <tr key={`${rating.role}-${rating.context ?? ''}-${index}`}><td className="px-3 py-2">{label(rating.role)}</td><td className="px-3 py-2 font-mono">{rating.tier ?? '—'}</td><td className="px-3 py-2 font-mono tabular-nums">{rating.rank ?? '—'}</td><td className="px-3 py-2 text-muted">{rating.context ?? '—'}</td></tr>
                ))}</tbody>
              </table>
            </div>
          ) : <p className="text-sm text-muted">No ratings recorded for this general.</p>)}
        </section>

        <section className="card">
          <div className="mb-4 flex items-end justify-between gap-4">
            <div><p className="eyebrow">Recommend</p><h2 className="mt-1 text-lg font-semibold">Best picks</h2></div>
            <label className="field-label w-48">Role
              <select className="field" onChange={(event) => setRole(event.target.value)} value={role}>
                {roles.map((value) => <option key={value} value={value}>{label(value)}</option>)}
              </select>
            </label>
          </div>
          {recommendations.isPending && <p className="text-sm text-muted">Loading recommendations…</p>}
          {recommendations.isError && <div className="error-banner mb-0">Recommendations are unavailable right now.</div>}
          {recommendations.data && (recommendations.data.recommendations.length ? (
            <ol className="space-y-2">{recommendations.data.recommendations.map((general) => (
              <li className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2" key={general.name}>
                <span className="font-mono text-sm text-muted tabular-nums">{general.rank ?? '—'}</span>
                <span><strong className="font-medium">{general.name}</strong><span className="ml-2 text-xs capitalize text-muted">{general.gtype ?? 'other'}</span><span className="block text-xs text-muted">{general.best_use ?? 'No best use recorded'}</span></span>
                <span className="rounded bg-bg px-2 py-1 font-mono text-xs">{general.tier ?? '—'}</span>
              </li>
            ))}</ol>
          ) : <p className="text-sm text-muted">No recommendations match this role and type.</p>)}
        </section>
      </div>
    </div>
  )
}

function GeneralRow({ general, onSelect, selected }: { general: General; onSelect: (name: string) => void; selected: boolean }) {
  const select = () => onSelect(general.name)
  return (
    <tr
      aria-selected={selected}
      className={`cursor-pointer transition hover:bg-surface-2/60 ${selected ? 'bg-surface-2' : ''}`}
      onClick={select}
      onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') select() }}
      role="button"
      tabIndex={0}
    >
      <td className="px-4 py-3 font-medium">{general.name}</td><td className="px-3 py-3 capitalize text-muted">{general.gtype ?? '—'}</td><td className="px-3 py-3 capitalize text-muted">{general.quality ?? '—'}</td><td className="px-3 py-3 text-muted">{general.best_use ?? '—'}</td>
    </tr>
  )
}

function label(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
