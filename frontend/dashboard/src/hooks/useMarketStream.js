import { useEffect, useState } from 'react'
import { wsUrl } from '../api/client'

export function useMarketStream(symbol) {
  const [stream, setStream] = useState({ tick: null, signals: [] })

  useEffect(() => {
    const socket = new WebSocket(wsUrl(symbol))
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setStream(data)
      } catch {
        // ignore malformed messages
      }
    }
    return () => socket.close()
  }, [symbol])

  return stream
}
