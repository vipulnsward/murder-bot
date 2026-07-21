import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { API_BASE_URL, api, type ScreenFrame } from '../api'
import { useWS } from '../hooks/useWS'

export function Live() {
  const status = useQuery({ queryKey: ['status'], queryFn: api.getStatus, retry: false, refetchInterval: 5_000 })
  const screen = useWS<ScreenFrame>('/ws/screen')
  const [imageFailed, setImageFailed] = useState(false)
  const noSignal = imageFailed || screen.data?.no_signal !== false
  const label = screen.data?.screen ?? status.data?.screen ?? 'unknown'

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Observe</p><h1>Live</h1></div>
        <span className={`text-sm ${noSignal ? 'text-warn' : 'text-good'}`}>{noSignal ? 'No signal' : 'Live'}</span>
      </div>
      {status.isError && <div className="offline-banner">Backend unavailable. The stream will reconnect when Keep Console returns.</div>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section className="card relative min-h-64 overflow-hidden p-0 md:p-0">
          <img
            alt="Latest emulator screen"
            className="block aspect-video h-full w-full object-contain"
            onError={() => setImageFailed(true)}
            onLoad={() => setImageFailed(false)}
            src={`${API_BASE_URL}/api/screen.mjpeg`}
          />
          {noSignal && <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-bg/45 text-sm text-muted">No device signal</div>}
        </section>
        <aside className="card space-y-5">
          <div><p className="eyebrow">Screen label</p><p className="mt-1 font-mono text-lg tabular-nums">{label}</p></div>
          <div><p className="eyebrow">Stream</p><p className="mt-1 capitalize">{screen.status}</p></div>
          <div><p className="eyebrow">Engine</p><p className="mt-1 capitalize">{status.data?.engine ?? 'offline'}</p></div>
          <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm text-muted">Read-only live view · 🔒 no tap controls</div>
        </aside>
      </div>
    </div>
  )
}
