import { useCallback, useEffect, useState } from 'react'
import { ApiError, cancelGoal, getMapInfo, mapImageUrl, sendGoal, setInitialPose } from './api'
import { Banner } from './components/Banner'
import { MapView } from './components/MapView'
import { StatusPanel } from './components/StatusPanel'
import type { GestureMode, MapInfo, Point, Pose } from './types'
import { useRobotStream } from './useRobotStream'

export default function App() {
  const { connected, robots } = useRobotStream()
  const robotIds = Object.keys(robots)
  const [selected, setSelected] = useState<string | null>(null)
  const robotId = selected ?? robotIds[0] ?? ''
  const robot = robots[robotId]

  const [mapInfo, setMapInfo] = useState<MapInfo | null>(null)
  const [mode, setMode] = useState<GestureMode>('dispatch')
  const [error, setError] = useState<string | null>(null)
  const [cursor, setCursor] = useState<Point | null>(null)

  // 地圖版本變了（或換車）才重新抓地圖資訊；圖片網址帶版本號，瀏覽器會重新載入
  const mapVersion = robot?.map_ready ? robot.map_version : 0
  useEffect(() => {
    if (!robotId || !mapVersion) {
      setMapInfo(null)
      return
    }
    let current = true
    getMapInfo(robotId)
      .then((info) => current && setMapInfo(info))
      .catch((e: ApiError) => current && setError(e.message))
    return () => { current = false }
  }, [robotId, mapVersion])

  const report = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  const onPose = useCallback((gesture: GestureMode, pose: Pose) => {
    setError(null)
    if (gesture === 'initial_pose') {
      setMode('dispatch')                       // 設定一次就回到派車
      setInitialPose(robotId, pose).catch(report)
    } else {
      sendGoal(robotId, pose).catch(report)
    }
  }, [robotId])

  const onCancel = () => {
    setError(null)
    cancelGoal(robotId).catch(report)
  }

  // 派車要導航準備好；設定初始位姿只要有地圖（AMCL 不管導航有沒有啟動）
  const gestureEnabled = mode === 'initial_pose' ? !!robot?.map_ready : !!robot?.nav_ready

  return (
    <div className="app">
      <header>
        <h1>AMR 派車</h1>
        <Banner connected={connected} robot={robot} />
      </header>
      <main>
        <MapView
          info={mapInfo}
          imageUrl={mapInfo ? mapImageUrl(robotId, mapInfo.version) : null}
          robot={robot}
          mode={mode}
          gestureEnabled={connected && gestureEnabled}
          onPose={onPose}
          onCursor={setCursor}
        />
        <StatusPanel
          robotIds={robotIds}
          robotId={robotId}
          onRobotChange={setSelected}
          robot={robot}
          mode={mode}
          onModeChange={setMode}
          onCancel={onCancel}
          error={error}
          cursor={cursor}
        />
      </main>
    </div>
  )
}
