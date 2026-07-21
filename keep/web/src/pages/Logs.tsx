import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type LogLine } from '../api'
import { useWS } from '../hooks/useWS'

type Level = 'all' | LogLine['level']

export function Logs() {
  const initial = useQuery({ queryKey: ['logs'], queryFn: api.getLogs, retry: false })
  const events = useQuery({ queryKey: ['events'], queryFn: api.getEvents, retry: false, refetchInterval: 10_000 })
  const socket = useWS<LogLine>('/ws/logs')
  const [live, setLive] = useState<LogLine[]>([])
  const [level, setLevel] = useState<Level>('all')

  useEffect(() => {
    if (!socket.data) return
    setLive((lines) => [...lines.filter((line) => line.cursor !== socket.data?.cursor), socket.data!].slice(-500))
  }, [socket.data])

  const lines = useMemo(() => {
    const unique = new Map<string, LogLine>()
    for (const line of [...(initial.data?.lines ?? []), ...live]) unique.set(line.cursor, line)
    return [...unique.values()].filter((line) => level === 'all' || line.level === level).slice(-500)
  }, [initial.data, level, live])

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Observe</p><h1>Logs</h1></div>
        <span className={`text-sm ${socket.status === 'open' ? 'text-good' : 'text-muted'}`}>{socket.status === 'open' ? 'Live tail' : socket.status}</span>
      </div>
      {initial.isError && <div className="offline-banner">Backend unavailable. Waiting for the log stream to reconnect.</div>}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.6fr)]">
        <section className="card min-w-0">
          <div className="mb-4 flex items-end justify-between gap-4">
            <div><p className="eyebrow">Tail</p><h2 className="mt-1 text-lg font-semibold">Runtime log</h2></div>
            <label className="field-label w-32">Level
              <select className="field" onChange={(event) => setLevel(event.target.value as Level)} value={level}>
                {['all', 'debug', 'info', 'warn', 'alert'].map((value) => <option key={value}>{value}</option>)}
              </select>
            </label>
          </div>
          <div className="max-h-[60vh] overflow-auto rounded-lg border border-border bg-bg font-mono text-xs tabular-nums">
            {lines.length ? lines.map((line) => <LogRow key={line.cursor} line={line} />) : <p className="p-5 text-muted">No log lines yet.</p>}
          </div>
        </section>
        <section className="card">
          <p className="eyebrow">Events</p><h2 className="mb-4 mt-1 text-lg font-semibold">Recent events</h2>
          <div className="space-y-3">
            {events.data?.events.length ? events.data.events.slice().reverse().map((event) => (
              <article className="rounded-lg border border-border bg-surface-2 p-3" key={`${event.ts}-${event.msg}`}>
                <div className="mb-1 flex justify-between gap-2 text-xs"><time className="font-mono text-muted">{time(event.ts)}</time><span className={levelColor(event.level)}>{event.level}</span></div>
                <p className="text-sm">{event.msg}</p>
              </article>
            )) : <p className="text-sm text-muted">No events recorded.</p>}
          </div>
        </section>
      </div>
    </div>
  )
}

function LogRow({ line }: { line: LogLine }) {
  return <div className="grid grid-cols-[5rem_3.5rem_7rem_minmax(0,1fr)] gap-2 border-b border-border px-3 py-2 last:border-b-0"><time className="text-muted">{time(line.ts)}</time><span className={levelColor(line.level)}>{line.level}</span><span className="truncate text-muted">{line.task ?? 'engine'}</span><span className="break-words">{line.msg}</span></div>
}

function time(value: string) {
  return new Date(value).toLocaleTimeString([], { hour12: false })
}

function levelColor(level: string) {
  return level === 'alert' ? 'text-bad' : level === 'warn' ? 'text-warn' : level === 'info' ? 'text-good' : 'text-muted'
}
