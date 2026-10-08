import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { RobotState } from './types'

// 假的 WebSocket：測試裡用 FakeSocket.last.push(...) 模擬後端推送
class FakeSocket {
  static last: FakeSocket
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  url: string
  constructor(url: string) {
    this.url = url
    FakeSocket.last = this
    setTimeout(() => this.onopen?.(), 0)
  }
  push(robots: Record<string, RobotState>) {
    act(() => this.onmessage?.({ data: JSON.stringify({ robots }) }))
  }
  close() {
    this.onclose?.()
  }
}

const MAP = { width: 400, height: 200, resolution: 0.05, origin_x: 0, origin_y: 0, version: 1 }
const ready: RobotState = {
  pose: { x: 1, y: 1, yaw: 0 }, goal: null, status: 'idle', message: '', distance_remaining: null,
  plan: [], map_version: 1, map_ready: true, nav_ready: true,
}
const client = (x: number, y: number) => ({ clientX: (x + 0.5) * 10, clientY: (10.5 - y) * 10 })

let fetchMock: ReturnType<typeof vi.fn>

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', FakeSocket)
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/map') && !init?.method?.match(/POST|DELETE/)) return respond(200, MAP)
    return respond(202, { detail: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(
    { left: 0, top: 0, width: 210, height: 110, right: 210, bottom: 110, x: 0, y: 0, toJSON: () => ({}) } as DOMRect)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function startWith(robot: RobotState) {
  render(<App />)
  FakeSocket.last.push({ amr1: robot })
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/robots/amr1/map', expect.anything()))
  await screen.findByText('整張地圖')
  return screen.getByTestId('map-svg')
}

function drag(svg: HTMLElement, from: [number, number], to: [number, number]) {
  fireEvent.pointerDown(svg, { ...client(...from), button: 0, pointerId: 1 })
  fireEvent.pointerMove(svg, { ...client(...to), pointerId: 1 })
  fireEvent.pointerUp(svg, { ...client(...to), button: 0, pointerId: 1 })
}

describe('App', () => {
  it('拖曳派車送出 POST /goal（只連後端的 /api）', async () => {
    const svg = await startWith(ready)
    drag(svg, [10, 1], [10, 2])
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/robots/amr1/goal', expect.objectContaining({ method: 'POST' })))
    const body = JSON.parse(fetchMock.mock.calls.find((c) => c[0] === '/api/robots/amr1/goal')![1].body)
    expect(body.x).toBeCloseTo(10)
    expect(body.yaw).toBeCloseTo(Math.PI / 2)
    expect(FakeSocket.last.url).toMatch(/\/api\/ws$/)
    for (const [url] of fetchMock.mock.calls) expect(url).toMatch(/^\/api\//)
  })

  it('後端拒絕時顯示後端給的原因', async () => {
    const svg = await startWith(ready)
    fetchMock.mockImplementationOnce(() => respond(503, { detail: 'amr1 的導航還在啟動' }))
    drag(svg, [10, 1], [10, 2])
    expect(await screen.findByTestId('error')).toHaveTextContent('amr1 的導航還在啟動')
  })

  it('設定初始位姿：送出 POST /initial_pose，之後回到派車模式', async () => {
    const svg = await startWith({ ...ready, pose: null, nav_ready: false })
    expect(screen.getByRole('alert')).toHaveTextContent('尚未定位')
    fireEvent.click(screen.getByRole('button', { name: '設定初始位姿' }))
    drag(svg, [1, 1], [2, 1])
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/robots/amr1/initial_pose', expect.objectContaining({ method: 'POST' })))
    expect(screen.getByRole('button', { name: '設定初始位姿' })).toBeInTheDocument()
  })

  it('導航沒在執行時派車手勢停用', async () => {
    const svg = await startWith({ ...ready, nav_ready: false })
    drag(svg, [10, 1], [10, 2])
    expect(fetchMock.mock.calls.some((c) => c[0] === '/api/robots/amr1/goal')).toBe(false)
  })

  it('取消送出 DELETE /goal', async () => {
    await startWith({ ...ready, status: 'navigating', goal: { x: 10, y: 1, yaw: 0 } })
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/robots/amr1/goal', expect.objectContaining({ method: 'DELETE' })))
  })

  it('斷線時顯示橫幅並自動重連', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(<App />)
    const first = FakeSocket.last
    act(() => first.close())
    expect(screen.getByRole('alert')).toHaveTextContent('與後端斷線')
    await act(async () => { vi.advanceTimersByTime(2100) })
    expect(FakeSocket.last).not.toBe(first)
    vi.useRealTimers()
  })
})
