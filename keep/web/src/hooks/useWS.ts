import { useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../api'

type SocketStatus = 'open' | 'connecting' | 'closed'

export function useWS<T>(channel: string) {
  const [data, setData] = useState<T | null>(null)
  const [status, setStatus] = useState<SocketStatus>('connecting')
  const attempts = useRef(0)

  useEffect(() => {
    let socket: WebSocket | undefined
    let reconnect: number | undefined
    let disposed = false

    const connect = () => {
      setStatus('connecting')
      const url = new URL(API_BASE_URL || window.location.origin)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      url.pathname = channel
      socket = new WebSocket(url)
      socket.onopen = () => {
        attempts.current = 0
        setStatus('open')
      }
      socket.onmessage = (event) => {
        try {
          setData(JSON.parse(event.data) as T)
        } catch {
          // Ignore malformed frames; the next heartbeat replaces them.
        }
      }
      socket.onclose = () => {
        if (disposed) return
        setStatus('closed')
        const delay = Math.min(1000 * 2 ** attempts.current++, 15_000)
        reconnect = window.setTimeout(connect, delay)
      }
      socket.onerror = () => socket?.close()
    }

    connect()
    return () => {
      disposed = true
      if (reconnect) window.clearTimeout(reconnect)
      socket?.close()
    }
  }, [channel])

  return { data, status }
}
