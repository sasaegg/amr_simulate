# Proposal

## Why

子專案 1 已有可開車的模擬 AMR，但車子只會照速度指令移動，不知道自己在倉庫的哪裡。子專案 2 要讓車子系統能建出倉庫地圖、在地圖上定位，並自動導航到指定位置——這是之後網頁派車（子專案 3）與任務佇列（子專案 4）的基礎。

## What Changes

- 新增車子系統套件 `amr_navigation`（真車也會安裝，不依賴任何模擬套件）：
  - 建圖：以 slam_toolbox（非同步線上建圖）配合手動 teleop 建立 2D 佔據格地圖；以 Nav2 的 map_saver 存成 `.pgm` + `.yaml`。
  - 導航：自己撰寫的 XML launch 逐一啟動 map_server、AMCL 與 Nav2 各節點（NavFn 全域規劃、DWB 局部控制、behavior、bt_navigator、velocity_smoother、lifecycle_manager）；初始位姿由使用者在 RViz 以 2D Pose Estimate 給定。
  - 參數檔以 launch 代換帶入 `robot_id`，所有節點在 namespace `<id>` 下，地圖 frame `map` 為多車共用。
  - 附 RViz 設定檔。
- 新增 RViz 建圖面板外掛 `amr_rviz_plugins`（使用者要求）：輸入地圖名稱、按鈕存圖（呼叫 Nav2 `map_saver_server` 的存圖服務），並顯示建圖狀態；`mapping_ui.launch.xml` 一次開啟建圖與 RViz。
- 車子系統中控 `robot.launch.xml` 新增 `mode`（`none`／`mapping`／`navigation`，預設 `none`）與 `map` 參數；建圖與導航的 launch 也可在中控執行中單獨啟動與停止。
- robot 容器新增執行資料目錄掛載 `docker/amr_sim/data/`（容器內 `/data`）；地圖存在 `docker/amr_sim/data/maps/` 並納入版控，附一張以 teleop 建出的 `warehouse_small` 地圖。
- 新增建圖與導航的整合冒煙測試（放在模擬側套件 `amr_hw_sim`）。
- 文件：README 建圖／存圖／導航流程與疑難排解；每個步驟一篇學習筆記（15 起）。

## Capabilities

### New Capabilities
- `mapping`：以 2D 光達與里程計線上建立佔據格地圖、存圖（指令、服務、RViz 面板按鈕）與地圖檔格式。
- `navigation`：在既有地圖上定位（初始位姿、持續定位）、規劃路徑並自動行駛到目標、避開地圖上沒有的障礙物、無法到達時的回報。

### Modified Capabilities
- `sim-runtime`：「執行設定」新增車子系統的 `mode`、`map` 參數，以及 robot 容器的執行資料目錄（地圖）掛載。

## Impact

- 新套件 `ros_ws/src/amr_navigation`、`ros_ws/src/amr_rviz_plugins`（C++ RViz 外掛）；修改 `amr_bringup/launch/robot.launch.xml` 與其測試、`docker/amr_sim/compose.yaml`（robot 掛載 `./data:/data`）。
- 新增 `docker/amr_sim/data/maps/`（`.pgm` 已在 `.gitattributes` 標為 binary）。
- 相依：`slam_toolbox`、`nav2_*`（映像已安裝，不需重建映像）。
- 測試：`amr_hw_sim` 新增建圖、導航冒煙測試（執行時間較長，約 1–2 分鐘）。
