// WebSocket：後端每 0.1 秒推一次所有車的狀態。斷線後每 2 秒重連。
import { useEffect, useState } from 'react'
import type { RobotState } from './types'

export function defaultStreamUrl(): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/api/ws`
}

export interface RobotStream {
  connected: boolean
  robots: Record<string, RobotState>
}

export function useRobotStream(url: string = defaultStreamUrl(), retryMs = 2000): RobotStream {
  const [stream, setStream] = useState<RobotStream>({ connected: false, robots: {} })

  useEffect(() => {
    let socket: WebSocket
    let retry: ReturnType<typeof setTimeout> | undefined
    let stopped = false

    const connect = () => {
      socket = new WebSocket(url)
      socket.onopen = () => setStream((s) => ({ ...s, connected: true }))
      socket.onmessage = (event) =>
        setStream({ connected: true, robots: JSON.parse(event.data).robots })
      socket.onclose = () => {
        setStream((s) => ({ ...s, connected: false }))
        if (!stopped) retry = setTimeout(connect, retryMs)
      }
      socket.onerror = () => socket.close()     // 錯誤之後一定會 close，重連交給 onclose
    }
    connect()

    return () => {
      stopped = true
      clearTimeout(retry)
      socket.close()
    }
  }, [url, retryMs])

  return stream
}
