import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { RobotState } from '../types'
import { StatusPanel } from './StatusPanel'

const base: RobotState = {
  pose: { x: 1, y: 1, yaw: 0 }, goal: null, status: 'idle', message: '', distance_remaining: null,
  plan: [], map_version: 1, map_ready: true, nav_ready: true,
}

function setup(robot: RobotState, extra: Partial<Parameters<typeof StatusPanel>[0]> = {}) {
  const handlers = { onRobotChange: vi.fn(), onModeChange: vi.fn(), onCancel: vi.fn() }
  render(<StatusPanel robotIds={['amr1']} robotId="amr1" robot={robot} mode="dispatch"
                      error={null} cursor={null} {...handlers} {...extra} />)
  return handlers
}

describe('側欄', () => {
  it('導航中：狀態、剩餘距離、目標，取消可按', () => {
    const h = setup({ ...base, status: 'navigating', goal: { x: 10, y: 1, yaw: 0 }, distance_remaining: 6.84 })
    expect(screen.getByTestId('status')).toHaveTextContent('導航中')
    expect(screen.getByText('6.8 m')).toBeInTheDocument()
    expect(screen.getByText('(10.00, 1.00)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(h.onCancel).toHaveBeenCalled()
  })

  it('不在導航中：取消停用', () => {
    setup(base)
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled()
  })

  it('失敗：顯示原因', () => {
    setup({ ...base, status: 'failed', message: 'Nav2 放棄（到不了或卡住）' })
    expect(screen.getByTestId('status')).toHaveTextContent('失敗')
    expect(screen.getByTestId('message')).toHaveTextContent('Nav2 放棄')
  })

  it('設定初始位姿按鈕切換模式，模式中有提示', () => {
    const h = setup(base)
    fireEvent.click(screen.getByRole('button', { name: '設定初始位姿' }))
    expect(h.onModeChange).toHaveBeenCalledWith('initial_pose')
  })

  it('初始位姿模式中可取消回到派車', () => {
    const h = setup(base, { mode: 'initial_pose' })
    expect(screen.getByTestId('hint')).toHaveTextContent('設定初始位姿：')
    fireEvent.click(screen.getByRole('button', { name: '取消設定初始位姿' }))
    expect(h.onModeChange).toHaveBeenCalledWith('dispatch')
  })

  it('錯誤訊息與游標座標', () => {
    setup(base, { error: 'amr1 的導航還在啟動', cursor: { x: 7.321, y: 4.1 } })
    expect(screen.getByTestId('error')).toHaveTextContent('導航還在啟動')
    expect(screen.getByTestId('cursor')).toHaveTextContent('(7.32, 4.10)')
  })
})
