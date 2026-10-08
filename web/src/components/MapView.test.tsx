import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MapInfo, RobotState } from '../types'
import { MapView } from './MapView'

// 地圖 x 0～20、y 0～10；整張地圖的視窗（邊界 0.5 m）是 21 × 11 m。
// 把 SVG 的大小假裝成 210 × 110 px → 剛好 10 px/m、沒有留白：
//   螢幕 (cx, cy) ↔ 地圖 (−0.5 + cx/10, 10.5 − cy/10)
const MAP: MapInfo = { width: 400, height: 200, resolution: 0.05, origin_x: 0, origin_y: 0, version: 1 }
const client = (x: number, y: number) => ({ clientX: (x + 0.5) * 10, clientY: (10.5 - y) * 10 })

function robot(overrides: Partial<RobotState> = {}): RobotState {
  return {
    pose: { x: 1, y: 1, yaw: 0.7 }, goal: null, status: 'idle', message: '', distance_remaining: null,
    plan: [], map_version: 1, map_ready: true, nav_ready: true, ...overrides,
  }
}

beforeEach(() => {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(
    { left: 0, top: 0, width: 210, height: 110, right: 210, bottom: 110, x: 0, y: 0, toJSON: () => ({}) } as DOMRect)
})

function setup(props: Partial<Parameters<typeof MapView>[0]> = {}) {
  const onPose = vi.fn()
  const onCursor = vi.fn()
  render(
    <MapView info={MAP} imageUrl="/map.png" robot={robot()} mode="dispatch" gestureEnabled
             onPose={onPose} onCursor={onCursor} {...props} />,
  )
  return { svg: screen.getByTestId('map-svg'), onPose, onCursor }
}

describe('左鍵拖曳派車', () => {
  it('按下＝位置、拖曳＝方向、放開＝送出', () => {
    const { svg, onPose } = setup()
    fireEvent.pointerDown(svg, { ...client(10, 1), button: 0, pointerId: 1 })
    fireEvent.pointerMove(svg, { ...client(10, 2), pointerId: 1 })
    expect(screen.getByTestId('arrow-preview')).toBeInTheDocument()       // 拖曳中有預覽
    fireEvent.pointerUp(svg, { ...client(10, 2), button: 0, pointerId: 1 })
    expect(onPose).toHaveBeenCalledTimes(1)
    const [mode, pose] = onPose.mock.calls[0]
    expect(mode).toBe('dispatch')
    expect(pose.x).toBeCloseTo(10)
    expect(pose.y).toBeCloseTo(1)
    expect(pose.yaw).toBeCloseTo(Math.PI / 2)
    expect(screen.queryByTestId('arrow-preview')).not.toBeInTheDocument()
  })

  it('只點不拖：方向沿用車目前的朝向', () => {
    const { svg, onPose } = setup()
    fireEvent.pointerDown(svg, { ...client(5, 5), button: 0, pointerId: 1 })
    fireEvent.pointerUp(svg, { ...client(5.02, 5), button: 0, pointerId: 1 })
    expect(onPose.mock.calls[0][1].yaw).toBeCloseTo(0.7)
  })

  it('還沒定位時只點不拖，方向為 0', () => {
    const { svg, onPose } = setup({ robot: robot({ pose: null }) })
    fireEvent.pointerDown(svg, { ...client(5, 5), button: 0, pointerId: 1 })
    fireEvent.pointerUp(svg, { ...client(5, 5), button: 0, pointerId: 1 })
    expect(onPose.mock.calls[0][1].yaw).toBe(0)
  })

  it('按在地圖外不送出', () => {
    const { svg, onPose } = setup()
    fireEvent.pointerDown(svg, { ...client(-0.3, 5), button: 0, pointerId: 1 })
    fireEvent.pointerUp(svg, { ...client(1, 5), button: 0, pointerId: 1 })
    expect(onPose).not.toHaveBeenCalled()
  })

  it('手勢停用時（導航沒在執行）不送出', () => {
    const { svg, onPose } = setup({ gestureEnabled: false })
    fireEvent.pointerDown(svg, { ...client(10, 1), button: 0, pointerId: 1 })
    fireEvent.pointerUp(svg, { ...client(10, 2), button: 0, pointerId: 1 })
    expect(onPose).not.toHaveBeenCalled()
  })

  it('右鍵拖曳是平移，不送出', () => {
    const { svg, onPose } = setup()
    const before = svg.getAttribute('viewBox')
    fireEvent.pointerDown(svg, { ...client(10, 1), button: 2, pointerId: 1 })
    fireEvent.pointerMove(svg, { ...client(12, 1), pointerId: 1 })
    fireEvent.pointerUp(svg, { ...client(12, 1), button: 2, pointerId: 1 })
    expect(onPose).not.toHaveBeenCalled()
    expect(svg.getAttribute('viewBox')).not.toBe(before)
  })
})

describe('設定初始位姿模式', () => {
  it('同樣的手勢送出初始位姿', () => {
    const { svg, onPose } = setup({ mode: 'initial_pose' })
    fireEvent.pointerDown(svg, { ...client(1, 1), button: 0, pointerId: 1 })
    fireEvent.pointerMove(svg, { ...client(2, 1), pointerId: 1 })
    expect(screen.getByTestId('arrow-initial')).toBeInTheDocument()
    fireEvent.pointerUp(svg, { ...client(2, 1), button: 0, pointerId: 1 })
    const [mode, pose] = onPose.mock.calls[0]
    expect(mode).toBe('initial_pose')
    expect(pose.yaw).toBeCloseTo(0)
  })
})

describe('顯示', () => {
  it('游標座標', () => {
    const { svg, onCursor } = setup()
    fireEvent.pointerMove(svg, { ...client(7.3, 4.1), pointerId: 1 })
    const p = onCursor.mock.calls.at(-1)![0]
    expect(p.x).toBeCloseTo(7.3)
    expect(p.y).toBeCloseTo(4.1)
  })

  it('導航中顯示目標箭頭與路徑', () => {
    setup({ robot: robot({ status: 'navigating', goal: { x: 10, y: 1, yaw: 0 }, plan: [[1, 1], [5, 1], [10, 1]] }) })
    expect(screen.getByTestId('arrow-goal')).toBeInTheDocument()
    expect(document.querySelector('path.plan')?.getAttribute('d')).toBe('M1 -1L5 -1L10 -1')
    expect(document.querySelector('g.robot')).toBeInTheDocument()
  })

  it('沒有位置時不畫車；沒有地圖時顯示等待', () => {
    setup({ info: null, imageUrl: null, robot: robot({ pose: null }) })
    expect(document.querySelector('g.robot')).not.toBeInTheDocument()
    expect(screen.getByText('等待地圖…')).toBeInTheDocument()
  })
})
