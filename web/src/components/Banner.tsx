// 頂端提示：只顯示最需要處理的一則（依序：斷線 → 沒地圖 → 沒定位 → 導航沒準備好）
import type { RobotState } from '../types'

export function bannerMessage(connected: boolean, robot: RobotState | undefined): string | null {
  if (!connected) return '與後端斷線，每 2 秒自動重連…'
  if (!robot) return null
  if (!robot.map_ready) return '尚未收到地圖（車上的導航有在執行嗎？）'
  if (!robot.pose) return '車輛尚未定位：按「設定初始位姿」，在車子實際的位置按下、往車頭方向拖曳'
  if (!robot.nav_ready) return '導航沒有在執行或還在啟動，暫時不能派車'
  return null
}

export function Banner({ connected, robot }: { connected: boolean; robot: RobotState | undefined }) {
  const message = bannerMessage(connected, robot)
  if (!message) return null
  return <div className="banner" role="alert">{message}</div>
}
