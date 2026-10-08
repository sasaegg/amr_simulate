import { describe, expect, it } from 'vitest'
import type { RobotState } from '../types'
import { bannerMessage } from './Banner'

const ready: RobotState = {
  pose: { x: 1, y: 1, yaw: 0 }, goal: null, status: 'idle', message: '', distance_remaining: null,
  plan: [], map_version: 1, map_ready: true, nav_ready: true,
}

describe('橫幅', () => {
  it('依序只顯示最需要處理的一則', () => {
    expect(bannerMessage(false, ready)).toContain('與後端斷線')
    expect(bannerMessage(true, { ...ready, map_ready: false, pose: null })).toContain('尚未收到地圖')
    expect(bannerMessage(true, { ...ready, pose: null, nav_ready: false })).toContain('設定初始位姿')
    expect(bannerMessage(true, { ...ready, nav_ready: false })).toContain('不能派車')
    expect(bannerMessage(true, ready)).toBeNull()
    expect(bannerMessage(true, undefined)).toBeNull()
  })
})
