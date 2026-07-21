import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Hls from 'hls.js'
import { API_BASE_URL, api } from '../api'

export function Live() {
  const video = useRef<HTMLVideoElement>(null)
  const [fallback, setFallback] = useState(false)
  const [changing, setChanging] = useState(false)
  const stream = useQuery({ queryKey: ['stream'], queryFn: api.getStreamStatus, refetchInterval: 1_000 })

  useEffect(() => {
    void api.startStream().then(() => stream.refetch()).catch(() => setFallback(true))
  }, [])

  useEffect(() => {
    const element = video.current
    if (!element || fallback || !stream.data?.running || !stream.data.ready) return
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
  }, [fallback, stream.data?.ready, stream.data?.running])

  useEffect(() => {
    if (!fallback || !stream.data?.running) return
    void api.stopStream().then(() => stream.refetch())
  }, [fallback, stream.data?.running])

  const toggle = async () => {
    setChanging(true)
    try {
      if (stream.data?.running) {
        await api.stopStream()
      } else {
        setFallback(false)
        await api.startStream()
      }
      await stream.refetch()
    } finally {
      setChanging(false)
    }
  }

  const running = stream.data?.running ?? false
  const noSignal = stream.isError || (!running && !fallback)

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Observe</p><h1>Live</h1></div>
        <span className={`text-sm ${noSignal ? 'text-warn' : 'text-good'}`}>{fallback ? 'MJPEG fallback' : noSignal ? 'No signal' : 'H.264 live'}</span>
      </div>
      {stream.isError && <div className="offline-banner">Backend unavailable. The stream will reconnect when Murder Bot returns.</div>}
      {stream.data?.error && <div className="error-banner">{stream.data.error}</div>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section className="card relative min-h-64 overflow-hidden p-0 md:p-0">
          {fallback ? (
            <img alt="Latest emulator screen" className="block aspect-video h-full w-full object-contain" src={`${API_BASE_URL}/api/screen.mjpeg`} />
          ) : (
            <video ref={video} aria-label="Live emulator screen" autoPlay className="block aspect-video h-full w-full object-contain" muted playsInline />
          )}
          {noSignal && <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-bg/45 text-sm text-muted">No device signal</div>}
        </section>
        <aside className="card space-y-5">
          <div><p className="eyebrow">Format</p><p className="mt-1 font-mono text-lg tabular-nums">{fallback ? 'MJPEG' : 'H.264 · 60fps'}</p></div>
          <div><p className="eyebrow">Stream</p><p className="mt-1 capitalize">{running ? stream.data?.ready ? 'live' : 'starting' : 'stopped'}</p></div>
          <div><p className="eyebrow">Latency</p><p className="mt-1">{stream.data?.segment_duration_s ?? 1}s segments</p></div>
          <button className={running ? 'button-secondary w-full' : 'button-primary w-full'} disabled={changing} onClick={() => void toggle()} type="button">{changing ? 'Working…' : running ? 'Stop stream' : 'Start stream'}</button>
          <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm text-muted">The H.264 stream owns adb while active. Stop it before mapping sweeps.</div>
        </aside>
      </div>
    </div>
  )
}
