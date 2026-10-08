# Proposal

## Why

子專案 2 完成後，車子已能在地圖上定位並導航，但所有操作（給初始位姿、指定目標）都要開 RViz、懂 ROS。子專案 3 要提供一個操作者用的網頁：看到地圖與車輛即時位置、在地圖上點選派車——這也是子專案 4（儲位、任務佇列）的基礎：之後的任務都經由同一個後端送到車上。

本 change 只做 2D（使用者決定，2026-10-08）：3D 視角與 SQLite 資料庫留到之後。

## What Changes

- 新增**中控容器 `server`**（同一個映像）：與世界（sim）、車子系統（robot）並列，代表管理所有車輛的中控電腦；不需要 GPU、X11 與 `/data`。`up.sh` 的目標容器新增 `server`，`all` 改為三個；`exec.sh` 可進入 `server`。
- 映像新增 Python 套件 FastAPI、uvicorn（pip，釘死版本）與 Node.js 24 LTS（官方 tarball，驗證 SHA256）。**需要重建映像。**
- 新增後端套件 `ros_ws/src/amr_server`（ament_python）：一個程序同時是 ROS 節點與 HTTP 伺服器。
  - 每台車一個 RobotBridge：訂閱 `/<id>/map`（Transient Local）與 `/<id>/plan`、以 TF 查 `map → <id>/base_footprint` 取得位置、`/<id>/navigate_to_pose` action client、發布 `/<id>/initialpose`。
  - REST：車輛清單、地圖資訊與 PNG、派車、取消、設定初始位姿；WebSocket：每 0.1 秒推送所有車輛的位置、目標、導航狀態、剩餘距離、規劃路徑、地圖版本。
  - 提供前端建置後的靜態檔（`web/dist`）。
  - `server.launch.xml`：參數 `robots`（逗號分隔，預設 `amr1`）、`host`（預設 `127.0.0.1`）、`port`（預設 8000）、`use_sim_time`。
- 新增前端 `web/`（React + Vite + TypeScript）：SVG 2D 地圖（縮放、平移）、車輛、目標箭頭、規劃路徑；**RViz 式拖曳**（按下＝位置、拖曳＝方向）派車與設定初始位姿；側欄顯示狀態、剩餘距離、取消按鈕、游標座標；後端斷線、尚未收到地圖、尚未定位、導航沒在執行時顯示橫幅。前端只與後端溝通，不直連 ROS。
- 測試：後端單元測試（地圖轉圖片、API 以假 bridge 測）、bridge 整合測試（假 action server、靜態 TF）、端到端冒煙測試（世界 + 車子系統 + 導航 + 後端，經 HTTP／WebSocket 派車並比對 Gazebo 真實位置）、前端 Vitest。
- 文件：README 新增「7. 網頁派車」；學習筆記 26 起。

## Capabilities

### New Capabilities
- `fleet-server`：中控後端對外提供的車輛介面——車輛狀態、地圖、即時位置推送、派車與取消、設定初始位姿，以及錯誤回報（車子系統或導航未執行、輸入不合法）。
- `operator-web`：操作者網頁——2D 地圖顯示、即時車輛位置與路徑、拖曳派車與設定初始位姿、導航狀態與取消、連線與狀態提示。

### Modified Capabilities
- `sim-runtime`：「世界與車子系統分開的兩個容器」改為三個容器（新增中控 `server`），啟動與進入腳本接受 `server`；「執行設定」加入中控的 launch 參數（`robots`、`host`、`port`、`use_sim_time`）。

## Impact

- 新增 `ros_ws/src/amr_server`、`web/`；修改 `docker/amr_sim/{Dockerfile,compose.yaml,up.sh,exec.sh}`（軟體渲染疊加檔不需要改：server 本來就不用 GPU）。
- 映像變大（Node.js 約 100 MB）；需要使用者重建映像（`build.sh` 或 `up.sh ... --build`）。
- 新增 HTTP 埠 8000（後端）與 5173（Vite 開發伺服器），皆在主機網路（`network_mode: host`）。
- `web/node_modules`、`web/dist` 不進 git。
- 不修改車子系統（robot 容器）的任何套件：後端只使用既有的 topic、TF 與 action。
