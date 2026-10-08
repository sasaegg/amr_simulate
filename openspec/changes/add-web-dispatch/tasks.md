# Tasks

每個 task 的節奏：說明原因 → 執行（`sudo` 與重建映像由使用者親手執行；檔案由 Claude 撰寫並逐段解釋）→ 驗證 → 寫學習筆記 → commit。使用者要求連續進行，需要手動時才通知。筆記編號見 design.md D8。

整合驗證時若使用者的模擬還開著，以不同 `ROS_DOMAIN_ID`／`IGN_PARTITION`／埠執行，不關閉使用者的程序。

## 1. server 容器與映像

- [x] 1.1 （筆記 26）Dockerfile 加 pip 的 `fastapi`、`uvicorn[standard]`、`httpx`（釘死當下穩定版）與 Node.js 24 LTS 官方 tarball（驗證 SHA256）（D1）；compose 新增 `server` service（不含 GPU、X11、`/data`，掛 `ros_ws` 與 `web`）；`up.sh` 接受 `server`、`exec.sh` 接受 `server`；`.gitignore` 加 `web/node_modules`、`web/dist`。驗證：`docker compose config -q` 通過；`up.sh` 參數錯誤仍顯示用法、非零結束；先以臨時標籤建置映像確認 `node --version` 為 v24、`python3 -c "import fastapi, uvicorn"` 成功
- [ ] 1.2 （筆記 26）**使用者手動**重建映像並啟動三個容器（`up.sh gpu all --build`）。驗證：三個容器在執行；`server` 中 `ros2 topic list` 看得到世界的 `/clock`、`nvidia-smi`／`DISPLAY` 不存在；sim、robot 原有流程（世界、車子系統）照常

## 2. 後端核心（不需要 ROS 的部分）

- [x] 2.1 （筆記 27）建立 `ros_ws/src/amr_server`（ament_python，console script `server`）與 `test_package_boundary.py`；`map_image.py`、`geometry.py`、`state.py`、`bridge.py`（D2）——先寫 pytest（三種顏色、上下翻轉、門檻、yaw 換算、降取樣、地圖範圍）確認失敗再實作。驗證：`colcon build` 成功、pytest 通過
- [x] 2.2 （筆記 29）`api.py`：`create_app(bridges, web_dir)`（D5），REST 路由、WebSocket 每 0.1 秒推送、Pydantic 驗證、地圖範圍檢查、靜態檔與未建置訊息；`test_api.py` 以 FakeBridge＋TestClient 涵蓋 `specs/fleet-server` 每個情境的狀態碼與訊息格式（先寫測試）。驗證：pytest 通過

## 3. 後端 ROS 整合

- [x] 3.1 （筆記 28）`ros_bridge.py`（RosRobotBridge、FleetNode，D4）與 `test_ros_bridge.py`（假 NavigateToPose action server、靜態 TF、假地圖與 plan）：成功、拒絕、放棄、取消（含等待接受中取消）、新目標取代舊目標（舊結果延遲送達不改寫狀態）、位置過期、初始位姿訊息內容與共變異數。驗證：pytest 通過
- [ ] 3.2 （筆記 27）`main.py`（D3：executor 背景執行緒＋uvicorn 主執行緒、結束清理）與 `launch/server.launch.xml`（`robots`、`host`、`port`、`web_dir`、`use_sim_time`）；pytest 檢查 launch 參數與 use_sim_time 以 ros_args 設定。驗證：server 容器中啟動，`curl localhost:8000/api/robots` 回 `amr1`；世界、車子系統、導航執行中時 `curl .../map` 與 yaml 一致、`curl -X POST .../initial_pose` 後 WebSocket（`python3` 簡易用戶端）位置正確、`curl -X POST .../goal` 車輛開到；Ctrl+C 後程序在 2 秒內結束、無殘留
- [ ] 3.3 （筆記 32）`amr_hw_sim/test/test_web_dispatch_smoke.py`（D7 端到端）；amr_hw_sim 的 package.xml 加 `amr_server` test_depend。驗證：`launch_test` 通過、`colcon test` 全部通過

## 4. 前端

- [ ] 4.1 （筆記 30）`web/` 以 Vite react-ts 範本建立（相依見 D6）、`vite.config.ts` proxy、`api.ts`、`useRobotStream.ts`、`geometry.ts`（先寫 Vitest）、`MapView`（地圖底圖、縮放平移、整張地圖、游標座標）、`RobotMarker`、`PlanPath`、`Banner`、`App`。驗證：server 容器 `npm test`、`npx tsc --noEmit` 通過；`npm run dev` 後以軟體渲染 Chromium 或 in-app 瀏覽器開啟，截圖確認地圖方向與 RViz 一致、車輛即時移動、游標在倉庫左下角約 (0, 0)、後端停止時出現斷線橫幅並在恢復後自動重連
- [ ] 4.2 （筆記 31）拖曳派車與設定初始位姿：`MapView` 手勢（D6）、`GoalArrow`、預覽箭頭、`StatusPanel`（狀態、原因、剩餘距離、目標、取消、「設定初始位姿」按鈕與模式提示）；Vitest 涵蓋拖曳送出 x/y/yaw、只點不拖用車的朝向、地圖外不送、初始位姿模式送出後回到派車、導航沒執行時停用、錯誤顯示 `detail`。驗證：測試通過；瀏覽器實際操作：設定初始位姿 → 派車到達 → 中途取消 → 派到箱子內顯示失敗
- [ ] 4.3 （筆記 32）`npm run build` 後由後端提供（`http://localhost:8000/`）；README 新增「7. 網頁派車」（啟動後端、開發模式與建置、`host` 的安全提醒、前端測試指令）、架構圖加入 server 容器、套件表加入 `amr_server` 與 `web/`、截圖 `docs/images/05_web.png`；`docs/開發摘要.md` 更新。驗證：照 README 指令從頭執行一次、截圖確認

## 5. 驗收

- [ ] 5.1 （筆記 33）使用者依手動驗收清單確認：`up.sh gpu all` 三個容器、開啟 `http://localhost:8000/` 看到地圖、網頁設定初始位姿後車出現在正確位置、拖曳派車車輛開到並朝向拖曳方向、路徑顯示、中途取消車停下、派到障礙物內顯示失敗、後端重啟網頁自動恢復、游標座標與 RViz 一致。結果記錄於筆記 33

## Workflow follow-up

- 完成後執行 `openspec archive add-web-dispatch`
- 子專案 3 後半（3D 視角）與子專案 4（儲位、任務佇列、SQLite）另開 change
