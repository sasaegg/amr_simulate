# Spec Delta

## MODIFIED Requirements

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

### Requirement: 軟體渲染退路
系統 SHALL 提供一份疊加設定，使兩個容器可在沒有 NVIDIA GPU 或未安裝 NVIDIA Container Toolkit 的主機上以軟體渲染啟動，且使用時不需修改預設 compose 檔內容。

#### Scenario: 以軟體渲染啟動
- **WHEN** 使用者以 `docker/amr_sim/up.sh cpu all`（預設 compose 檔加上軟體渲染疊加檔）啟動，再啟動世界與車子系統
- **THEN** Gazebo 開啟並模擬，光達資料照常發布，OpenGL renderer 為 `llvmpipe`
