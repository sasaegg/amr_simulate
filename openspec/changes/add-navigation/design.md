# Design

## Context

- 子專案 1 完成後的狀態見 `openspec/specs/`：sim 容器只跑世界與 `/clock`；robot 容器跑車子系統中控 `amr_bringup/robot.launch.xml`（`hardware:=sim|real` 必填，sim 時 include `amr_hw_sim` 的虛擬驅動）。車輛介面：`/amr1/{cmd_vel,scan,odom,imu,joint_states}`、TF `amr1/odom → amr1/base_footprint → …`，速度指令經 `cmd_vel_watchdog`（0.5 s 逾時）進 Gazebo。
- launch 一律用 XML（使用者熟悉 ROS 1、偏好可讀性；子專案 1 task 5.13）；XML 不能讀自訂 YAML，設定以 launch 參數傳入。
- 映像已安裝 slam_toolbox 2.6.10、Nav2 1.1.20（Humble），含 `nav2_dwb_controller`、`nav2_navfn_planner`、`nav2_velocity_smoother`、`nav2_map_server`、`nav2_amcl`，不需重建映像。
- 車體：車身 0.5 × 0.4 m、輪子在 y = ±0.22（寬 0.04，外緣 ±0.24）、`base_link` 中心即 `base_footprint` 的 xy；光達 0.12–12 m、360 點、10 Hz；硬體速度上限 1.0 m/s、1.5 rad/s。

## Goals / Non-Goals

**Goals:**
- 使用者在模擬中用 teleop 建圖、存圖，再以導航模式點目標讓車開過去；過程中每個節點、參數、remap 都看得到並能解釋。
- 建圖與導航只依賴車輛標準介面，真車上不需修改即可使用。

**Non-Goals:**
- 自動探索建圖（之後視需要另立子專案）。
- 多台車同時導航（架構預留 namespace 與共用 `map`，但只驗證一台）。
- 連續建圖並定位（lifelong mapping）、地圖合併、多樓層。
- collision_monitor、keepout／speed 區域等 Nav2 進階功能。
- 導航失敗後的任務層處理（子專案 4）。

## Decisions

### D1：新套件 `amr_navigation` 屬於車子系統

`ament_python`（與其他套件一致；之後若有小工具也可放 Python）。內容：`launch/mapping.launch.xml`、`launch/navigation.launch.xml`、`config/slam_toolbox.yaml`、`config/nav2.yaml`、`config/navigate.rviz`。package.xml 只列 `slam_toolbox`、`nav2_*`、`launch_xml` 等，**不列任何 `ros_gz*`／`amr_hw_sim`／`amr_worlds`**，以測試檢查（同 `amr_bringup`）。

替代：放進 `amr_bringup`——中控會變大，且 SLAM／Nav2 的參數與 launch 和「啟動驅動」是不同職責，分開較好維護與測試。

### D2：啟動方式——獨立 launch，中控以 `mode` include

- `mapping.launch.xml`、`navigation.launch.xml` 參數：`robot_id`（預設 `amr1`）、`use_sim_time`（預設 `false`）；導航另有 `map`（預設 `warehouse_small`）。
- `robot.launch.xml` 新增 `mode`（`none`／`mapping`／`navigation`，預設 `none`）與 `map`；在 `is_sim` group 內依 `mode` 以 `if="$(equals $(var mode) mapping)"` include 對應 launch，傳入 `robot_id`、`use_sim_time:=$(var is_sim)`、`map`。不合法的 `mode` 與 `hardware` 相同處理：`<log>` + `<shutdown>`，不啟動節點。
- 單獨啟動時使用者自己加 `use_sim_time:=true`（README 寫明）。
- 替代：只用 `mode`（切換要重啟驅動，模擬時車被移回出生點）；只用獨立 launch（正式使用要開多個終端機）。兩者都支援（使用者選定）。

### D3：參數檔以 `allow_substs` 帶入 robot_id

XML `<param from="$(find-pkg-share amr_navigation)/config/nav2.yaml" allow_substs="true"/>` 讓 YAML 內可寫 `$(var robot_id)`：
- 節點鍵用完整名稱：`/$(var robot_id)/controller_server:`、`/$(var robot_id)/global_costmap/global_costmap:`——costmap 是 planner／controller 程序內的子節點，參數檔以完整名稱比對才會套用到它們，也避免依賴 Nav2 官方 Python 的 `RewrittenYaml`。
- frame：`map`（不加前綴）、`$(var robot_id)/odom`、`$(var robot_id)/base_footprint`。
- `use_sim_time` 不寫在 YAML，由 launch 對每個節點以 `<param name="use_sim_time" value="$(var use_sim_time)"/>` 設定（避免兩處矛盾）。
- 替代：每台車一份參數檔（重複）；Python launch 用 `RewrittenYaml`（違反 XML 決定）。**先在 task 1 驗證**這個機制對 costmap 子節點有效；若無效，退回改用 `/**/global_costmap/global_costmap:` 萬用鍵加 launch 層級覆寫 frame。

### D4：建圖——slam_toolbox 非同步線上建圖

- `async_slam_toolbox_node`（`sync` 版本在跟不上時會累積延遲；官方建議線上建圖用 async）。namespace `<id>`；`scan_topic: /<id>/scan`、`map_frame: map`、`odom_frame: <id>/odom`、`base_frame: <id>/base_footprint`、`resolution: 0.05`、`max_laser_range: 12.0`（與 xacro 一致）、`mode: mapping`。
- 發布 `/<id>/map`（`map` topic 在 namespace 下為相對名稱）與 TF `map → <id>/odom`。
- 存圖：Nav2 的 `map_saver_cli`（不另寫程式），README 指令 `ros2 run nav2_map_server map_saver_cli -f /data/maps/<name> --ros-args -r map:=/<id>/map -p use_sim_time:=true`；輸出 `<name>.pgm` + `<name>.yaml`（trinary 模式、佔據門檻 0.65／空曠 0.25）。
- 替代：slam_toolbox 的 serialize（`.posegraph`／`.data`）——網頁讀不懂，且導航改用 AMCL，不需要。

### D5：導航——自己寫 XML 列出 Nav2 各節點

參考 `nav2_bringup` Humble 的 `localization_launch.py` 與 `navigation_launch.py`，以 XML 逐一列出：

| 群組 | 節點 | 重點 |
|---|---|---|
| 定位 | `map_server` | `yaml_filename: /data/maps/$(var map).yaml` |
| | `amcl` | 差速模型 `nav2_amcl::DifferentialMotionModel`；`global_frame_id: map`、`odom_frame_id`、`base_frame_id` 帶前綴；`scan_topic: /<id>/scan`；`set_initial_pose: false`（初始位姿由使用者給定） |
| | `lifecycle_manager_localization` | `node_names: [map_server, amcl]`、`autostart: true` |
| 導航 | `planner_server` | NavFn（`use_astar: false`，Dijkstra） |
| | `controller_server` | DWB（`FollowPath`），輸出 remap `cmd_vel → cmd_vel_nav` |
| | `smoother_server` | 預設 SimpleSmoother（bt 預設樹會呼叫） |
| | `behavior_server` | spin、backup、wait |
| | `bt_navigator` | Humble 預設 `navigate_to_pose_w_replanning_and_recovery.xml` |
| | `waypoint_follower` | 預設 bt 與 RViz Nav2 面板會用到 |
| | `velocity_smoother` | 訂 `cmd_vel_nav`、發 `cmd_vel`（namespace 下即 `/<id>/cmd_vel`）；上限與 DWB 一致 |
| | `lifecycle_manager_navigation` | 上述 7 個節點，`autostart: true` |

- 所有節點 namespace `<id>`；Nav2 內部以相對名稱溝通，namespace 自然隔離。
- TF：Nav2 訂 `/tf`、`/tf_static`（全域），不 remap。
- 替代：include 官方 `bringup_launch.py`（Python、黑箱）；混合（一半透明）。使用者選定自己寫。

### D6：costmap 與 DWB 參數

- 車體外形 `footprint: [[0.25, 0.24], [0.25, -0.24], [-0.25, -0.24], [-0.25, 0.24]]`（矩形，比 robot_radius 精確；窄通道才過得去）。
- 全域 costmap：`global_frame: map`、static + obstacle（`/<id>/scan`）+ inflation（`inflation_radius: 0.55`、`cost_scaling_factor: 3.0`）、`track_unknown_space: true`。
- 局部 costmap：`global_frame: <id>/odom`、`rolling_window: true` 3 × 3 m、obstacle + inflation。
- DWB：`max_vel_x: 0.5`、`max_vel_theta: 1.0`、`min_vel_x: 0.0`（不主動倒車；後退由 behavior 負責）、加速度上限 ≤ 硬體（2.5 m/s²、5.0 rad/s²）；critics 沿用官方預設組合（RotateToGoal、Oscillation、BaseObstacle、GoalAlign、PathAlign、PathDist、GoalDist）。
- 目標容差：`xy_goal_tolerance: 0.25`、`yaw_goal_tolerance: 0.25`（spec 要求 0.3 m 內）。
- 數值以官方 `nav2_params.yaml` 為起點，只改與本車相關者；調整過的參數在學習筆記說明原因。

### D7：RViz 設定檔

`config/navigate.rviz`：Fixed Frame `map`；Map（`/amr1/map`，Durability Transient Local）、LaserScan、TF、RobotModel（TF Prefix `amr1`）、全域／局部 costmap、全域路徑（`/amr1/plan`）；**2D Pose Estimate 工具 topic 設為 `/amr1/initialpose`、Nav2 Goal 設為 `/amr1/goal_pose`**——RViz 工具預設發到無 namespace 的 `/initialpose`、`/goal_pose`，Nav2 在 namespace 下收不到。設定檔寫死 `amr1`（RViz 設定檔不支援代換；多車時另存一份）。

### D8：執行資料目錄與地圖版控

- 主機 `data/` → robot 容器 `/data`（可寫，compose `../../data:/data`）；地圖在 `data/maps/`，納入 git（`.pgm` 已標 binary）。
- repo 內附 `warehouse_small` 地圖：由使用者在建圖步驟親手用 teleop 建出並 commit；導航冒煙測試使用它。
- sim 容器不掛 `/data`（世界不需要地圖）。

### D9：測試策略

- 純解析（無 ROS）：`amr_navigation` 的 package.xml 與 launch 不含模擬套件；參數檔所有 frame 為 `map` 或 `$(var robot_id)/…`；footprint、`max_laser_range`、速度／加速度上限與 xacro 的一致性（解析 xacro property，不需 xacro 執行檔）；RViz 設定檔工具 topic 帶 namespace。
- 實際執行 launch（需 ROS）：`mode:=foo` 顯示訊息且不啟動節點。
- 整合冒煙測試（launch_testing，放 `amr_hw_sim/test/`，因為需要世界）：
  - `test_mapping_smoke.py`：world headless + `robot.launch.xml hardware:=sim mode:=mapping x:=1 y:=1` → 30 s 內 `/amr1/map`、TF `map → amr1/base_footprint`、`map → amr1/odom` 單一發布者；送 cmd_vel 行駛後已知格數增加；以 `map_saver_cli` 存到暫存目錄，檔案存在。
  - `test_navigation_smoke.py`：`mode:=navigation map:=warehouse_small` → 發布 `/amr1/initialpose` (1, 1, 0) → 10 s 內 `map → amr1/base_footprint` 在 0.3 m 內 → `navigate_to_pose` action 送空曠處目標 → 90 s 內 SUCCEEDED，位置誤差 < 0.3 m；送牆內目標 → 回報失敗。
- 冒煙測試可用不同 `ROS_DOMAIN_ID`／`IGN_PARTITION` 執行，避免與使用者開著的模擬互相干擾（子專案 1 筆記 14）。
- 手動驗收（使用者）：teleop 建圖時 RViz 看地圖長出來、存圖並檢視 `.pgm`、導航點目標、途中放箱子避障、單獨切換建圖／導航時車留在原地。

### D10：學習筆記

每個實作步驟一篇，編號接續子專案 1（15 起），段落同前（為什麼／做了什麼／怎麼驗證／面試追問／踩坑紀錄）。預計：15 slam_toolbox 建圖、16 存圖與地圖格式、17 AMCL 定位、18 Nav2 架構與 lifecycle、19 costmap 與 DWB、20 導航冒煙測試、21 最終驗收。

## Risks / Trade-offs

- [`allow_substs` 對 costmap 子節點的參數鍵不生效] → task 1 先做最小驗證；退路見 D3。
- [RViz 工具 topic 未帶 namespace，點了沒反應] → 設定檔寫死 `/amr1/...`，README 說明；測試檢查設定檔。
- [模擬時間下 TF 時間戳與節點時鐘不一致（`use_sim_time` 漏設），出現 extrapolation 錯誤] → 每個節點由 launch 設定 `use_sim_time`；測試檢查導航節點的 `use_sim_time`。
- [DWB 參數不適合本車，原地打轉或貼牆停住] → 以官方參數為起點，只改車體相關值；冒煙測試的目標選在開闊處；調整紀錄寫入筆記。
- [teleop 與導航同時發 `/amr1/cmd_vel` 互搶] → 已知行為，README 註明導航時不要用 teleop（之後可加 twist_mux）。
- [map_saver 直接覆蓋同名檔] → README 提醒換名字；版控可復原。
- [冒煙測試耗時、偶發逾時] → 用條件輪詢而非固定 sleep，逾時留餘裕（建圖 30 s、導航 90 s）。
- [使用者建的地圖品質不佳（漏掃、扭曲），導航測試不穩] → 建圖步驟提供開法建議（慢速、沿牆繞一圈、回到起點閉環）；必要時重建。

## Migration Plan

- 新增套件與 `data/`；`robot.launch.xml` 新參數有預設值（`mode:=none`），既有啟動指令行為不變。
- compose 新增 robot 的 `/data` 掛載：需 `up_gpu.sh` 重建容器。
- 回滾：刪除 `amr_navigation` 與 `data/`、還原 `robot.launch.xml` 與 compose。
