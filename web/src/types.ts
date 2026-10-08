// 和後端（amr_server/api.py）的回應格式一致；座標都是地圖座標系 map（公尺、弧度）

export interface Pose {
  x: number
  y: number
  yaw: number
}

export interface Point {
  x: number
  y: number
}

export type NavStatus = 'idle' | 'navigating' | 'succeeded' | 'failed' | 'canceled'

export interface RobotState {
  pose: Pose | null
  goal: Pose | null
  status: NavStatus
  message: string
  distance_remaining: number | null
  plan: [number, number][]
  map_version: number
  map_ready: boolean
  nav_ready: boolean
}

export interface MapInfo {
  width: number
  height: number
  resolution: number
  origin_x: number
  origin_y: number
  version: number
}

// 地圖上左鍵拖曳的用途：派車（預設）或設定初始位姿
export type GestureMode = 'dispatch' | 'initial_pose'
