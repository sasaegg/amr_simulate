// 後端 REST API（amr_server/api.py）。前端只和後端溝通，不直連 ROS。
import type { MapInfo, Pose } from './types'

/** 後端回傳非 2xx：detail 是後端給的原因（一句中文），直接顯示給操作者。 */
export class ApiError extends Error {
  status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, '無法連線到後端')
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      // 回應不是 JSON：用狀態碼當原因
    }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export function getMapInfo(robotId: string): Promise<MapInfo> {
  return request('GET', `/robots/${robotId}/map`)
}

/** 地圖圖片網址；加上版本號，地圖換了瀏覽器才不會用舊的快取。 */
export function mapImageUrl(robotId: string, version: number): string {
  return `/api/robots/${robotId}/map.png?v=${version}`
}

export function sendGoal(robotId: string, pose: Pose): Promise<unknown> {
  return request('POST', `/robots/${robotId}/goal`, pose)
}

export function cancelGoal(robotId: string): Promise<unknown> {
  return request('DELETE', `/robots/${robotId}/goal`)
}

export function setInitialPose(robotId: string, pose: Pose): Promise<unknown> {
  return request('POST', `/robots/${robotId}/initial_pose`, pose)
}
