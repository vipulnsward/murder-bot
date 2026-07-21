import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type MacroState, type ScheduleSegment } from '../api'

const stateClass: Record<MacroState, string> = {
  active: 'bg-good',
  micro_break: 'bg-warn',
  sleep: 'bg-warn opacity-45',
}

export function Schedule() {
  const query = useQuery({ queryKey: ['schedule'], queryFn: api.getSchedule, retry: false, refetchInterval: 60_000 })
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const segments = query.data ?? []
  const start = segments.length ? Date.parse(segments[0].start) : now
  const end = segments.length ? Date.parse(segments[segments.length - 1].end) : start + 86_400_000
  const duration = Math.max(1, end - start)
  const nowLeft = Math.min(99.8, Math.max(0.2, ((now - start) / duration) * 100))

  return (
    <div>
      <div className="page-heading"><div><p className="eyebrow">Macro rhythm</p><h1>Schedule</h1></div><span className="text-sm text-muted">Next 24 hours</span></div>
      {query.isError && <div className="offline-banner">Backend unavailable. The schedule will appear after reconnecting.</div>}
      <section className="card">
        <div className="mb-5 flex flex-wrap gap-4 text-xs text-muted"><Legend className="bg-good" label="Active" /><Legend className="bg-warn" label="Micro break" /><Legend className="bg-warn opacity-45" label="Sleep" /></div>
        {segments.length ? (
          <>
            <div className="relative flex h-16 overflow-hidden rounded-lg border border-border bg-surface-2">
              {segments.map((segment) => <Band duration={duration} key={`${segment.start}-${segment.state}`} segment={segment} start={start} />)}
              <span className="absolute inset-y-0 z-10 w-0.5 bg-text" style={{ left: `${nowLeft}%` }} title="Current time" />
            </div>
            <div className="mt-2 flex justify-between font-mono text-xs text-muted tabular-nums"><span>{clock(start)}</span><span>+6h</span><span>+12h</span><span>+18h</span><span>{clock(end)}</span></div>
            <div className="mt-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {segments.map((segment) => <SegmentRow key={`row-${segment.start}-${segment.state}`} segment={segment} />)}
            </div>
          </>
        ) : <div className="empty-state">{query.isPending ? 'Loading timeline…' : 'No schedule segments returned.'}</div>}
      </section>
    </div>
  )
}

function Band({ duration, segment, start }: { duration: number; segment: ScheduleSegment; start: number }) {
  const left = ((Date.parse(segment.start) - start) / duration) * 100
  const width = ((Date.parse(segment.end) - Date.parse(segment.start)) / duration) * 100
  return <span className={`absolute inset-y-0 ${stateClass[segment.state]}`} style={{ left: `${left}%`, width: `${width}%` }} title={`${segment.state}: ${clock(Date.parse(segment.start))}–${clock(Date.parse(segment.end))}`} />
}

function SegmentRow({ segment }: { segment: ScheduleSegment }) {
  return <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm"><span className="flex items-center gap-2 capitalize"><i className={`h-2 w-2 rounded-full ${stateClass[segment.state]}`} />{segment.state.replace('_', ' ')}</span><span className="font-mono text-xs text-muted tabular-nums">{clock(Date.parse(segment.start))}–{clock(Date.parse(segment.end))}</span></div>
}

function Legend({ className, label }: { className: string; label: string }) {
  return <span className="flex items-center gap-2"><i className={`h-2.5 w-2.5 rounded-sm ${className}`} />{label}</span>
}

function clock(value: number) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}
