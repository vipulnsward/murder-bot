import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Hls from 'hls.js'
import { API_BASE_URL, api } from '../api'

export function Live() {
  const video = useRef<HTMLVideoElement>(null)
  const [fallback, setFallback] = useState(false)
  const [changing, setChanging] = useState(false)
  const stream = useQuery({ queryKey: ['stream'], queryFn: api.getStreamStatus, refetchInterval: 2_000 })

  const running = stream.data?.running ?? false
  const ready = stream.data?.ready ?? false
  // H.264 only when a stream is explicitly running AND ready AND hls.js is happy.
  // Otherwise the shared-frame MJPEG is the live view — it always works and never
  // needs a second adb capture, so it is the default rather than a last resort.
  const hlsActive = !fallback && running && ready

  useEffect(() => {
    const element = video.current
    if (!element || !hlsActive) return
    const source = `${API_BASE_URL}/hls/stream.m3u8`
    if (element.canPlayType('application/vnd.apple.mpegurl')) {
      element.src = source
      void element.play().catch(() => setFallback(true))
      return () => element.removeAttribute('src')
    }
    if (!Hls.isSupported()) {
      setFallback(true)
      return
    }
    const hls = new Hls({
      lowLatencyMode: true,
      liveSyncDurationCount: 1,
      liveMaxLatencyDurationCount: 3,
      maxBufferLength: 3,
      backBufferLength: 0,
    })
    hls.loadSource(source)
    hls.attachMedia(element)
    hls.on(Hls.Events.MANIFEST_PARSED, () => void element.play().catch(() => setFallback(true)))
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data.fatal) setFallback(true)
    })
    return () => hls.destroy()
  }, [hlsActive])

  const toggle = async () => {
    setChanging(true)
    try {
      if (running) {
        await api.stopStream()
      } else {
        setFallback(false)
        await api.startStream()
      }
      await stream.refetch()
    } catch {
      // Streaming is optional — the MJPEG shared frame keeps the screen live either way.
    } finally {
      setChanging(false)
    }
  }

  const backendDown = stream.isError
  const label = backendDown ? 'No signal' : hlsActive ? 'H.264 live' : 'Live · MJPEG'

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Observe</p><h1>Live</h1></div>
        <span className={`text-sm ${backendDown ? 'text-warn' : 'text-good'}`}>{label}</span>
      </div>
      {backendDown && <div className="offline-banner">Backend unavailable. The screen will reconnect when Murder Bot returns.</div>}
      {stream.data?.error && <div className="error-banner">{stream.data.error}</div>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section className="card relative min-h-64 overflow-hidden p-0 md:p-0">
          {hlsActive ? (
            <video ref={video} aria-label="Live emulator screen" autoPlay className="block aspect-video h-full w-full object-contain" muted playsInline />
          ) : (
            <img alt="Live emulator screen" className="block aspect-video h-full w-full object-contain" src={`${API_BASE_URL}/api/screen.mjpeg`} />
          )}
          {backendDown && <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-bg/45 text-sm text-muted">No device signal</div>}
        </section>
        <aside className="card space-y-5">
          <div><p className="eyebrow">Format</p><p className="mt-1 font-mono text-lg tabular-nums">{hlsActive ? 'H.264 · 60fps' : 'MJPEG'}</p></div>
          <div><p className="eyebrow">Stream</p><p className="mt-1 capitalize">{running ? (ready ? 'live' : 'starting') : 'stopped'}</p></div>
          <div><p className="eyebrow">Latency</p><p className="mt-1">{stream.data?.segment_duration_s ?? 1}s segments</p></div>
          <button className={running ? 'button-secondary w-full' : 'button-primary w-full'} disabled={changing} onClick={() => void toggle()} type="button">{changing ? 'Working…' : running ? 'Stop H.264 stream' : 'Start H.264 stream'}</button>
          <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm text-muted">The screen is always live via MJPEG. Start the H.264 stream for a smoother 60fps view — it takes over adb, so stop it before heavy mapping sweeps.</div>
        </aside>
      </div>
    </div>
  )
}
