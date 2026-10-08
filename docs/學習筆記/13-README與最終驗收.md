# 13 README 與最終驗收

檔案：[`README.md`](../../README.md)、[`docs/開發摘要.md`](../開發摘要.md)

## 為什麼要做

README 是專案的入口：別人（或之後的自己）clone 下來，照著 README 從零就能跑起來。最終驗收由使用者親自操作——有些事只能用眼睛確認（3D 畫面、鍵盤開車的手感、RViz 的顯示），自動測試無法取代。

## README 的結構

架構圖與套件分工 → 主機準備（連到筆記 01–03）→ 建置與啟動（兩個容器、兩個終端機）→ 設定（launch 參數表、`ros.env`、UID）→ 地圖（產生器、GUI 另存 `_edited`）→ 開車與觀察（teleop、RViz、Gazebo 光束）→ 軟體渲染 → 測試 → 疑難排解。

寫 README 的原則：每個指令都要實際跑過一次（筆記 08 的教訓：`python3 -m` 那行少了 `__main__` 區塊）；疑難排解收錄實際踩過的坑。驗證方式是從 `docker/amr_sim/build.sh` 開始照做一遍。

## 自動驗證已完成的項目（Claude，2026-10-08）

以下已用腳本在 headless 世界上驗證，詳見筆記 11、12：

- 兩個容器啟動、`exec.sh` 用法、`ROS_DOMAIN_ID` 一致與隔離、`docker compose down` 0.21 s
- 容器內 renderer：GPU 模式 RTX 3060、CPU 模式 llvmpipe（兩個容器都是）
- 世界無車 → 車子系統讓車出現在 (1, 1)；`/clock` 一個發布者
- 停止車子系統時車輛停下並留在世界；重啟移回出生點且只有一台；先啟動驅動再啟動世界也能生成
- 未指定 `hardware` 時結束碼 1；`hardware:=real`／不合法值顯示訊息且不啟動任何節點（launch 改 XML 後重新驗證）
- namespace、頻率、TF、停送 0.86 s 停車、超速截斷 1.0 m/s、光達讀值吻合幾何、暫停時 `/clock` 停止
- world 不存在時印出路徑、launch 自行結束；新增 world build 後可載入
- `colcon test`：117 tests, 0 failures（launch 改 XML 後；冒煙測試 9 項通過）

## 使用者手動驗收清單（task 7.2）

照 [`README.md`](../../README.md) 操作，逐項確認後把 ⬜ 改成 ✅ 並記下觀察：

| # | 項目 | 怎麼做 | 結果 |
|---|---|---|---|
| 1 | 啟動 | `up_gpu.sh`（會重建容器，拿掉 `/config` 掛載）→ `exec.sh sim` 執行 `ros2 launch amr_worlds world.launch.xml` → `exec.sh robot` 執行 `ros2 launch amr_bringup robot.launch.xml hardware:=sim x:=1 y:=1` | ⬜ |
| 2 | 世界先無車、之後車輛出現 | 世界啟動時沒有車；車子系統啟動後車出現在左下角 (1, 1)，車頭朝 +x | ⬜ |
| 3 | 3D 互動 | Gazebo 視窗中左鍵拖曳旋轉、中鍵平移、滾輪縮放，流暢 | ⬜ |
| 4 | GPU | 容器內 `glxinfo -B` 的 renderer 是 RTX 3060；Gazebo 執行時主機 `nvidia-smi` 看得到 Gazebo | ⬜ |
| 5 | 光達光束 | Gazebo 右上 ⋮ → Visualize Lidar → Topic `/amr1/scan`（必要時按 refresh），光束打到牆 | ⬜ |
| 6 | 鍵盤開車 | robot 容器另開 shell 執行 teleop（README），i 前進、j/l 轉向；車子照指令走 | ⬜ |
| 7 | 放開後停車 | 關掉 teleop（Ctrl+C），車子 1 秒內停下 | ⬜ |
| 8 | RViz | robot 容器 `rviz2`，Fixed Frame `amr1/odom`，加 LaserScan（`/amr1/scan`）、TF、RobotModel（`/amr1/robot_description`）；看得到掃到牆與貨架 | ⬜ |
| 9 | 停止車子系統 | robot launch 按 Ctrl+C：車子停在原地、Gazebo 仍在；再啟動一次，車回到 (1, 1) 且只有一台；改用 `x:=3 y:=1 yaw:=1.57` 啟動，車移到 (3, 1) 朝 +y | ⬜ |
| 10 | 改場景 | 改 `warehouse_small.yaml`（例如移動一個障礙物）→ `gen_world` → 重啟世界，看到變化；過程中沒有重建映像 | ⬜ |
| 11 | GUI 另存 world | Gazebo 中修改並另存為 `ros_ws/src/amr_worlds/worlds/warehouse_small_edited.sdf` → `colcon build` → 以 `world:=warehouse_small_edited` 重啟世界可載入 | ⬜ |
| 12 | 軟體渲染 | `up_cpu.sh` 後重啟世界與車子系統，可運作（較慢）；`up_gpu.sh` 切回 | ⬜ |
| 13 | exec.sh | 不給參數時顯示用法 | ⬜ |
| 14 | 參數錯誤 | `robot.launch.xml` 不給 `hardware`、給 `hardware:=real` 各試一次，看訊息；關掉 Gazebo 視窗時世界的 launch 跟著結束 | ⬜ |

驗收完成後：tasks.md 的 7.2 打勾、`docs/開發摘要.md` 子專案 1 狀態改為完成，再執行 `openspec archive add-sim-environment`。

## 面試追問

**Q：自動測試都過了，為什麼還要手動驗收？**
A：自動測試驗證可量化的行為（頻率、距離、時間）；畫面是否正確、操作手感、工具（RViz、GUI 外掛）的實際使用流程只能人來看。兩者互補。

**Q：README 怎麼確保是對的？**
A：每個指令都實際執行過；最後從 build 開始照 README 完整做一次。疑難排解收錄真的遇過的問題。

**Q：這個子專案做完，交付了什麼？**
A：一個可重現的模擬環境：Docker 化（GPU／軟體渲染）、可用 YAML 編輯並版控的倉庫地圖、帶光達與 IMU 的差速車、與真車共用的車子系統架構（硬體模式切換），以及 117 個自動測試與逐步學習筆記。
