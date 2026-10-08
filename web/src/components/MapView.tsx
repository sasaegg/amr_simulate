// 2D 地圖：底圖、車、目標、路徑；滾輪縮放、右鍵／中鍵拖曳平移；
// 左鍵和 RViz 的 2D Goal Pose 一樣：按下＝位置、拖曳＝方向、放開＝送出（派車或設定初始位姿）。
import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import {
  clientToMap, dragYaw, fitViewBox, inMap, isDrag, mapBounds, pan, zoomAt,
} from '../geometry'
import type { ViewBox } from '../geometry'
import type { GestureMode, MapInfo, Point, Pose, RobotState } from '../types'
import { GoalArrow } from './GoalArrow'
import { PlanPath } from './PlanPath'
import { RobotMarker } from './RobotMarker'

const ZOOM_STEP = 1.15

interface Props {
  info: MapInfo | null
  imageUrl: string | null
  robot: RobotState | undefined
  mode: GestureMode
  gestureEnabled: boolean               // false：左鍵手勢不作用（例如導航沒在執行時不能派車）
  onPose: (mode: GestureMode, pose: Pose) => void
  onCursor?: (p: Point | null) => void
}

interface Drag {
  start: Point
  current: Point
}

export function MapView({ info, imageUrl, robot, mode, gestureEnabled, onPose, onCursor }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [viewBox, setViewBox] = useState<ViewBox | null>(info ? fitViewBox(info) : null)
  const [drag, setDrag] = useState<Drag | null>(null)
  const panning = useRef<{ clientX: number; clientY: number } | null>(null)

  // 地圖的大小或位置變了（換了一張圖）才重設視角；同一張圖重新載入時保留使用者的縮放
  const extentKey = info ? `${info.width} ${info.height} ${info.resolution} ${info.origin_x} ${info.origin_y}` : ''
  useEffect(() => {
    setViewBox(info ? fitViewBox(info) : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extentKey])

  // 滾輪縮放要 preventDefault（不然整頁會捲動）；React 的 onWheel 是 passive，所以自己掛事件
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      setViewBox((vb) => {
        if (!vb) return vb
        const p = clientToMap(e.clientX, e.clientY, svg.getBoundingClientRect(), vb)
        return zoomAt(vb, { x: p.x, y: -p.y }, e.deltaY > 0 ? ZOOM_STEP : 1 / ZOOM_STEP)
      })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])

  const toMap = (e: ReactPointerEvent): Point | null => {
    if (!viewBox || !svgRef.current) return null
    return clientToMap(e.clientX, e.clientY, svgRef.current.getBoundingClientRect(), viewBox)
  }

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.button === 1 || e.button === 2) {
      panning.current = { clientX: e.clientX, clientY: e.clientY }
      e.currentTarget.setPointerCapture?.(e.pointerId)
      return
    }
    if (e.button !== 0 || !info || !gestureEnabled) return
    const p = toMap(e)
    if (!p || !inMap(info, p)) return        // 按在地圖外不算
    setDrag({ start: p, current: p })
    e.currentTarget.setPointerCapture?.(e.pointerId)   // 滑出地圖再放開也收得到
  }

  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const p = toMap(e)
    onCursor?.(p)
    if (panning.current && viewBox && svgRef.current) {
      const dx = e.clientX - panning.current.clientX
      const dy = e.clientY - panning.current.clientY
      panning.current = { clientX: e.clientX, clientY: e.clientY }
      setViewBox(pan(viewBox, svgRef.current.getBoundingClientRect(), dx, dy))
      return
    }
    if (drag && p) setDrag({ ...drag, current: p })
  }

  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (panning.current) {
      panning.current = null
      return
    }
    if (e.button !== 0 || !drag) return
    const end = toMap(e) ?? drag.current
    setDrag(null)
    onPose(mode, previewPose(drag.start, end, robot))
  }

  const preview = drag ? previewPose(drag.start, drag.current, robot) : null
  const bounds = info ? mapBounds(info) : null

  return (
    <div className={`map-view mode-${mode}`}>
      <svg
        ref={svgRef}
        data-testid="map-svg"
        viewBox={viewBox ? `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}` : '0 0 1 1'}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => onCursor?.(null)}
        onContextMenu={(e) => e.preventDefault()}
      >
        {info && bounds && imageUrl && (
          // PNG 的上方＝地圖 y 最大；SVG 的 y 變號後，圖片左上角就在 (minX, −maxY)
          <image
            href={imageUrl}
            x={bounds.minX}
            y={-bounds.maxY}
            width={bounds.maxX - bounds.minX}
            height={bounds.maxY - bounds.minY}
            preserveAspectRatio="none"
            style={{ imageRendering: 'pixelated' }}
          />
        )}
        {info && <OriginAxes />}
        {robot?.plan && <PlanPath plan={robot.plan} />}
        {robot?.goal && robot.status === 'navigating' && <GoalArrow pose={robot.goal} variant="goal" />}
        {robot?.pose && <RobotMarker pose={robot.pose} />}
        {preview && <GoalArrow pose={preview} variant={mode === 'dispatch' ? 'preview' : 'initial'} />}
      </svg>
      {info && (
        <button type="button" className="fit-button" onClick={() => setViewBox(fitViewBox(info))}>
          整張地圖
        </button>
      )}
      {!info && <div className="map-placeholder">等待地圖…</div>}
    </div>
  )
}

/** 拖曳中或放開時的位姿：有拖曳就用拖曳方向，只點一下就沿用車目前的朝向（沒有位置時為 0）。 */
export function previewPose(start: Point, current: Point, robot: RobotState | undefined): Pose {
  const yaw = isDrag(start, current) ? dragYaw(start, current) : (robot?.pose?.yaw ?? 0)
  return { x: start.x, y: start.y, yaw }
}

// 地圖原點的座標軸（紅＝+x、綠＝+y，同 RViz），長 1 m
function OriginAxes() {
  return (
    <g className="origin-axes">
      <line x1={0} y1={0} x2={1} y2={0} className="axis-x" />
      <line x1={0} y1={0} x2={0} y2={-1} className="axis-y" />
    </g>
  )
}
