# Tasks

每個 task：說明原因 → 實作（Claude）→ 驗證 → 學習筆記 → commit。整合驗證時以不同 `ROS_DOMAIN_ID`／`IGN_PARTITION` 執行，不關閉使用者的程序。

## 1. 地圖改寫核心

- [x] 1.1 （筆記 25）新增 `amr_navigation/amr_navigation/map_origin.py`（D1、D4）與 pytest（D6 純 Python 部分）：先寫測試確認失敗，再實作。驗證：`env -i` 下 pytest 通過
- [x] 1.2 （筆記 25）新增 `ros_ws/src/amr_interfaces`（`SetMapOrigin.srv`）與 `amr_navigation` 的 `map_origin_server` 節點（console script，參數 `maps_dir`）；測試服務成功與失敗回報；套件邊界測試涵蓋新套件。驗證：`colcon build` 成功、`ros2 interface show amr_interfaces/srv/SetMapOrigin` 正確、服務測試通過

## 2. 地圖原點 UI

- [x] 2.1 （筆記 25）`amr_rviz_plugins`：`MapOriginPanel`、`config/map_origin.rviz`、`launch/map_origin_ui.launch.xml`（D3）；gtest（pluginlib 載入、對齊角度）、pytest（設定檔 topic 帶 namespace、launch 內容）。驗證：`colcon build` 無警告、測試通過；以乾淨映像在 Xvfb 啟動 UI、xdotool 點選拖曳並套用到複製的地圖，截圖確認座標軸移到新原點、檔案與備份正確

## 3. repo 地圖與既有流程

- [x] 3.1 （筆記 25）以服務把 `warehouse_small` 的原點改為 (−1, −1, 0)（D5）；導航冒煙測試改用世界座標（初始位姿 (1, 1, 0)、目標 (10, 1)、障礙物 (7, 4)），移除 OFFSET 換算；`.gitignore` 加 `*.bak.*`。驗證：`.pgm` 內容不變、`.yaml` origin 改變；導航冒煙測試通過；`colcon test` 全部通過
- [x] 3.2 （筆記 25）README：第 5 步移除 (1, 1) 慣例、新增「5.3 標地圖原點」、第 6 步說明地圖座標＝倉庫座標；add-navigation design D4、筆記 16／17 的慣例處加註更新；開發摘要。驗證：README 指令實際執行過；`grep` 專案中（archive 與加註處以外）沒有「世界座標 = 地圖座標 + (1, 1)」

## 4. 驗收

- [ ] 4.1 （筆記 25）使用者以 `map_origin_ui.launch.xml` 在複製出的地圖上點選、套用，確認座標軸移到新原點、備份檔存在；以 `warehouse_small` 導航時 RViz 座標與 Gazebo 世界座標一致。結果記錄於筆記 25

## Workflow follow-up

- 完成後執行 `openspec archive add-map-origin`
