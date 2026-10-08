# Tasks

每個 task 的節奏：說明原因 → 執行（`sudo` 指令由使用者親手執行；檔案由 Claude 撰寫並逐段解釋）→ 驗證 → 寫學習筆記 → commit → 使用者確認後才進下一個。筆記格式與編號見 design.md D10。

整合驗證時若使用者的模擬還開著，以不同 `ROS_DOMAIN_ID`／`IGN_PARTITION` 執行，不關閉使用者的程序。

## 1. 套件骨架與執行資料目錄

- [x] 1.1 （筆記 15）建立 `ros_ws/src/amr_navigation`（ament_python）：package.xml 列 `slam_toolbox`、`nav2_map_server`、`nav2_amcl`、`nav2_lifecycle_manager`、`nav2_planner`、`nav2_navfn_planner`、`nav2_controller`、`nav2_dwb_controller`、`nav2_smoother`、`nav2_behaviors`、`nav2_bt_navigator`、`nav2_waypoint_follower`、`nav2_velocity_smoother`、`launch`、`launch_ros`、`launch_xml`；setup.py 安裝 `launch/*.launch.xml` 與 `config/*`；`test/test_package_boundary.py`（package.xml 與 launch 不含 `ros_gz*`、`amr_hw_sim`、`amr_worlds`）。驗證：`colcon build` 成功、`ros2 pkg prefix amr_navigation` 找得到、`env -i` 下 pytest 通過
- [x] 1.2 （筆記 15）驗證 design D3 的參數代換：以最小的 launch 啟動 `planner_server`（namespace `amr1`）並以 `<param from=... allow_substs="true"/>` 載入鍵為 `/$(var robot_id)/planner_server:`、`/$(var robot_id)/global_costmap/global_costmap:` 的參數檔。驗證：`ros2 param get /amr1/global_costmap/global_costmap robot_base_frame` 為 `amr1/base_footprint`；結果寫入筆記；若無效改用 D3 退路並更新 design.md
- [x] 1.3 （筆記 15）建立 `data/maps/.gitkeep`；compose 的 robot service 加 `../../data:/data`；`up_gpu.sh` 重建容器。驗證：robot 容器 `touch /data/maps/test` 後主機 `data/maps/test` 擁有者為使用者（驗證後刪除）；sim 容器沒有 `/data`；`docker compose config -q` 通過

## 2. 建圖（mapping）

- [x] 2.1 （筆記 16）撰寫 `config/slam_toolbox.yaml`（D4：async、frame 帶 `$(var robot_id)`、`scan_topic`、`resolution: 0.05`、`max_laser_range: 12.0`）與 `launch/mapping.launch.xml`（參數 `robot_id`、`use_sim_time`；namespace `<id>`）；pytest：frame 只有 `map` 或 `$(var robot_id)/…`、`max_laser_range` 與 xacro 光達最大距離一致、scan topic 帶 namespace。驗證：pytest 通過；世界與 `robot.launch.xml hardware:=sim x:=1 y:=1` 執行中，另外啟動 `mapping.launch.xml use_sim_time:=true` → 30 s 內 `/amr1/map` 有資料、`tf2_echo map amr1/base_footprint` 有輸出、`map → amr1/odom` 只有一個發布者
- [x] 2.2 （筆記 16）撰寫 `config/navigate.rviz`（D7：Fixed Frame `map`；Map、LaserScan、TF、RobotModel（TF Prefix `amr1`）、全域／局部 costmap、`/amr1/plan`；2D Pose Estimate → `/amr1/initialpose`、2D Goal Pose → `/amr1/goal_pose`）；pytest 解析設定檔檢查工具 topic 帶 namespace、Map 的 Durability 為 Transient Local。驗證：pytest 通過；`rviz2 -d $(ros2 pkg prefix amr_navigation)/share/amr_navigation/config/navigate.rviz` 建圖中看得到地圖長出來（RViz 需要螢幕，畫面確認併入 2.3 由使用者操作）
- [ ] 2.3 （筆記 17）使用者以 teleop 沿倉庫繞一圈並回到起點建圖，以 `map_saver_cli` 存成 `data/maps/warehouse_small.{pgm,yaml}` 並 commit；筆記說明 `.pgm`／`.yaml` 每個欄位（resolution、origin、negate、occupied_thresh、free_thresh、mode）、佔據格的三種值、閉環。驗證：兩個檔案存在且擁有者為使用者；圖片檢視器打開 `.pgm` 看得到牆與貨架輪廓；`.yaml` 的 resolution 為 0.05
- [ ] 2.4 （筆記 16）撰寫 `amr_hw_sim/test/test_mapping_smoke.py`（launch_testing：world headless + `robot.launch.xml hardware:=sim x:=1 y:=1` + `mapping.launch.xml use_sim_time:=true`）：30 s 內收到 `/amr1/map` 且車周圍有佔據格、TF `map → amr1/base_footprint` 可查且 `map → amr1/odom` 單一發布者、送 cmd_vel 行駛後已知格數增加、`map_saver_cli` 存到暫存目錄產生 `.pgm` 與 `.yaml`；amr_hw_sim 的 package.xml 加對應 test_depend。驗證：`launch_test test/test_mapping_smoke.py` 全部通過、`colcon test` 全部通過
- [ ] 2.5 （筆記 16）README 新增「建圖與存圖」：啟動、teleop 開法建議（慢速、沿牆、回起點）、RViz 設定檔、存圖指令（含 `-r map:=/amr1/map`、`use_sim_time`）、同名覆蓋提醒。驗證：照 README 指令從頭做一次可建圖並存圖

## 3. 定位（navigation：載入地圖與 AMCL）

- [ ] 3.1 （筆記 18）`config/nav2.yaml` 的 map_server、amcl 段落（D5：差速模型、frame 帶前綴、`scan_topic`、`set_initial_pose: false`）與 `launch/navigation.launch.xml` 的定位部分（參數 `robot_id`、`use_sim_time`、`map`；map_server、amcl、`lifecycle_manager_localization`；每個節點設 `use_sim_time`）；pytest：frame、地圖路徑為 `/data/maps/$(var map).yaml`、每個節點都有 `use_sim_time`。驗證：pytest 通過；以 `map:=warehouse_small` 啟動後 `/amr1/map` 有資料；RViz 以 2D Pose Estimate 點在車輛位置後 10 s 內 `map → amr1/base_footprint` 可查且與 Gazebo 中車輛位置差 < 0.3 m；teleop 行駛 5 m 後仍 < 0.3 m；`map:=nope` 時訊息顯示 `/data/maps/nope.yaml`

## 4. 導航（navigation：Nav2）

- [ ] 4.1 （筆記 19）`navigation.launch.xml` 加入 Nav2 的 7 個節點與 `lifecycle_manager_navigation`（D5：controller 輸出 remap 為 `cmd_vel_nav`、velocity_smoother 輸出 `cmd_vel`），`nav2.yaml` 加入 planner（NavFn）、smoother、behavior、bt_navigator、waypoint_follower 段落；pytest：lifecycle_manager 的 `node_names` 與 launch 中的節點一致、`cmd_vel` 路徑為 `cmd_vel_nav → velocity_smoother → cmd_vel`。驗證：pytest 通過；啟動後 `ros2 lifecycle get` 每個節點皆為 `active`；RViz 2D Goal Pose 點空曠處，車輛開到並停下；導航中按 Ctrl+C 停止導航，車輛 1 秒內停下
- [ ] 4.2 （筆記 20）`nav2.yaml` 的全域／局部 costmap 與 DWB 段落（D6：矩形 footprint、static/obstacle/inflation、局部 3×3 m 滾動視窗、速度與加速度上限、目標容差）；pytest：footprint 與 xacro 車身／輪子外緣一致、速度與加速度上限不超過 xacro 硬體上限、obstacle 層觀測來源為 `/amr1/scan`。驗證：pytest 通過；RViz 看得到膨脹層；直線導航時 `/amr1/odom` 線速度 ≤ 0.5 m/s；導航途中在 Gazebo 放一個箱子擋路，車輛不撞到並抵達（記錄於筆記）；目標點在牆內時 RViz 顯示失敗且車停下
- [ ] 4.3 （筆記 20）撰寫 `amr_hw_sim/test/test_navigation_smoke.py`（launch_testing：world headless + `robot.launch.xml hardware:=sim x:=1 y:=1` + `navigation.launch.xml use_sim_time:=true map:=warehouse_small`）：發布 `/amr1/initialpose` 為地圖座標 (0, 0, 0)（地圖從出生點 (1, 1) 開始建，design D4）後 10 s 內 `map → amr1/base_footprint` 誤差 < 0.3 m、`navigate_to_pose` 送空曠處目標 90 s 內 SUCCEEDED 且誤差 < 0.3 m、送牆內目標回報失敗、導航中 odom 線速度 ≤ 0.5 + 0.05 m/s、定位與導航節點皆在 namespace `amr1`。驗證：`launch_test test/test_navigation_smoke.py` 全部通過、`colcon test` 全部通過
- [ ] 4.4 （筆記 20）README 新增「定位與導航」：啟動、先 2D Pose Estimate 再 Nav2 Goal、導航時不要用 teleop、疑難排解（地圖找不到、RViz 點了沒反應＝工具 topic 沒帶 namespace、TF extrapolation＝`use_sim_time`、lifecycle 卡住）。驗證：照 README 從啟動到抵達目標做一次

## 5. 中控整合（sim-runtime）

- [ ] 5.1 （筆記 21）`robot.launch.xml` 新增 `mode`（`none`／`mapping`／`navigation`，預設 `none`）與 `map`，在 `is_sim` group 內依 mode include 對應 launch（傳 `robot_id`、`use_sim_time:=$(var is_sim)`、`map`）；`mode` 不合法時 `<log>` + `<shutdown>`；更新 `test_robot_launch.py`（`mode:=foo` 顯示訊息且不啟動節點）與 `test_package_boundary.py`（`amr_navigation` 不在 sim 判斷之外被視為模擬套件）。驗證：pytest 通過；`mode:=mapping`、`mode:=navigation` 一行啟動可建圖／導航；未指定 mode 時沒有 `map` 座標系；`mode:=none` 執行中另外啟動建圖、停止後再啟動導航，車輛留在原地未被移回出生點
- [ ] 5.2 （筆記 21）README 啟動流程與參數表加入 `mode`、`map`、`/data`；`docs/開發摘要.md` 更新子專案 2 狀態與套件配置。驗證：README 的指令都實際執行過；`colcon test` 全部通過

## 6. 整體驗收

- [ ] 6.1 （筆記 22）使用者依手動驗收清單逐項確認：teleop 建圖時 RViz 看到地圖長出來、存圖並檢視 `.pgm`、`mode:=navigation` 載入地圖、2D Pose Estimate 後車輛位置正確、2D Goal Pose 開到目標、途中放箱子避障、牆內目標回報失敗、單獨切換建圖／導航時車輛留在原地；結果記錄於筆記 22，更新 `docs/開發摘要.md` 子專案 2 狀態

## Workflow follow-up

- 全部完成後執行 `openspec archive add-navigation`，把 specs 併入 `openspec/specs/`
- 子專案 3（後端 + 前端基礎）另開 brainstorming 與新 change
