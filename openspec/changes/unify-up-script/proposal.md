# Proposal

## Why

啟動容器原本分成兩個腳本：`up_gpu.sh`（GPU 繪圖）與 `up_cpu.sh`（軟體渲染），而且一律同時啟動 sim、robot 兩個容器。使用者希望合併成一個 `up.sh`，由參數決定繪圖方式與要啟動哪個容器（例如只重建 robot）。

## What Changes

- 新增 `docker/amr_sim/up.sh <gpu|cpu> <sim|robot|all> [docker compose up 的額外參數]`：兩個參數皆必填；`cpu` 套用軟體渲染疊加檔；`sim`／`robot` 只啟動或重建該容器，`all` 兩個都啟動。參數缺少或不合法時顯示用法並以非零碼結束，不做任何事。
- **BREAKING**：刪除 `up_gpu.sh`、`up_cpu.sh`（改用 `up.sh gpu all`、`up.sh cpu all`）。
- README、開發摘要更新指令；舊學習筆記保留原文並加更新說明；新增學習筆記 24。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities
- `sim-runtime`：「世界與車子系統分開的兩個容器」的啟動腳本改為 `up.sh`，可指定繪圖方式與目標容器；「軟體渲染退路」以 `up.sh cpu` 啟動。

## Impact

- `docker/amr_sim/`：新增 `up.sh`，刪除 `up_gpu.sh`、`up_cpu.sh`；compose 檔不變。
- 文件：README、`docs/開發摘要.md`、學習筆記 06／11／13／23 加更新說明、新增筆記 24。
