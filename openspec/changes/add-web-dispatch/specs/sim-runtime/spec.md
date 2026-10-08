# Spec Delta

## REMOVED Requirements

### Requirement: 世界與車子系統分開的兩個容器
**Reason**: 新增中控容器 `server`，容器由兩個變成三個；以下方「世界、車子系統與中控分開的容器」取代（原有情境全部保留，改寫為三個容器）。
**Migration**: `up.sh` 的 `all` 改為啟動三個容器；只要兩個時以 `up.sh <gpu|cpu> sim`、`up.sh <gpu|cpu> robot` 分別啟動。

## ADDED Requirements

### Requirement: 世界、車子系統與中控分開的容器
在已完成主機準備的 Ubuntu 22.04 上，系統 SHALL 提供可在任何目錄執行的啟動腳本，在背景建立（映像不存在時先建置）並維持三個長駐容器：`sim`（世界）、`robot`（車子系統）與 `server`（中控：後端與網頁），此時不啟動任何程序；`server` SHALL 不需要 GPU、X11 顯示與執行資料目錄。啟動腳本 SHALL 要求明確指定繪圖方式（`gpu`／`cpu`）與目標容器（`sim`／`robot`／`server`／`all`），只啟動或重建指定的容器，參數缺少或不合法時顯示用法並以非零碼結束。進入腳本 SHALL 要求指定容器；各容器以單一 launch 指令啟動各自的程序，停止任一側不影響容器與其他容器的程序。

#### Scenario: 啟動三個長駐容器
- **WHEN** 使用者執行 `docker/amr_sim/up.sh gpu all`
- **THEN** 指令立即返回，`sim`、`robot`、`server` 三個容器持續執行，且尚未出現 Gazebo 視窗

#### Scenario: 只啟動指定的容器
- **WHEN** 三個容器都在執行中，使用者執行 `docker/amr_sim/up.sh cpu robot`
- **THEN** 只有 `robot` 被重建為軟體渲染設定，`sim` 與 `server` 容器沒有被重建

#### Scenario: 中控不需要 GPU 與顯示
- **WHEN** 檢查 `server` 容器的設定
- **THEN** 沒有 GPU 裝置要求、沒有掛載 X11 socket 與執行資料目錄

#### Scenario: 啟動參數必須指定
- **WHEN** 使用者執行 `docker/amr_sim/up.sh` 時缺少參數，或參數不是 `gpu`／`cpu` 與 `sim`／`robot`／`server`／`all`
- **THEN** 顯示用法說明並以非零碼結束，沒有任何容器被建立、重建或停止

#### Scenario: 進入容器必須指定哪一個
- **WHEN** 使用者執行 `docker/amr_sim/exec.sh` 而未指定 `sim`、`robot` 或 `server`
- **THEN** 顯示用法說明並以非零碼結束，不進入任何容器

#### Scenario: 啟動世界
- **WHEN** 使用者以 `exec.sh sim` 進入並執行世界的 launch 指令
- **THEN** Gazebo 視窗出現在主機桌面，顯示倉庫場景，且場景中沒有車輛

#### Scenario: 啟動車子系統讓車輛進入世界
- **WHEN** 世界已在執行，使用者以 `exec.sh robot` 進入並執行車子系統的 launch 指令（模擬模式）
- **THEN** 車輛出現在 Gazebo 中啟動參數 `x`、`y`、`yaw` 指定的位置

#### Scenario: 啟動後端
- **WHEN** 使用者以 `exec.sh server` 進入並執行後端的 launch 指令
- **THEN** 主機瀏覽器可開啟 `http://localhost:8000/`，且停止後端不影響世界與車子系統

#### Scenario: 停止車子系統但保留世界
- **WHEN** 使用者在執行車子系統 launch 的 shell 按下 Ctrl+C（即使車輛正在移動）
- **THEN** robot 側的程序全部結束，車輛停下並留在世界中，Gazebo 仍在執行，所有容器仍在執行

#### Scenario: 重新啟動車子系統不產生重複車輛
- **WHEN** 車輛已在世界中（前一次車子系統已停止），使用者再次啟動車子系統
- **THEN** 既有的車輛停下並被移回這次啟動參數指定的位置與朝向，世界中只有一台該 id 的車輛

#### Scenario: 停止世界
- **WHEN** 使用者在執行世界 launch 的 shell 按下 Ctrl+C
- **THEN** Gazebo 相關程序全部結束、不殘留，`sim` 容器仍在執行

#### Scenario: 關閉容器
- **WHEN** 使用者在 `docker/amr_sim/` 執行 `docker compose down`
- **THEN** 所有容器在 1 秒內停止並移除

## MODIFIED Requirements

### Requirement: 執行設定
所有容器共用的 ROS 環境變數（含 `ROS_DOMAIN_ID`）SHALL 放在專案 `docker/amr_sim/config/` 的一個環境變數檔；世界、車子系統與中控的設定（world、headless、hardware、robot_id、出生位姿、mode、map；中控的 robots、host、port、use_sim_time）SHALL 以 launch 參數傳入，各參數的預設值寫在 launch 檔中。執行中產生的資料（地圖）SHALL 存放在專案的 `docker/amr_sim/data/` 目錄，以可寫方式掛載到 robot 容器的 `/data`，存入的檔案在主機上屬於使用者。

#### Scenario: 兩個容器取得相同 domain
- **WHEN** 使用者把環境變數檔中的 `ROS_DOMAIN_ID` 改為 42 並重建容器，再分別進入 `sim` 與 `robot` 執行 `ros2 topic list`
- **THEN** 兩個 shell 的 `ROS_DOMAIN_ID` 皆為 42，且在 `robot` 中可看到 `sim` 發布的 `/clock`

#### Scenario: 中控取得相同 domain
- **WHEN** 世界執行中，進入 `server` 執行 `ros2 topic list`
- **THEN** `ROS_DOMAIN_ID` 與 `sim`、`robot` 相同，且看得到 `/clock`

#### Scenario: 地圖存到主機
- **WHEN** robot 容器內的程序在 `/data/maps/` 寫入地圖檔
- **THEN** 檔案出現在主機的 `docker/amr_sim/data/maps/`，擁有者為主機使用者

#### Scenario: 中控參數
- **WHEN** 以 `ros2 launch amr_server server.launch.xml port:=8100` 啟動後端
- **THEN** 後端在 8100 埠提供服務，管理的車輛為預設的 `amr1`
