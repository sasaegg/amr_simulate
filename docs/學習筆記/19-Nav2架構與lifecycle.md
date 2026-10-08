# 19 Nav2 架構與 lifecycle

檔案：[`navigation.launch.xml`](../../ros_ws/src/amr_navigation/launch/navigation.launch.xml)、[`nav2.yaml`](../../ros_ws/src/amr_navigation/config/nav2.yaml)（導航段落）

子專案 2 task 4.1。

## 為什麼要做

定位（筆記 18）回答「我在哪」；導航要回答「怎麼去那裡」：規劃一條避開障礙物的路徑，再產生速度指令沿著它走，遇到狀況（卡住、路被擋）要能脫困或回報失敗。Nav2 把這些拆成幾個獨立的 server，用行為樹（behavior tree）串起來。

## 做了什麼

### Nav2 的節點

```
                    goal_pose / navigate_to_pose action
                                  │
                           ┌──────▼──────┐
                           │ bt_navigator │  行為樹：規劃 → 跟隨 → 失敗時脫困
                           └──┬───┬───┬──┘
          ComputePathToPose   │   │   │  Spin / BackUp / Wait
                 ┌────────────┘   │   └──────────────┐
          ┌──────▼───────┐ ┌──────▼────────┐ ┌───────▼────────┐
          │planner_server│ │controller_srv │ │behavior_server │
          │ NavFn        │ │ DWB           │ │ 脫困動作        │
          │ 全域 costmap │ │ 局部 costmap  │ └────────────────┘
          └──────────────┘ └──────┬────────┘
                                  │ cmd_vel_nav
                         ┌────────▼─────────┐
                         │velocity_smoother │ 限速、限加速度
                         └────────┬─────────┘
                                  │ cmd_vel  ＝ /amr1/cmd_vel（和 teleop 同一個入口）
                                  ▼
                          虛擬驅動（watchdog → Gazebo）／真車驅動
```

| 節點 | 職責 |
|---|---|
| `planner_server` | 在全域 costmap（整張地圖）上規劃路徑，NavFn（Dijkstra） |
| `controller_server` | 在局部 costmap（車周圍 3×3 m）上沿路徑產生速度，DWB（筆記 20） |
| `smoother_server` | 把規劃出來的折線路徑修平順 |
| `behavior_server` | 脫困動作：原地旋轉、後退、等待 |
| `bt_navigator` | 執行行為樹，協調上面各 server；接收 `goal_pose` topic 或 `navigate_to_pose` action |
| `waypoint_follower` | 依序走多個點 |
| `velocity_smoother` | controller 輸出的速度再限速、限加速度，讓馬達指令平順 |
| `lifecycle_manager_navigation` | 依序帶起上面 7 個節點 |

**預設行為樹**（`navigate_to_pose_w_replanning_and_recovery.xml`）：每秒重新規劃一次（環境變了路徑跟著變）→ controller 跟隨 → 失敗時依序清 costmap、原地旋轉、等待、後退，重試幾次仍失敗就放棄回報 aborted。

### 速度指令的路徑

```xml
<node pkg="nav2_controller" exec="controller_server" ...>
  <remap from="cmd_vel" to="cmd_vel_nav"/>
</node>
<node pkg="nav2_velocity_smoother" exec="velocity_smoother" ...>
  <remap from="cmd_vel" to="cmd_vel_nav"/>          <!-- 輸入 -->
  <remap from="cmd_vel_smoothed" to="cmd_vel"/>     <!-- 輸出 -->
</node>
```

都在 namespace `amr1` 下，所以最後是 `/amr1/cmd_vel`——和 teleop 同一個入口，經過子專案 1 的 watchdog。導航程序結束後沒人發指令，watchdog 0.5 s 逾時停車。

### use_sim_time 要用 `ros_args`

一開始照 2.1 的寫法用 `<param name="use_sim_time">`，結果查到：

```
/amr1/planner_server: True
/amr1/global_costmap/global_costmap: False   ← !
/amr1/local_costmap/local_costmap: False     ← !
```

launch 的 `<param>` 會寫成以「主節點完整名稱」為鍵的參數檔，只套用到 planner_server 本身；程序內再建立的 costmap 子節點拿不到，變成用牆上時鐘，和模擬時間的 TF 時間戳對不上。改成：

```xml
<node ... ros_args="-p use_sim_time:=$(var use_sim_time)">
```

`--ros-args -p` 是**程序層級**的參數，套用到程序內所有節點。改完 costmap 都是 True。建圖 launch 也統一改成這個寫法，測試檢查每個節點都這樣設。

### lifecycle 與啟動順序

lifecycle_manager 依 `node_names` 順序 configure → activate。**planner_server 在啟動時會等 `map → amr1/base_footprint` 的 TF**——這要使用者給了初始位姿、AMCL 開始發布 `map → odom` 才有。所以完整流程是：

1. 啟動導航 → 定位的兩個節點 active；導航節點停在等 TF
2. RViz 2D Pose Estimate → AMCL 發布 TF → 導航節點陸續 active（log：`Managed nodes are active`）
3. RViz 2D Goal Pose → 開始導航

等待期間 planner_server 卡在 activate，`ros2 lifecycle get /amr1/planner_server` 會沒有回應——這是正常的。

## 怎麼驗證（2026-10-08 實測，暫時地圖 `dev_tmp`）

```bash
ros2 launch amr_navigation navigation.launch.xml use_sim_time:=true map:=dev_tmp
# 發 initialpose (0, 0, 0) 後
ros2 lifecycle get /amr1/<節點>      # 9 個節點皆 active
```

| 項目 | 結果 |
|---|---|
| `/amr1/goal_pose` 給地圖座標 (9, 1.5)（世界 (10, 2.5)） | 24 s 抵達，距目標 0.24 m（容差 0.25）；log `Reached the goal!`、`Goal succeeded` |
| 最高速度 | 線速度 0.500 m/s（上限 0.5）、角速度 0.47 rad/s |
| 導航中對導航 launch 送 SIGINT（= Ctrl+C） | 從 0.50 m/s 在 0.76 s 內停下，沒有殘留程序 |
| 靜態測試 | 25 passed：每個 lifecycle node 恰被一個 manager 管理、`ros_args` 設 use_sim_time、frame 前綴 |

## 面試追問

**Q：Nav2 由哪些部分組成？一個目標進來後發生什麼事？**
A：bt_navigator 收到目標，執行行為樹：叫 planner_server 在全域 costmap 上規劃路徑，叫 controller_server 在局部 costmap 上沿路徑產生速度（再經 velocity_smoother 送到 cmd_vel），每秒重新規劃；controller 回報卡住或失敗時，行為樹依序做清 costmap、旋轉、等待、後退等脫困動作，仍失敗就回報 aborted。

**Q：為什麼用行為樹而不是狀態機？**
A：行為樹可組合、可重用（每個節點是獨立的 action／condition），用 XML 描述，不改程式就能調整流程（例如換成不重新規劃、加入充電判斷）。狀態機在狀態多時轉移關係會爆炸。

**Q：全域規劃和局部控制為什麼要分開？**
A：全域規劃看整張地圖、算得慢（1 Hz），負責「大方向」；局部控制看車周圍、算得快（20 Hz），負責「怎麼開」與閃避地圖上沒有的障礙物，並考慮車的動力學限制（速度、加速度）。

**Q：`use_sim_time` 為什麼要每個節點都設？設錯會怎樣？**
A：模擬時 TF 和感測器的時間戳是模擬時間；節點用牆上時鐘查 TF 會出現 extrapolation／timeout 錯誤，或用到過期資料。一個程序裡有多個節點（composition、costmap 子節點）時，要用 `--ros-args -p` 這種程序層級的參數才會全部套到。

**Q：teleop 和導航同時發 cmd_vel 會怎樣？實務上怎麼處理？**
A：兩邊互搶，車會抖。實務上用 twist_mux 依優先順序選一個來源（例如緊急停止 > 手動 > 導航）。

## 踩坑紀錄

- **costmap 子節點沒吃到 use_sim_time**：見上面，改用 `ros_args`。
- **`ros2 lifecycle get` 卡住**：planner_server 在 activate 中等 `map` 的 TF；給初始位姿就會繼續。
- **用 `timeout` 結束 `ros2 launch` 留下孤兒**：SIGTERM 結束了 launch，但 lifecycle_manager 沒跟著結束，下一次啟動時出現兩個同名節點（`ros2 node list` 警告 share an exact name）。測試一律對整個 process group 送 SIGINT（等同 Ctrl+C）。
