# Spec Delta

## Purpose

定義在 Ubuntu 22.04 主機上以容器一鍵啟動模擬的使用方式：GPU 加速繪圖（含軟體渲染退路）、以標準 X11 顯示 Gazebo 3D 視窗、容器與主機／其他容器間的 ROS 互通，以及免重建映像的原始碼開發流程。

## ADDED Requirements

### Requirement: 一鍵啟動模擬
在已完成主機準備（Docker Engine、NVIDIA 驅動、NVIDIA Container Toolkit）的 Ubuntu 22.04 上，於專案根目錄執行單一 compose 指令 SHALL 建置（若需要）並啟動模擬容器，載入預設場景 `warehouse_small` 並生成 `amr1`。

#### Scenario: 首次啟動
- **WHEN** 使用者在專案根目錄執行 `docker compose up sim`
- **THEN** 映像建置完成後 Gazebo 視窗出現在主機桌面，顯示倉庫場景與車輛

#### Scenario: 關閉模擬
- **WHEN** 使用者在執行 compose 的終端機按下 Ctrl+C
- **THEN** 模擬相關程序全部結束，容器停止，不殘留 Gazebo 程序

### Requirement: 選擇場景
啟動時 SHALL 可透過環境變數 `WORLD` 或 launch 參數 `world` 指定要載入的 world；未指定時使用 `warehouse_small`。

#### Scenario: 指定其他 world
- **WHEN** 使用者以 `WORLD=warehouse_small_edited docker compose up sim` 啟動
- **THEN** Gazebo 載入 `warehouse_small_edited.sdf`

### Requirement: 容器以標準 X11 取得顯示
模擬容器 SHALL 只透過標準 Linux X11 機制（`DISPLAY` 環境變數與 `/tmp/.X11-unix` socket）把圖形畫面送到主機的 X server（Wayland 桌面下為 XWayland）；容器內程序 SHALL 以與主機使用者相同的 UID 執行。

#### Scenario: 在主機桌面顯示
- **WHEN** 使用者在 Ubuntu 桌面的終端機中啟動模擬
- **THEN** Gazebo 視窗出現在同一個桌面上

#### Scenario: 掛載目錄中產生的檔案屬於主機使用者
- **WHEN** 容器在掛載的工作區中建置產生 `build/`、`install/`、`log/`
- **THEN** 主機使用者不需 `sudo` 即可修改與刪除這些檔案

### Requirement: GPU 加速渲染
在具 NVIDIA GPU 的主機上，模擬容器 SHALL 預設使用 NVIDIA GPU 進行 OpenGL 繪圖（含光達感測器所需的渲染）；在雙顯卡主機上 SHALL 由 NVIDIA 而非內顯繪圖。

#### Scenario: 確認由 NVIDIA 繪圖
- **WHEN** 在模擬容器內查詢 OpenGL renderer
- **THEN** renderer 為 NVIDIA GPU（例如 `NVIDIA GeForce RTX 3060`），而不是 `llvmpipe` 或 Intel

#### Scenario: GPU 使用可觀察
- **WHEN** 模擬執行中，在主機上查看 NVIDIA GPU 程序清單
- **THEN** 清單中出現 Gazebo 的程序

### Requirement: 軟體渲染退路
系統 SHALL 提供一份疊加設定，使模擬可在沒有 NVIDIA GPU 或未安裝 NVIDIA Container Toolkit 的主機上以軟體渲染啟動，且使用時不需修改預設 compose 檔內容。

#### Scenario: 以軟體渲染啟動
- **WHEN** 使用者以預設 compose 檔加上軟體渲染疊加檔啟動模擬
- **THEN** Gazebo 開啟並模擬，光達資料照常發布，OpenGL renderer 為 `llvmpipe`

### Requirement: 不開 GUI 執行
系統 SHALL 能在不開啟 Gazebo GUI、不需要 X 顯示的情況下執行完整模擬（含光達），供自動化測試使用。

#### Scenario: headless 模擬發布光達資料
- **WHEN** 以 headless 模式啟動模擬
- **THEN** 不出現任何視窗，且 `/amr1/scan` 照常發布資料

### Requirement: 3D 視窗互動
Gazebo 視窗 SHALL 允許使用者以滑鼠旋轉、平移、縮放 3D 視角觀看場景與車輛。

#### Scenario: 旋轉視角
- **WHEN** 使用者在 Gazebo 視窗中拖曳滑鼠
- **THEN** 視角繞場景旋轉，車輛與光達視覺化持續更新

### Requirement: 主機與容器的 ROS 互通
模擬容器 SHALL 使模擬主機上的其他容器（後續子專案的導航、後端）與主機上的 ROS 工具可透過 ROS 2 DDS 發現模擬的 topic 並收到資料；所有容器 SHALL 使用相同的 `ROS_DOMAIN_ID`（預設 0，可設定）。

#### Scenario: 另一容器可收到資料
- **WHEN** 模擬執行中，在另一個同設定的容器內對 `/amr1/scan` 執行 echo
- **THEN** 持續收到 `LaserScan` 資料（不只是看得到 topic 名稱）

### Requirement: 原始碼掛載開發
ROS 工作區原始碼 SHALL 以 volume 掛載進容器；修改場景 YAML、world 檔或 Python／launch 檔後，SHALL 無須重建映像，只需重新產生／重新啟動即可生效。

#### Scenario: 修改場景後重啟
- **WHEN** 使用者修改 `warehouse_small.yaml`、重新執行產生指令並重啟模擬
- **THEN** Gazebo 顯示修改後的場景，且未重新建置 Docker 映像
