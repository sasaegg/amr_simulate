import { svgRotation, toSvg } from '../geometry'
import type { Pose } from '../types'

// 目標或拖曳中的預覽：位置的小圓點 ＋ 方向箭頭（長 0.8 m）
export function GoalArrow({ pose, variant }: { pose: Pose; variant: 'goal' | 'preview' | 'initial' }) {
  const p = toSvg(pose)
  return (
    <g className={`arrow arrow-${variant}`} data-testid={`arrow-${variant}`}
       transform={`translate(${p.x} ${p.y}) rotate(${svgRotation(pose.yaw)})`}>
      <circle r={0.08} />
      <line x1={0} y1={0} x2={0.65} y2={0} />
      <path d="M0.8 0 L0.55 0.14 L0.55 -0.14 Z" />
    </g>
  )
}
