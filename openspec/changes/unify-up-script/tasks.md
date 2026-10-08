# Tasks

## 1. 合併啟動腳本

- [ ] 1.1 （筆記 24）新增 `docker/amr_sim/up.sh <gpu|cpu> <sim|robot|all> [compose 參數]`，刪除 `up_gpu.sh`、`up_cpu.sh`。驗證：無參數、只給一個、`foo all`、`gpu foo` 皆顯示用法並以 2 結束且容器沒有被重建；`up.sh gpu all` 兩個容器的 `__GLX_VENDOR_LIBRARY_NAME` 為 nvidia；`up.sh cpu robot` 只重建 robot（robot 為 mesa、sim 的容器 ID 不變）；`up.sh gpu robot` 改回；`--build` 會傳給 compose
- [ ] 1.2 （筆記 24）README、`docs/開發摘要.md` 改用 `up.sh`；學習筆記 06、11、13、23 開頭加更新說明；新增筆記 24（位置參數、`case`、`exec`、`"$@"`、compose `-f` 疊加與指定服務）。驗證：`grep` 專案中（archive 與舊筆記正文以外）沒有 `up_gpu.sh`／`up_cpu.sh`；README 的指令實際執行過

## Workflow follow-up

- 完成後執行 `openspec archive unify-up-script`
