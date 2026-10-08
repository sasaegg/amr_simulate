import { svgRotation, toSvg } from '../geometry'
import type { Pose } from '../types'

// 車：圓形車身（直徑約等於實車 0.5 m）＋ 指向車頭的三角形
export function RobotMarker({ pose }: { pose: Pose }) {
  const p = toSvg(pose)
  return (
    <g className="robot" transform={`translate(${p.x} ${p.y}) rotate(${svgRotation(pose.yaw)})`}>
      <circle r={0.28} />
      <path d="M0.32 0 L0.02 0.16 L0.02 -0.16 Z" className="robot-heading" />
    </g>
  )
}
