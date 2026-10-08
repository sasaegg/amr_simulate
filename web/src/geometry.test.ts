import { describe, expect, it } from 'vitest'
import {
  clientToMap, dragYaw, fitViewBox, inMap, isDrag, pan, pathData, toSvg, zoomAt,
} from './geometry'
import type { MapInfo } from './types'

// 地圖範圍 x ∈ [−1, 19)、y ∈ [−0.5, 9.5)
const MAP: MapInfo = { width: 400, height: 200, resolution: 0.05, origin_x: -1, origin_y: -0.5, version: 1 }

describe('座標轉換', () => {
  it('地圖 y 向上，SVG y 向下：toSvg 只把 y 變號', () => {
    expect(toSvg({ x: 2, y: 3 })).toEqual({ x: 2, y: -3 })
  })

  it('整張地圖的視窗：地圖範圍加邊界，換成 SVG 座標', () => {
    expect(fitViewBox(MAP, 0.5)).toEqual({ x: -1.5, y: -10, width: 21, height: 11 })
  })

  it('螢幕座標 → 地圖座標（視窗比例相同，沒有留白）', () => {
    const rect = { left: 100, top: 50, width: 200, height: 100 }
    const vb = { x: 0, y: -10, width: 20, height: 10 }      // 地圖 x 0～20、y 0～10
    expect(clientToMap(100, 50, rect, vb)).toEqual({ x: 0, y: 10 })      // 左上角
    expect(clientToMap(300, 150, rect, vb)).toEqual({ x: 20, y: 0 })     // 右下角
    expect(clientToMap(200, 100, rect, vb)).toEqual({ x: 10, y: 5 })     // 中心
  })

  it('螢幕座標 → 地圖座標（視窗比較寬，左右留白；同 SVG 的 xMidYMid meet）', () => {
    const rect = { left: 0, top: 0, width: 400, height: 100 }
    const vb = { x: 0, y: -10, width: 20, height: 10 }      // 比例 10 px/m，圖寬 200 px，左右各留 100 px
    expect(clientToMap(100, 0, rect, vb)).toEqual({ x: 0, y: 10 })
    expect(clientToMap(300, 100, rect, vb)).toEqual({ x: 20, y: 0 })
  })
})

describe('縮放與平移', () => {
  const vb = { x: 0, y: -10, width: 20, height: 10 }

  it('以游標為中心縮放：游標下的點不動', () => {
    const anchor = { x: 5, y: -5 }                           // SVG 座標
    const zoomed = zoomAt(vb, anchor, 0.5)
    expect(zoomed).toEqual({ x: 2.5, y: -7.5, width: 10, height: 5 })
    // anchor 在縮放前後的相對位置相同
    expect((anchor.x - vb.x) / vb.width).toBeCloseTo((anchor.x - zoomed.x) / zoomed.width)
  })

  it('平移：拖曳的像素依比例換成公尺，視窗往反方向移', () => {
    const rect = { left: 0, top: 0, width: 200, height: 100 }   // 10 px/m
    expect(pan(vb, rect, 20, -10)).toEqual({ x: -2, y: -9, width: 20, height: 10 })
  })
})

describe('手勢判斷', () => {
  it('超過 0.1 m 才算拖曳', () => {
    expect(isDrag({ x: 0, y: 0 }, { x: 0.05, y: 0.05 })).toBe(false)
    expect(isDrag({ x: 0, y: 0 }, { x: 0.1, y: 0 })).toBe(true)
  })

  it('拖曳方向 → yaw（地圖座標，+x 為 0、逆時針為正）', () => {
    expect(dragYaw({ x: 1, y: 1 }, { x: 2, y: 1 })).toBeCloseTo(0)
    expect(dragYaw({ x: 1, y: 1 }, { x: 1, y: 2 })).toBeCloseTo(Math.PI / 2)
    expect(dragYaw({ x: 1, y: 1 }, { x: 0, y: 1 })).toBeCloseTo(Math.PI)
    expect(dragYaw({ x: 1, y: 1 }, { x: 1, y: 0 })).toBeCloseTo(-Math.PI / 2)
  })

  it('是否在地圖內（含左下邊、不含右上邊）', () => {
    expect(inMap(MAP, { x: -1, y: -0.5 })).toBe(true)
    expect(inMap(MAP, { x: 18.99, y: 9.49 })).toBe(true)
    expect(inMap(MAP, { x: 19, y: 0 })).toBe(false)
    expect(inMap(MAP, { x: 0, y: -0.6 })).toBe(false)
  })
})

describe('路徑', () => {
  it('轉成 SVG path（y 變號）', () => {
    expect(pathData([[1, 2], [3, 4], [5, 6]])).toBe('M1 -2L3 -4L5 -6')
    expect(pathData([])).toBe('')
  })
})
