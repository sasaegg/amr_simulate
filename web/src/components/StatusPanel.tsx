// 側欄：車輛選擇、導航狀態、取消、設定初始位姿、游標座標
import type { GestureMode, NavStatus, Point, RobotState } from '../types'

export const STATUS_LABEL: Record<NavStatus, string> = {
  idle: '待命',
  navigating: '導航中',
  succeeded: '已到達',
  failed: '失敗',
  canceled: '已取消',
}

interface Props {
  robotIds: string[]
  robotId: string
  onRobotChange: (id: string) => void
  robot: RobotState | undefined
  mode: GestureMode
  onModeChange: (mode: GestureMode) => void
  onCancel: () => void
  error: string | null
  cursor: Point | null
}

const fmt = (v: number) => v.toFixed(2)

export function StatusPanel({
  robotIds, robotId, onRobotChange, robot, mode, onModeChange, onCancel, error, cursor,
}: Props) {
  const navigating = robot?.status === 'navigating'
  return (
    <aside className="panel">
      <label className="field">
        <span>車輛</span>
        <select value={robotId} onChange={(e) => onRobotChange(e.target.value)} aria-label="車輛">
          {robotIds.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      </label>

      <dl className="status">
        <dt>狀態</dt>
        <dd data-testid="status" className={`status-${robot?.status ?? 'idle'}`}>
          {robot ? STATUS_LABEL[robot.status] : '—'}
        </dd>
        {robot?.message && (<><dt>原因</dt><dd data-testid="message" className="message">{robot.message}</dd></>)}
        {navigating && robot?.distance_remaining != null && (
          <><dt>剩餘</dt><dd>{robot.distance_remaining.toFixed(1)} m</dd></>
        )}
        {robot?.goal && (
          <><dt>目標</dt><dd>({fmt(robot.goal.x)}, {fmt(robot.goal.y)})</dd></>
        )}
        <dt>位置</dt>
        <dd>{robot?.pose ? `(${fmt(robot.pose.x)}, ${fmt(robot.pose.y)})` : '尚未定位'}</dd>
      </dl>

      <button type="button" onClick={onCancel} disabled={!navigating}>取消</button>

      <button
        type="button"
        className={mode === 'initial_pose' ? 'active' : undefined}
        aria-pressed={mode === 'initial_pose'}
        onClick={() => onModeChange(mode === 'initial_pose' ? 'dispatch' : 'initial_pose')}
      >
        {mode === 'initial_pose' ? '取消設定初始位姿' : '設定初始位姿'}
      </button>
      <p className="hint" data-testid="hint">
        {mode === 'initial_pose'
          ? '設定初始位姿：在車子實際的位置按下，往車頭方向拖曳後放開'
          : '派車：在目標位置按下，往車頭方向拖曳後放開（只點一下＝維持目前朝向）'}
      </p>

      {error && <p className="error" role="status" data-testid="error">{error}</p>}

      <p className="cursor" data-testid="cursor">
        游標 {cursor ? `(${fmt(cursor.x)}, ${fmt(cursor.y)})` : '—'}
      </p>
      <p className="hint">滾輪縮放，右鍵或中鍵拖曳平移</p>
    </aside>
  )
}
