# sim-runtime Specification

## Purpose

定義在 Ubuntu 22.04 主機上執行模擬的使用方式：世界（Gazebo）與車子系統分別在 sim、robot 兩個長駐容器中執行，車子系統以「硬體模式」決定使用虛擬或真實的驅動；以及 GPU 加速繪圖（含軟體渲染退路）、標準 X11 顯示、容器間 ROS 互通與免重建映像的原始碼開發流程。

## Requirements

### Requirement: 世界與車子系統分開的兩個容器
在已完成主機準備（Docker Engine、NVIDIA 驅動、NVIDIA Container Toolkit）的 Ubuntu 22.04 上，系統 SHALL 提供可在任何目錄執行的啟動腳本，在背景建立（映像不存在時先建置）並維持兩個長駐容器：`sim`（世界）與 `robot`（車子系統），此時不啟動任何模擬程序。啟動腳本 SHALL 要求使用者明確指定繪圖方式（`gpu` 或 `cpu`）與目標容器（`sim`、`robot` 或 `all`），只啟動或重建指定的容器；參數缺少或不合法時 SHALL 顯示用法並以非零碼結束，不做任何事。使用者 SHALL 可透過進入腳本指定容器開啟互動式 shell：在 `sim` 中以單一 launch 指令啟動世界（不含車輛），在 `robot` 中以單一 launch 指令啟動車子系統（模擬模式下車輛於此時進入世界）。停止任一側的 launch 不 SHALL 停止容器，也不 SHALL 停止另一側。

#### Scenario: 啟動兩個長駐容器
- **WHEN** 使用者執行 `docker/amr_sim/up.sh gpu all`
- **THEN** 指令立即返回，`sim` 與 `robot` 兩個容器持續執行，且尚未出現 Gazebo 視窗

#### Scenario: 只啟動指定的容器
- **WHEN** 兩個容器都在執行中，使用者執行 `docker/amr_sim/up.sh cpu robot`
- **THEN** 只有 `robot` 被重建為軟體渲染設定，`sim` 容器沒有被重建

#### Scenario: 啟動參數必須指定
- **WHEN** 使用者執行 `docker/amr_sim/up.sh` 時缺少參數，或參數不是 `gpu`／`cpu` 與 `sim`／`robot`／`all`
- **THEN** 顯示用法說明並以非零碼結束，沒有任何容器被建立、重建或停止

#### Scenario: 進入容器必須指定哪一個
- **WHEN** 使用者執行 `docker/amr_sim/exec.sh` 而未指定 `sim` 或 `robot`
- **THEN** 顯示用法說明並以非零碼結束，不進入任何容器

#### Scenario: 啟動世界
- **WHEN** 使用者以 `exec.sh sim` 進入並執行世界的 launch 指令
- **THEN** Gazebo 視窗出現在主機桌面，顯示倉庫場景，且場景中沒有車輛

#### Scenario: 啟動車子系統讓車輛進入世界
- **WHEN** 世界已在執行，使用者以 `exec.sh robot` 進入並執行車子系統的 launch 指令（模擬模式）
- **THEN** 車輛出現在 Gazebo 中啟動參數 `x`、`y`、`yaw` 指定的位置

#### Scenario: 停止車子系統但保留世界
- **WHEN** 使用者在執行車子系統 launch 的 shell 按下 Ctrl+C（即使車輛正在移動）
- **THEN** robot 側的程序全部結束，車輛停下並留在世界中，Gazebo 仍在執行，兩個容器仍在執行

#### Scenario: 重新啟動車子系統不產生重複車輛
- **WHEN** 車輛已在世界中（前一次車子系統已停止），使用者再次啟動車子系統
- **THEN** 既有的車輛停下並被移回這次啟動參數指定的位置與朝向，世界中只有一台該 id 的車輛

#### Scenario: 停止世界
- **WHEN** 使用者在執行世界 launch 的 shell 按下 Ctrl+C
- **THEN** Gazebo 相關程序全部結束、不殘留，`sim` 容器仍在執行

#### Scenario: 關閉容器
- **WHEN** 使用者在 `docker/amr_sim/` 執行 `docker compose down`
- **THEN** 兩個容器在 1 秒內停止並移除

### Requirement: 硬體模式
車子系統 SHALL 依啟動參數 `hardware` 決定使用的驅動，值 SHALL 為 `sim` 或 `real` 且必須明確指定（沒有預設值）。`sim` 時 SHALL 啟動虛擬驅動（車輛進入世界、底盤、光達、IMU 的資料由 Gazebo 提供）並以模擬時間執行；`real` 時目前 SHALL 顯示尚未提供真車驅動的訊息並結束，不啟動任何節點。不合法的值 SHALL 顯示訊息（含收到的值與可用值）並結束，不啟動任何節點。

#### Scenario: 模擬模式
- **WHEN** 以 `hardware:=sim` 啟動車子系統
- **THEN** 虛擬驅動啟動，`/amr1/scan`、`/amr1/odom`、`/amr1/imu` 有資料，robot 側節點使用模擬時間

#### Scenario: 真車模式尚未提供
- **WHEN** 以 `hardware:=real` 啟動車子系統
- **THEN** 訊息指出尚未提供真車驅動，沒有啟動任何節點即結束

#### Scenario: 未指定硬體模式
- **WHEN** 啟動車子系統時沒有指定 `hardware`
- **THEN** 以非零碼結束，訊息指出缺少必要參數 `hardware`

#### Scenario: 不合法的硬體模式
- **WHEN** 以 `hardware:=foo` 啟動車子系統
- **THEN** 訊息指出 `hardware` 必須是 `sim` 或 `real` 並顯示收到的值，沒有啟動任何節點即結束

### Requirement: 車子系統的功能模式
車子系統 SHALL 依啟動參數 `mode` 決定同時帶起的功能：`none`（預設，只有驅動與共用節點）、`navigation`（定位與導航）。建圖一定有人操作，SHALL 不由 `mode` 帶起，而是在車子系統執行中另外啟動（建圖 UI）。不合法的值（含 `mapping`）SHALL 顯示訊息（含收到的值、可用值與建圖的啟動方式）並結束，不啟動任何節點。建圖與導航 SHALL 能在車子系統執行中單獨啟動與停止，不需重啟驅動。

#### Scenario: 預設不帶建圖或導航
- **WHEN** 以 `hardware:=sim` 啟動車子系統，沒有指定 `mode`
- **THEN** 沒有建圖或導航節點，也沒有 `map` 座標系

#### Scenario: 以模式一次啟動
- **WHEN** 以 `hardware:=sim mode:=navigation` 啟動車子系統
- **THEN** 驅動、共用節點與導航節點都啟動

#### Scenario: 不合法的模式
- **WHEN** 以 `hardware:=sim mode:=foo` 啟動車子系統
- **THEN** 訊息指出 `mode` 必須是 `none` 或 `navigation` 並顯示收到的值，沒有啟動任何節點即結束

#### Scenario: 建圖不經由 mode
- **WHEN** 以 `hardware:=sim mode:=mapping` 啟動車子系統
- **THEN** 訊息指出 `mode` 不接受 `mapping` 並提示以建圖 UI 啟動建圖，沒有啟動任何節點即結束

#### Scenario: 單獨切換建圖與導航
- **WHEN** 車子系統以 `mode:=none` 執行中，使用者另外啟動建圖，之後停止建圖再另外啟動導航
- **THEN** 驅動在過程中持續執行，車輛留在原地，不被移回出生點

### Requirement: 車子系統不依賴模擬套件
車子系統的套件（部署到真車上的部分）SHALL 不依賴任何 Gazebo／ros_gz 相關套件與虛擬驅動套件；虛擬驅動只在模擬模式時以套件名稱載入。

#### Scenario: 套件相依不含模擬套件
- **WHEN** 檢查車子系統套件宣告的相依
- **THEN** 其中沒有 `ros_gz*` 開頭的套件，也沒有虛擬驅動套件

### Requirement: 模擬時間由世界提供
模擬時間 `/clock` SHALL 由 `sim` 容器的世界發布到 ROS，且不論世界中有幾台車輛 SHALL 只有一個發布者。

#### Scenario: 唯一的時間來源
- **WHEN** 世界與車子系統都在執行
- **THEN** `/clock` 恰有一個發布者，且位於 `sim` 容器

### Requirement: 選擇場景
要載入的 world SHALL 由世界 launch 參數 `world` 決定，未指定時 SHALL 為 `warehouse_small`。切換場景 SHALL 不需修改 compose 檔或重建映像。

#### Scenario: 以啟動參數切換
- **WHEN** 使用者以 `world:=warehouse_small_edited` 啟動世界
- **THEN** Gazebo 載入 `warehouse_small_edited.sdf`

#### Scenario: 未指定時使用預設值
- **WHEN** 啟動世界時沒有指定 `world`
- **THEN** Gazebo 載入 `warehouse_small.sdf`

#### Scenario: world 不存在
- **WHEN** 指定的 world 檔不存在（例如新增後尚未 `colcon build`）
- **THEN** 訊息顯示嘗試載入的路徑，Gazebo 結束後整個世界 launch 一起結束，不殘留其他程序

### Requirement: 執行設定
兩個容器共用的 ROS 環境變數（含 `ROS_DOMAIN_ID`）SHALL 放在專案 `docker/amr_sim/config/` 的一個環境變數檔；世界與車子系統的設定（world、headless、hardware、robot_id、出生位姿、mode、map）SHALL 以 launch 參數傳入，各參數的預設值寫在 launch 檔中。執行中產生的資料（地圖）SHALL 存放在專案的 `docker/amr_sim/data/` 目錄，以可寫方式掛載到 robot 容器的 `/data`，存入的檔案在主機上屬於使用者。

#### Scenario: 兩個容器取得相同 domain
- **WHEN** 使用者把環境變數檔中的 `ROS_DOMAIN_ID` 改為 42 並重建容器，再分別進入 `sim` 與 `robot` 執行 `ros2 topic list`
- **THEN** 兩個 shell 的 `ROS_DOMAIN_ID` 皆為 42，且在 `robot` 中可看到 `sim` 發布的 `/clock`

#### Scenario: 地圖存到主機
- **WHEN** robot 容器內的程序在 `/data/maps/` 寫入地圖檔
- **THEN** 檔案出現在主機的 `docker/amr_sim/data/maps/`，擁有者為主機使用者

### Requirement: 容器以標準 X11 取得顯示
兩個容器 SHALL 只透過標準 Linux X11 機制（`DISPLAY` 環境變數與 `/tmp/.X11-unix` socket）把圖形畫面送到主機的 X server；容器內程序 SHALL 以與主機使用者相同的 UID 執行。

#### Scenario: 在主機桌面顯示
- **WHEN** 使用者在 Ubuntu 桌面的終端機中啟動世界
- **THEN** Gazebo 視窗出現在同一個桌面上

#### Scenario: 掛載目錄中產生的檔案屬於主機使用者
- **WHEN** 容器在掛載的工作區中建置產生 `build/`、`install/`、`log/`
- **THEN** 主機使用者不需 `sudo` 即可修改與刪除這些檔案

### Requirement: GPU 加速渲染
在具 NVIDIA GPU 的主機上，容器 SHALL 預設使用 NVIDIA GPU 進行 OpenGL 繪圖（含光達感測器所需的渲染）；在雙顯卡主機上 SHALL 由 NVIDIA 而非內顯繪圖。

#### Scenario: 確認由 NVIDIA 繪圖
- **WHEN** 在容器內查詢 OpenGL renderer
- **THEN** renderer 為 NVIDIA GPU（例如 `NVIDIA GeForce RTX 3060`），而不是 `llvmpipe` 或 Intel

#### Scenario: GPU 使用可觀察
- **WHEN** 世界執行中，在主機上查看 NVIDIA GPU 程序清單
- **THEN** 清單中出現 Gazebo 的程序

### Requirement: 軟體渲染退路
系統 SHALL 提供一份疊加設定，使兩個容器可在沒有 NVIDIA GPU 或未安裝 NVIDIA Container Toolkit 的主機上以軟體渲染啟動，且使用時不需修改預設 compose 檔內容。

#### Scenario: 以軟體渲染啟動
- **WHEN** 使用者以 `docker/amr_sim/up.sh cpu all`（預設 compose 檔加上軟體渲染疊加檔）啟動，再啟動世界與車子系統
- **THEN** Gazebo 開啟並模擬，光達資料照常發布，OpenGL renderer 為 `llvmpipe`

### Requirement: 不開 GUI 執行
世界 SHALL 能在不開啟 Gazebo GUI、不需要 X 顯示的情況下執行完整模擬（含光達），供自動化測試使用。

#### Scenario: headless 模擬發布光達資料
- **WHEN** 以 headless 模式啟動世界並以模擬模式啟動車子系統
- **THEN** 不出現任何視窗，且 `/amr1/scan` 照常發布資料

### Requirement: 3D 視窗互動
Gazebo 視窗 SHALL 允許使用者以滑鼠旋轉、平移、縮放 3D 視角觀看場景與車輛。

#### Scenario: 旋轉視角
- **WHEN** 使用者在 Gazebo 視窗中拖曳滑鼠
- **THEN** 視角繞場景旋轉，車輛與光達視覺化持續更新

### Requirement: 主機與容器的 ROS 互通
容器 SHALL 使模擬主機上的其他容器與主機上的 ROS 工具可透過 ROS 2 DDS 發現彼此的 topic 並收到資料；所有容器 SHALL 使用相同的 `ROS_DOMAIN_ID`（預設 0，由 `docker/amr_sim/config/` 的環境變數檔設定）。

#### Scenario: 另一容器可收到資料
- **WHEN** 世界與車子系統執行中，在另一個同設定的容器內對 `/amr1/scan` 執行 echo
- **THEN** 持續收到 `LaserScan` 資料（不只是看得到 topic 名稱）

### Requirement: 原始碼掛載開發
ROS 工作區原始碼 SHALL 以 volume 掛載進容器；修改既有的場景 YAML、world 檔或 Python／launch 檔後，SHALL 無須重建映像，只需重新產生／重新啟動即可生效。新增檔案（例如新的場景或 GUI 另存的 world）SHALL 只需重新執行工作區建置（`colcon build`），不需重建映像。

#### Scenario: 修改場景後重啟
- **WHEN** 使用者修改 `warehouse_small.yaml`、重新執行產生指令並重啟世界
- **THEN** Gazebo 顯示修改後的場景，且未重新建置 Docker 映像
