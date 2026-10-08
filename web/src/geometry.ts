// 純函式：地圖座標 ↔ SVG 座標 ↔ 螢幕座標、縮放平移、手勢判斷（沒有 DOM 相依，方便測試）
//
// SVG 的單位直接用公尺，但 SVG 的 y 向下、地圖的 y 向上，所以畫東西時一律用 toSvg 把 y 變號。

import type { MapInfo, Point } from './types'

export interface ViewBox {
  x: number
  y: number
  width: number
  height: number
}

export interface Rect {
  left: number
  top: number
  width: number
  height: number
}

export const DRAG_THRESHOLD = 0.1     // 公尺：移動超過這個距離才算拖曳（決定方向）

export function toSvg(p: Point): Point {
  return { x: p.x, y: -p.y }
}

export function mapBounds(info: MapInfo) {
  return {
    minX: info.origin_x,
    minY: info.origin_y,
    maxX: info.origin_x + info.width * info.resolution,
    maxY: info.origin_y + info.height * info.resolution,
  }
}

/** 顯示整張地圖的視窗（SVG 座標），四周留 margin 公尺。 */
export function fitViewBox(info: MapInfo, margin = 0.5): ViewBox {
  const b = mapBounds(info)
  return {
    x: b.minX - margin,
    y: -b.maxY - margin,
    width: b.maxX - b.minX + 2 * margin,
    height: b.maxY - b.minY + 2 * margin,
  }
}

/** SVG 預設 preserveAspectRatio="xMidYMid meet"：等比例縮放、置中。回傳每公尺幾像素與左上角的位置。 */
function layout(rect: Rect, vb: ViewBox) {
  const scale = Math.min(rect.width / vb.width, rect.height / vb.height)
  return {
    scale,
    left: rect.left + (rect.width - vb.width * scale) / 2,
    top: rect.top + (rect.height - vb.height * scale) / 2,
  }
}

/** 螢幕座標（滑鼠事件的 clientX/Y）→ 地圖座標。 */
export function clientToMap(clientX: number, clientY: number, rect: Rect, vb: ViewBox): Point {
  const l = layout(rect, vb)
  const svgX = vb.x + (clientX - l.left) / l.scale
  const svgY = vb.y + (clientY - l.top) / l.scale
  return { x: svgX, y: -svgY + 0 }      // + 0：把 -0 變成 0
}

/** 以 anchor（SVG 座標）為中心縮放；factor < 1 放大、> 1 縮小。 */
export function zoomAt(vb: ViewBox, anchor: Point, factor: number): ViewBox {
  return {
    x: anchor.x - (anchor.x - vb.x) * factor,
    y: anchor.y - (anchor.y - vb.y) * factor,
    width: vb.width * factor,
    height: vb.height * factor,
  }
}

/** 拖曳平移：滑鼠移動 (dx, dy) 像素，視窗往反方向移動同樣的距離。 */
export function pan(vb: ViewBox, rect: Rect, dx: number, dy: number): ViewBox {
  const { scale } = layout(rect, vb)
  return { ...vb, x: vb.x - dx / scale, y: vb.y - dy / scale }
}

export function isDrag(start: Point, current: Point): boolean {
  return Math.hypot(current.x - start.x, current.y - start.y) >= DRAG_THRESHOLD
}

/** 從 start 拖到 current 的方向（地圖座標的 yaw：+x 為 0、逆時針為正）。 */
export function dragYaw(start: Point, current: Point): number {
  return Math.atan2(current.y - start.y, current.x - start.x)
}

export function inMap(info: MapInfo, p: Point): boolean {
  const b = mapBounds(info)
  return p.x >= b.minX && p.x < b.maxX && p.y >= b.minY && p.y < b.maxY
}

/** 路徑點（地圖座標）→ SVG path 的 d 屬性。 */
export function pathData(points: [number, number][]): string {
  return points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x} ${-y}`).join('')
}

/** yaw（地圖，逆時針為正）→ SVG rotate 的角度（度；SVG 的 y 向下，所以變號）。 */
export function svgRotation(yaw: number): number {
  return (-yaw * 180) / Math.PI
}
