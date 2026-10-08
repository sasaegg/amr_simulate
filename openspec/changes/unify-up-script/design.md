# Design

## Context

`docker/amr_sim/` 的啟動腳本原為 `up_gpu.sh`（`docker compose up -d`）與 `up_cpu.sh`（加上 `-f compose.software.yaml`），一律啟動兩個容器。需求見 proposal.md。

## Goals / Non-Goals

**Goals:** 一個腳本、兩個必填參數決定繪圖方式與目標容器；行為和原本兩個腳本一致（`all` 時）。

**Non-Goals:** 不改 compose 檔、不改 `exec.sh`、`build.sh`；不加「停止容器」的功能（照舊 `docker compose down`）。

## Decisions

- **位置參數 `<gpu|cpu> <sim|robot|all>`，皆必填、不給預設**：和 `exec.sh` 一致——避免在沒注意時開錯繪圖模式或重建到另一個容器。選字用 `gpu`／`cpu` 而不是 `true`／`false`（使用者選定），指令本身就看得懂。之後的參數原樣交給 `docker compose up`（例如 `--build`）。
- **`cpu` = 疊加 `compose.software.yaml`**：沿用既有的疊加檔（D2），`-f compose.yaml -f compose.software.yaml`。
- **`sim`／`robot` 傳服務名稱給 compose**：compose 只會建立或重建指定的服務；同一專案（`name: amr_sim`）裡另一個容器不受影響，所以可以讓 sim 用 GPU、robot 用 CPU（排查繪圖問題時有用）。`all` 不傳服務名稱。
- **參數錯誤時 `exit 2`**：shell 慣例，2 表示用法錯誤；在呼叫 compose 之前就檢查完，確保不會有任何容器被動到。

## Risks / Trade-offs

- [舊指令 `up_gpu.sh` 失效] → README、開發摘要全部改成新寫法；舊學習筆記開頭加更新說明。
- [`up.sh cpu robot` 後 sim 仍是 GPU，混用時容易忘記目前狀態] → README 說明；需要時用 `docker compose exec <服務> glxinfo -B` 確認。
