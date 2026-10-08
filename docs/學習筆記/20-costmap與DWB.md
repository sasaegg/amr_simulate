# 20 costmap、DWB 與導航冒煙測試

檔案：[`nav2.yaml`](../../ros_ws/src/amr_navigation/config/nav2.yaml)（costmap、controller_server 段落）、[`test_navigation_config.py`](../../ros_ws/src/amr_navigation/test/test_navigation_config.py)、[`test_navigation_smoke.py`](../../ros_ws/src/amr_hw_sim/test/test_navigation_smoke.py)

子專案 2 task 4.2–4.4。

## 為什麼要做

Nav2 的「怎麼開」由兩件事決定：
- **costmap**：把地圖和光達看到的東西變成「每一格有多危險」的代價地圖，規劃和控制都在上面算。
- **局部控制器 DWB**：在局部 costmap 上，每 50 ms 選一組速度。

這些參數必須和**這台車**一致（外形、速度、加速度、光達），不然會撞牆、或太保守卡在窄道。

## 做了什麼

### costmap 的三層

| 層 | 內容 |
|---|---|
| static layer | 載入的地圖：牆、貨架（只有全域 costmap 有） |
| obstacle layer | 光達即時看到的障礙物，地圖上沒有的也算；光束穿過的格子會清掉（raytrace），障礙物移走後會消失 |
| inflation layer | 從障礙物往外擴散代價：車體內切圓半徑內是「一定撞」，再往外到 0.55 m 代價遞減（`cost_scaling_factor` 越大衰減越快），讓路徑自然離牆遠一點 |

- **全域 costmap**：`global_frame: map`，整張地圖，1 Hz 更新，給 planner。
- **局部 costmap**：`global_frame: amr1/odom`、`rolling_window: true`、3 × 3 m 跟著車移動，5 Hz 更新，給 controller。用 odom 座標系是因為它連續不會跳（AMCL 修正時 map 座標系會跳）。
- 官方局部 costmap 用 voxel layer（3D），我們只有 2D 光達，改用 obstacle layer。
- **車體外形**：官方用 `robot_radius: 0.22` 的圓；本車改用矩形 footprint `[[0.25, 0.24], [0.25, -0.24], [-0.25, -0.24], [-0.25, 0.24]]`——前後到車身、左右到輪子外緣。圓形要用外接圓（半徑 0.35）才安全，會讓窄道過不去。
- topic 一律絕對名稱（`/amr1/scan`、`/amr1/map`）：costmap 是程序內的子節點，相對名稱會解析到它自己的 namespace 底下。

### DWB（Dynamic Window approach）

每個控制週期（20 Hz）：
1. **取樣**：在目前速度附近、加速度做得到的範圍（dynamic window）內，取 20 × 20 組 (vx, ω)。
2. **模擬**：每組速度往前模擬 1.7 秒，得到一條軌跡。
3. **評分**：每條軌跡由多個 critic 打分數加總——
   - BaseObstacle：軌跡經過的 costmap 代價（撞到直接淘汰）
   - PathAlign／PathDist：貼近全域路徑
   - GoalAlign／GoalDist：朝向目標
   - RotateToGoal：快到目標時原地轉到目標朝向
   - Oscillation：避免來回抖動
4. 選分數最好的那組送出。

本車的值：`max_vel_x: 0.5`（官方 0.26 是 TurtleBot3）、`max_vel_theta: 1.0`、`min_vel_x: 0`（不主動倒車，後退交給 behavior 的 backup）、`max_vel_y: 0`（差速車不能橫移）、加速度 ≤ 硬體上限。velocity_smoother 的上限和 DWB 一致。

### planner 的 tolerance 改成 0

官方 `GridBased.tolerance: 0.5`：目標在障礙物裡時，planner 會在 0.5 m 內找一個可行的點規劃過去。實測把目標放在隔間牆裡——車停在離目標 0.59 m 的地方，**回報 SUCCEEDED**，因為 controller 只檢查有沒有到「路徑終點」（替代點）。

這比失敗更糟：之後派車系統會以為車到了指定儲位。改成 `tolerance: 0.0`：目標不可行就規劃失敗，行為樹脫困幾次後回報 ABORTED。代價是使用者點得太貼牆時會失敗（點遠一點就好），README 疑難排解有寫。

### 靜態測試（task 4.2 新增 10 項，共 35 項）

和 xacro 比對，車輛模型改了參數就會提醒：footprint 的前後左右邊界、速度與加速度不超過硬體、光達觀測距離 ≤ 光達最大距離、goal tolerance < spec 的 0.3 m、planner tolerance 為 0。

### 導航冒煙測試（task 4.3）

world + `robot.launch.xml hardware:=sim x:=1 y:=1` + `navigation.launch.xml map:=warehouse_small`：

| 測試 | 檢查 |
|---|---|
| 01 | `/amr1/map` 有資料，frame `map` |
| 02 | 給初始位姿前**沒有** `map → base_footprint` |
| 03 | 發 initialpose (0, 0, 0) 後 10 s 內定位，和 Gazebo 真實位置差 < 0.3 m |
| 04 | `navigate_to_pose` 到地圖 (9, 0) 成功，誤差 < 0.3 m，最高速度 ≤ 0.55 m/s |
| 05 | 行駛後定位仍 < 0.3 m |
| 06 | 目標在場景箱子中心 → ABORTED，車停下 |
| 07 | 9 個導航節點都在 `/amr1` 下 |

幾個寫測試時遇到的重點：
- **要等導航節點 active 才送目標**：bt_navigator 的 action server 在節點 active 前就存在，但會拒絕目標。呼叫 `/amr1/lifecycle_manager_navigation/is_active`（std_srvs/Trigger）等到 true。
- **「真實位置」從 Gazebo 拿**（`ign model -m amr1 -p`），換算成地圖座標（減出生點 (1, 1)）。用 odom 或 AMCL 自己的估計來驗證定位，等於自己驗證自己。
- **整合測試要在 robot 容器跑**：sim 容器沒有 `/data`，map_server 找不到地圖，後面全部連鎖失敗。
- **地圖可以換**：環境變數 `NAV_SMOKE_MAP`。正式地圖由使用者建（task 2.3），開發時先用腳本建的 `dev_tmp` 跑通。

## 怎麼驗證（2026-10-08 實測，暫時地圖 `dev_tmp`）

| 項目 | 結果 |
|---|---|
| costmap | 全域 403 × 304（＝地圖），局部 60 × 60（3 m ÷ 0.05） |
| 途中在路徑上生成 0.6 m 箱子（世界 (5.5, 1)） | 27 s 抵達、誤差 0.10 m；車中心離箱子中心最近 0.84 m（碰撞距離約 0.54 m） |
| 目標在箱子中心 | ABORTED（`failed to create plan with tolerance 0.50`，21.5 s 脫困後放棄） |
| 目標在隔間牆內，tolerance 0.5 | **SUCCEEDED 但停在 0.59 m 外** → 改 0 |
| 目標在隔間牆內，tolerance 0 | ABORTED |
| 一般目標（含轉 180°） | 19.7 s、誤差 0.07 m |
| 冒煙測試 | 7 項通過（約 54 s）；`colcon test` 155 tests 全部通過 |

## 面試追問

**Q：costmap 有哪些層？為什麼要膨脹層？**
A：static（地圖）、obstacle（感測器即時障礙物）、inflation（往外擴散代價）。規劃時把車當成一個點，膨脹層讓「點」離障礙物至少有車體半徑的距離，並偏好離牆遠一點的路徑。

**Q：全域 costmap 和局部 costmap 差在哪？**
A：全域在 map 座標系、整張地圖、低頻，給 planner；局部在 odom 座標系、車周圍小範圍滾動視窗、高頻，給 controller。局部用 odom 是因為它連續，AMCL 修正 map 時不會讓局部控制跳動。

**Q：DWA／DWB 的原理？和 Pure Pursuit 比？**
A：在可達的速度空間取樣、模擬軌跡、用代價函式評分、選最好的。能在局部繞開障礙物，但參數多、要調 critic 權重。Pure Pursuit 只追路徑上前方一點，平順好調，但遇到障礙物只會停，要靠全域重新規劃。

**Q：怎麼確定導航參數和車子一致？**
A：footprint、速度、加速度、感測器範圍都從車輛模型來；我們用測試直接解析 xacro 和參數檔比對，車輛規格改了測試會失敗提醒。

**Q：導航目標到不了時，系統應該怎麼回報？**
A：明確回報失敗，不能「接近就算成功」。上層（派車、任務佇列）才能決定重試、換目標或通知人。所以 planner 不替換不可行的目標。

## 踩坑紀錄

- **planner tolerance 讓「到不了」變成「成功」**：見上面。
- **目標被拒絕**：導航節點還沒 active；測試等 `is_active`。
- **sim 容器沒有 `/data`**：整合測試改在 robot 容器跑，README 更新。
- **Gazebo 關閉偶爾超過 5 秒被 SIGKILL**：測試結束時所有程序同時收到 SIGINT，3 次有 2 次 Gazebo 沒在 5 秒內結束；單獨關閉 Gazebo 時 0.2 秒。三個冒煙測試以 `SetLaunchConfiguration('sigterm_timeout', '20')` 放寬，連跑 3 次都正常結束。使用者 Ctrl+C 世界時只有 Gazebo 那組程序在關閉，不受影響。
- **初始位姿給錯，導航一直卡住**：手算座標時多減了一次出生點。開發腳本改成直接讀 Gazebo 真實位姿來發 initialpose。
