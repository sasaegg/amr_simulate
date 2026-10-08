# 16 slam_toolbox 建圖

檔案：[`slam_toolbox.yaml`](../../ros_ws/src/amr_navigation/config/slam_toolbox.yaml)、[`mapping.launch.xml`](../../ros_ws/src/amr_navigation/launch/mapping.launch.xml)、[`navigate.rviz`](../../ros_ws/src/amr_navigation/config/navigate.rviz)、[`test_mapping_smoke.py`](../../ros_ws/src/amr_hw_sim/test/test_mapping_smoke.py)

子專案 2 task 2.1、2.2、2.4、2.5。

## 為什麼要做

導航要先有地圖。SLAM（Simultaneous Localization and Mapping，同時定位與建圖）解決「沒有地圖，也不知道自己在哪」的問題：一邊用光達掃描建地圖，一邊用這張地圖修正自己的位置。

只靠里程計（odom）會累積誤差：輪子打滑、半徑誤差，開越久偏越多。SLAM 把每次的掃描和已經建好的地圖比對（scan matching），算出「我其實在這裡」，再發布一個修正量：TF `map → odom`。

```
map ──(slam_toolbox：修正量)──▶ amr1/odom ──(DiffDrive：輪子積分)──▶ amr1/base_footprint
```

- `odom → base_footprint`：連續、平滑，但會漂移（REP-105）
- `map → odom`：讓 `map → base_footprint` 不漂移，但修正時可能會跳一下

## 做了什麼

### 1. 參數檔（task 2.1）

以官方 `mapper_params_online_async.yaml` 為起點，只改和本車有關的：

| 參數 | 值 | 原因 |
|---|---|---|
| `map_frame` | `map` | 多車共用地圖，不加前綴 |
| `odom_frame`／`base_frame` | `$(var robot_id)/odom`、`…/base_footprint` | frame 帶前綴（筆記 15 的代換） |
| `scan_topic` | `/$(var robot_id)/scan` | |
| `map_name` | `/$(var robot_id)/map` | **預設是絕對名稱 `/map`，namespace 不會作用** |
| `min/max_laser_range` | 0.12／12.0 | 和光達規格一致（官方 0／20）；超過光達能力的距離不該拿來畫地圖 |
| `map_update_interval` | 2.0 | 官方 5 秒；倉庫小，2 秒更新讓 RViz 看得到地圖逐漸長出來 |
| `resolution` | 0.05 | 每格 5 cm |
| `enable_interactive_mode` | false | 不用 RViz 外掛手動拖位姿圖 |

其他維持官方值。其中幾個值得知道：
- `minimum_travel_distance: 0.5`、`minimum_travel_heading: 0.5`：車移動 0.5 m 或轉 0.5 rad 才加入一個新的「節點」（位姿 + 當時的掃描）到位姿圖；原地不動不會一直加。
- `do_loop_closing: true`：回到看過的地方時，掃描和舊節點比對成功就加一條「閉環」邊，用最佳化（Ceres solver）把整張圖的誤差攤平。

### 2. launch

```xml
<node pkg="slam_toolbox" exec="async_slam_toolbox_node" name="slam_toolbox" namespace="$(var robot_id)">
  <param from="$(find-pkg-share amr_navigation)/config/slam_toolbox.yaml" allow_substs="true"/>
  <param name="use_sim_time" value="$(var use_sim_time)"/>
</node>
```

- **async vs sync**：sync 每一筆 scan 都處理，跟不上就排隊、延遲越來越大；async 處理不完就跳過，永遠用最新的。線上建圖官方建議 async。
- slam_toolbox 2.6（Humble）是一般節點，不是 lifecycle node，啟動就開始運作。
- `use_sim_time` 只由 launch 設定，參數檔不寫（避免兩處不一致）；測試會檢查。

### 3. RViz 設定檔（task 2.2）

`config/navigate.rviz` 以 Nav2 官方設定為起點，所有 topic 改成 `/amr1/...`。重點：
- **Map 的 Durability = Transient Local**：地圖不是一直發，而是更新時才發；Transient Local 讓晚加入的訂閱者也拿得到最後一筆（類似 ROS 1 的 latched topic）。
- **2D Pose Estimate → `/amr1/initialpose`、2D Goal Pose → `/amr1/goal_pose`**：RViz 工具預設發到沒有 namespace 的 `/initialpose`、`/goal_pose`，namespace 下的 Nav2 收不到——點了沒反應是最常見的坑。
- **不用 Nav2 的 RViz 外掛**（Navigation 2 面板、Nav2 Goal 工具）：Humble 版直接呼叫 `/navigate_to_pose`，不支援 namespace。bt_navigator 本來就訂閱 `goal_pose`，用 RViz 內建的 2D Goal Pose 效果一樣。

### 4. 建圖冒煙測試（task 2.4）

world（headless）+ `robot.launch.xml hardware:=sim x:=1 y:=1` + 8 秒後 `mapping.launch.xml`：

| 測試 | 檢查 |
|---|---|
| 01 | 30 s 內收到含佔據格的 `/amr1/map`，解析度 0.05、frame `map` |
| 02 | 查得到 `map → amr1/base_footprint`，車還沒動所以在原點附近 |
| 03 | `/tf` 的發布者只有 base_bridge、robot_state_publisher、slam_toolbox |
| 04 | 行駛後已知格數至少變成 1.5 倍 |
| 05 | `map_saver_cli` 存出 `.pgm`（> 1 KB）與 `.yaml` |

訂閱地圖的 QoS 要用 Transient Local，和 RViz 同樣的道理。

## 怎麼驗證（2026-10-08 實測）

```bash
env -i PATH=/usr/bin:/bin python3 -m pytest -q test      # amr_navigation：16 passed
launch_test test/test_mapping_smoke.py                    # amr_hw_sim：Ran 5 tests ... OK
colcon test && colcon test-result --all                   # 134 tests, 0 failures
```

手動實測：已知格 1174 → 12202、地圖 257×248 → 296×254；`/tf` 發布者確認只有 slam_toolbox 加了 `map`。README 的存圖指令照抄執行一次，`data/maps/` 下產生的檔案擁有者是使用者。

**重要發現**：車在世界 (1, 1) 開始建圖，`map → amr1/base_footprint` 卻是 (0, 0)。**`map` 座標系的原點是開始建圖時車子的位置**，不是 Gazebo 世界原點。慣例：repo 內的地圖都從出生點 (1, 1, 0) 開始建，所以世界座標 = 地圖座標 + (1, 1)。

## 面試追問

**Q：SLAM 在解決什麼問題？為什麼不能只用里程計？**
A：同時建地圖和定位。里程計是積分，誤差會累積；SLAM 用感測器觀測和地圖比對來修正，並在回到舊地方時閉環，把累積誤差攤平。

**Q：slam_toolbox 的原理？**
A：graph-based SLAM。每移動一段距離就建一個節點（位姿 + 掃描），相鄰節點之間以 scan matching 算出相對位姿當作邊；偵測到閉環時加一條長邊，然後用非線性最佳化（Ceres）調整所有節點，使整體誤差最小。地圖是把所有節點的掃描依最佳化後的位姿畫成佔據格。

**Q：`map → odom` 為什麼不直接發 `map → base_link`？**
A：TF 是樹，每個 frame 只能有一個父節點。`odom → base_link` 已經由里程計發布了，SLAM 只能在上面接一段 `map → odom`，表示「里程計的原點在地圖上的哪裡」。這樣里程計維持連續（控制器用），地圖位置也正確（規劃用）。

**Q：Transient Local 是什麼？**
A：DDS 的 durability QoS。發布端保留最後幾筆，新的訂閱者連上來時會收到；相當於 ROS 1 的 latched topic。地圖、robot_description 這種「很少更新但隨時要拿得到」的資料都用它。發布端和訂閱端都要設定才有效。

**Q：建圖時怎麼開車比較好？**
A：慢、平順、避免原地快速旋轉（scan matching 跟不上）；沿牆走，掃描特徵多；最後回到起點觸發閉環。長走廊這種特徵少的地方容易失敗。

## 踩坑紀錄

- **`map_name` 預設是 `/map`**：slam_toolbox 的地圖 topic 名稱是參數，預設是絕對名稱，放在 namespace 裡也一樣會發到 `/map`。在參數檔明確指定 `/$(var robot_id)/map`。
- **tf2_monitor 看不出發布者**：它不吃模擬時間，延遲數字很誇張，broadcaster 也顯示 `no authority available`。改用 `ros2 topic info /tf -v` 看發布者節點。
- **RViz 沒辦法在背景測試**：`QT_QPA_PLATFORM=offscreen` 時 Ogre 建不出 OpenGL 視窗（`Invalid parentWindowHandle`）。設定檔改用靜態測試檢查，畫面由使用者確認。
- **README 原本的「地圖」章節是 Gazebo 場景**：和 SLAM 地圖容易混淆，改名為「場景（Gazebo world）」。
