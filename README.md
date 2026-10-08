# AMR SLAM 模擬

ROS 2 Humble + Gazebo Fortress 的倉庫 AMR 模擬環境：可編輯的倉庫場景、一台帶 2D 光達與 IMU 的差速車，世界與車子系統分開執行——車子系統以「硬體模式」切換虛擬（Gazebo）或真實驅動，建圖、導航、之後的派車都建立在同一套車子系統上。

- 子專案 1：模擬環境（完成）。設計與任務紀錄見 [`openspec/changes/archive/2026-10-08-add-sim-environment/`](openspec/changes/archive/2026-10-08-add-sim-environment/)。
- 子專案 2：建圖、定位、導航（完成）。設計與任務紀錄見 [`openspec/changes/archive/2026-10-08-add-navigation/`](openspec/changes/archive/2026-10-08-add-navigation/)。

規格見 [`openspec/specs/`](openspec/specs/)，逐步學習筆記見 [`docs/學習筆記/`](docs/學習筆記/README.md)。

## 架構

```
┌──────────────── robot 容器：車子系統（之後部署到真車）────────────────┐   ┌──── sim 容器 ────┐
│ robot.launch.xml（中控）  hardware:=sim | real                         │   │ world.launch.xml │
│  ├ robot_state_publisher（車身 TF，來自 amr_description 的 URDF）      │   │  ├ Gazebo 世界   │
│  ├ mode:=navigation → 定位與導航（map_server + AMCL + Nav2）           │   │                  │
│  └ hardware: sim → 虛擬驅動（amr_hw_sim）                               │◀─▶│  └ /clock        │
│       ├ 虛擬底盤：把車放進世界、cmd_vel 逾時停車、odom／TF／joint_states │   │                  │
│       ├ 虛擬光達：/amr1/scan（Gazebo 依車輛實際位置計算）                │   │  真車上不存在     │
│       └ 虛擬 IMU：/amr1/imu                                             │   └──────────────────┘
│    hardware: real → 真車驅動（尚未提供）                                │
│ 建圖：mapping_ui.launch.xml（slam_toolbox + RViz 建圖面板），另外啟動    │
└────────────────────────────────────────────────────────────────────────┘
```

| 套件 | 內容 | 真車需要 |
|---|---|---|
| `amr_worlds` | 場景產生器、world、`world.launch.xml` | ❌ |
| `amr_description` | 車輛模型（xacro → URDF） | ✅ |
| `amr_bringup` | 車子系統中控 `robot.launch.xml` | ✅ |
| `amr_hw_sim` | 虛擬驅動 `sim_hardware.launch.xml`、冒煙測試 | ❌ |
| `amr_navigation` | 建圖 `mapping.launch.xml`（含存圖服務）、導航 `navigation.launch.xml`、參數、導航用 RViz 設定 | ✅ |
| `amr_rviz_plugins` | RViz「AMR 建圖」面板（按鈕存圖）、建圖用 RViz 設定、`mapping_ui.launch.xml` | 操作員電腦 |

車輛對外介面：`/amr1/cmd_vel`（輸入）、`/amr1/scan`、`/amr1/odom`、`/amr1/imu`、`/amr1/joint_states`、`/tf`（`amr1/odom → amr1/base_footprint`）、`/tf_static`；模擬時另有 `/clock`。所有 frame 帶 `amr1/` 前綴。

## 準備

### 主機

Ubuntu 22.04，依學習筆記操作（需要 sudo 的步驟由你自己執行）：

1. [docker 群組](docs/學習筆記/01-docker群組.md)：`sudo usermod -aG docker $USER` 後重新登入
2. [NVIDIA 驅動](docs/學習筆記/02-NVIDIA驅動.md)：`nvidia-smi` 看得到 GPU
3. [NVIDIA Container Toolkit](docs/學習筆記/03-NVIDIA-Container-Toolkit.md)：`docker run --rm --gpus all ubuntu nvidia-smi` 成功

沒有 NVIDIA GPU 時可以跳過 2、3，改用 `cpu` 模式（軟體渲染）。

### 建置映像、啟動容器

```bash
docker/amr_sim/build.sh          # 建置映像（自動帶入你的 UID/GID）
docker/amr_sim/up.sh gpu all     # 背景啟動 sim、robot 兩個長駐容器（不會開任何視窗）
```

- `up.sh <gpu|cpu> <sim|robot|all> [compose 參數]`：兩個參數都必填；`cpu` 用軟體渲染；`sim`／`robot` 只啟動或重建那一個容器。修改 Dockerfile 後加 `--build`。
- 進入容器：`docker/amr_sim/exec.sh sim`（世界）或 `docker/amr_sim/exec.sh robot`（車子系統），必須指定。以下每一步都註明在哪個容器執行；需要多個終端機時就多開幾個 `exec.sh`。
- 容器第一次啟動時若工作區沒建置過，entrypoint 會自動 `colcon build`。之後修改既有的 Python／launch／YAML 不用重 build；**新增檔案**（場景、world、套件）才要在容器內 `cd /ros_ws && colcon build --symlink-install`。
- 收工：`cd docker/amr_sim && docker compose down`。

---

## 使用流程

### 1. 編寫場景 YAML，產生 world

倉庫用一份 YAML 描述，產生器把它轉成 Gazebo 的 world（`.sdf`）：

```
ros_ws/src/amr_worlds/scenes/<檔名>.yaml  ──gen_world──▶  ros_ws/src/amr_worlds/worlds/<name>.sdf
```

**① 寫 YAML**（例如 `scenes/my_warehouse.yaml`；座標原點在地板左下角，x 往右、y 往上，單位公尺／弧度）：

```yaml
name: my_warehouse             # 必填，會變成 world 名稱與 .sdf 檔名（只能英數字、_、-）
size: [20, 15]                 # 必填，地板 [x, y]；四面外牆與地板自動產生

walls:                         # 內牆（線段）
  - {from: [12, 6], to: [12, 15]}
shelves:                       # 貨架（長方體）：中心、[長, 寬, 高]、yaw
  - {pos: [3, 8], yaw: 0, size: [2.0, 0.6, 1.8]}
obstacles:                     # 障礙物：box 或 cylinder
  - {type: box, pos: [7, 4], size: [1.0, 1.0, 1.0]}
  - {type: cylinder, pos: [17, 12], radius: 0.3, height: 1.2}
```

完整欄位、預設值與驗證規則見 [`amr_worlds/README.md`](ros_ws/src/amr_worlds/README.md)；範例是 [`scenes/warehouse_small.yaml`](ros_ws/src/amr_worlds/scenes/warehouse_small.yaml)。**車輛出生點不寫在場景裡**（第 4 步啟動車子系統時指定）。

**② 產生 world**（sim 容器）：

```bash
ros2 run amr_worlds gen_world /ros_ws/src/amr_worlds/scenes/my_warehouse.yaml
# → /ros_ws/src/amr_worlds/worlds/my_warehouse.sdf
cd /ros_ws && colcon build --symlink-install     # 新的 .sdf 要 build 一次才會安裝（第 2 步才找得到）
```

- YAML 有錯（缺欄位、尺寸 ≤ 0、元素超出地板）時會指出哪個元素哪個欄位，而且**不會寫入或覆蓋任何檔案**。
- 同一份 YAML 每次產生的 `.sdf` 完全相同，`.sdf` 納入版控，可用 `git diff` 看變化。
- 之後改 YAML：重新執行 `gen_world` 覆蓋同名 `.sdf`、重啟世界即可（已安裝過的檔案是 symlink，不用再 build）。
- 想在 Gazebo GUI 裡微調：另存為 `worlds/<name>_edited.sdf`、`colcon build`，第 2 步以 `world:=<name>_edited` 載入；產生器不會覆蓋 `_edited.sdf`。

### 2. 啟動世界

sim 容器：

```bash
ros2 launch amr_worlds world.launch.xml                     # 預設 world:=warehouse_small
ros2 launch amr_worlds world.launch.xml world:=my_warehouse # 第 1 步產生的
```

- Gazebo 視窗出現倉庫，**此時世界裡沒有車**（車由第 4 步的車子系統放進來）。世界同時發布模擬時間 `/clock`。
- `headless:=true`：不開 GUI（光達照常運作，測試用）。
- 停止：Ctrl+C，或直接關掉 Gazebo 視窗（launch 會跟著結束）。
- 看光達光束：Gazebo 右上角 ⋮ → Visualize Lidar → Topic 選 `/amr1/scan`（第 4 步之後；沒有就按 refresh）。

### 3. 車輛模型：amr_description 的 URDF

車輛定義在 [`ros_ws/src/amr_description/urdf/amr.urdf.xacro`](ros_ws/src/amr_description/urdf/amr.urdf.xacro)。xacro 是有變數與巨集的 URDF，展開後同一份 URDF 同時給兩個地方用：Gazebo 生成車體（含外掛與感測器），robot_state_publisher 發布車身各零件的 TF。**這一步不用執行指令**，第 4 步會自動展開；想看展開結果：

```bash
xacro /ros_ws/src/amr_description/urdf/amr.urdf.xacro robot_id:=amr1 > /tmp/amr.urdf
check_urdf /tmp/amr.urdf          # 印出 link 樹
```

**結構**（link 名稱不帶前綴；TF 裡的 `amr1/` 由 robot_state_publisher 的 `frame_prefix` 加上）：

```
base_footprint（地面投影，導航用的車體座標）
└─ base_link（輪軸高度）
   ├─ left_wheel_link / right_wheel_link    驅動輪（continuous joint）
   ├─ front_caster_link / rear_caster_link  支撐球（固定、零摩擦）
   ├─ laser_link                            2D 光達（前方 0.15 m、車頂上）
   └─ imu_link
```

**規格**（檔案開頭的 `xacro:property`，改這裡就好；建圖／導航的參數有測試會比對這些值）：

| 項目 | 值 |
|---|---|
| 車身 | 0.5 × 0.4 × 0.2 m，15 kg |
| 驅動輪 | 半徑 0.08 m、寬 0.04 m、輪距 0.44 m |
| 速度上限 | 1.0 m/s、1.5 rad/s；加速度 2.5 m/s²、5.0 rad/s² |
| 光達 | 360 點、0.12–12 m、10 Hz（gpu_lidar） |
| IMU | 100 Hz |

**Gazebo 外掛**（只在模擬時作用，真車不需要）：

| 外掛／感測器 | Gazebo 端 topic | 作用 |
|---|---|---|
| DiffDrive | 收 `/amr1/cmd_vel_gz`；發 `/amr1/odom`、`/amr1/tf` | 依速度指令轉動兩輪、積分出里程計（30 Hz） |
| JointStatePublisher | `/amr1/joint_states` | 輪子轉角 |
| gpu_lidar | `/amr1/scan` | 依車在世界中的實際位置算光達 |
| imu | `/amr1/imu` | |

Gazebo 的 topic 由虛擬驅動的 bridge 轉成 ROS topic（第 4 步）。驅動輪的**碰撞形狀是球**（外觀是圓柱）：圓柱的接觸點會落在輪緣、讓有效輪距變小，原地旋轉時 odom 會少算約 10%，SLAM 地圖會扭曲（[筆記 17](docs/學習筆記/17-存圖與地圖格式.md)）。

### 4. 啟動車子系統，把車放進世界

robot 容器（世界已在執行）：

```bash
ros2 launch amr_bringup robot.launch.xml hardware:=sim x:=1 y:=1
```

- `hardware:=sim` **必填**（`real` 目前會提示尚未提供真車驅動）。`x`、`y`、`yaw` 是出生位置（公尺、弧度，預設 0）。
- 啟動的東西：robot_state_publisher（第 3 步的 URDF → 車身 TF）＋虛擬驅動：把車放進世界（世界還沒起來會等）、cmd_vel 逾時停車（0.5 s 沒指令就停）、bridge（`/amr1/cmd_vel` 進 Gazebo；scan、odom、imu、joint_states、TF 出來）。
- 車輛出現在 Gazebo 的 (1, 1)，車頭朝 +x。
- 停止：Ctrl+C，車停下並留在世界中、Gazebo 繼續跑；再啟動會把車移回出生點（不會出現兩台）。

確認與試開（robot 容器另開 shell）：

```bash
ros2 topic list                                   # /amr1/scan、/amr1/odom、/amr1/imu ...
ros2 topic hz /amr1/scan                          # 約 10 Hz
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/amr1/cmd_vel
#   i 前進、j／l 轉向、k 停止；關掉 teleop 後 1 秒內停車
```

### 5. 掃圖（建圖、存圖）

世界與車子系統都在執行。建圖用 slam_toolbox：一邊開車，一邊把光達掃到的東西畫成 2D 地圖。

**5.1 建圖 + RViz**（robot 容器）：

```bash
ros2 launch amr_rviz_plugins mapping_ui.launch.xml use_sim_time:=true
```

RViz 開啟，顯示地圖、光達、車身，左下角是 **「AMR 建圖」面板**。

**5.2 開車掃圖**（robot 容器另開 shell）：

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/amr1/cmd_vel
```

- **慢慢開**：按幾次 `z`（每次速度上限降 10%，預設 0.5 m/s）降到 0.3 m/s 左右；太快掃描比對容易失敗，地圖會扭曲。
- **沿著牆繞一圈，最後回到起點**：回到看過的地方時 slam_toolbox 會「閉環」，修正累積誤差。
- 面板狀態列顯示地圖尺寸、已知比例、最後更新時間，開到新區域會跟著變。

**存圖**：在面板輸入**地圖名稱** → 按 **「存圖」** → 確認視窗顯示 `/data/maps/<名稱>.pgm`／`.yaml` → Yes。面板顯示「已存」，檔案在主機的 `docker/amr_sim/data/maps/`。

- 建圖中隨時可以存，不用停止；**同名會覆蓋**（確認視窗會提醒）。`data/maps/` 有進 git，覆蓋錯了可用 git 還原。
- 名稱只能用英數字、`_`、`-`；「存圖」按鈕是灰的表示存圖服務還沒就緒（建圖剛啟動）。
- **從出生點 `x:=1 y:=1` 開始建圖**：`map` 座標系的原點是開始建圖時車的位置，repo 的地圖都遵守這個慣例（世界座標 = 地圖座標 + (1, 1)）。
- 關掉 RViz 視窗，建圖一起結束；車子系統繼續跑，可以直接進第 6 步，車留在原地。
- 存出的格式（`.pgm` 灰階圖：白＝空曠、黑＝障礙、灰＝未知；`.yaml`：解析度、原點、門檻）見[筆記 17](docs/學習筆記/17-存圖與地圖格式.md)。

不開 RViz 的替代方式：`ros2 launch amr_navigation mapping.launch.xml use_sim_time:=true`，存圖用 `ros2 run nav2_map_server map_saver_cli -f /data/maps/<名稱> --ros-args -r map:=/amr1/map -p use_sim_time:=true`。

### 6. 導航

世界與車子系統都在執行（掃圖已關掉）。在存好的地圖上定位（map_server + AMCL），點目標讓車自己開過去（Nav2：NavFn 規劃 + DWB 控制）。

robot 容器：

```bash
ros2 launch amr_navigation navigation.launch.xml use_sim_time:=true map:=warehouse_small
```

robot 容器另開 shell：

```bash
rviz2 -d $(ros2 pkg prefix --share amr_navigation)/config/navigate.rviz
```

RViz 操作順序：

1. 工具列 **2D Pose Estimate**：在地圖上車子實際所在位置按下、拖出車頭方向。綠色箭頭（AMCL 粒子）聚到車周圍，紅色光達點和地圖的牆對齊。**沒給初始位姿前導航不會啟動**（終端機一直出現等待 `map` 的訊息是正常的）。
2. 工具列 **2D Goal Pose**：點目標、拖出方向。藍線是規劃的路徑，車子開過去後停下。
3. 目標在障礙物裡或到不了：Nav2 先試著脫困（原地轉、後退、等待），仍不行就放棄並停車（終端機顯示 `Goal failed`）。

- `map:=<名稱>` 載入 `docker/amr_sim/data/maps/<名稱>.yaml`。
- 導航速度上限 0.5 m/s、1.0 rad/s；路上臨時出現的障礙物會繞開或重新規劃。
- **導航時不要同時用 teleop**：兩邊都發 `/amr1/cmd_vel`，會互搶。
- 停止導航（Ctrl+C）後車子 1 秒內停下。
- 平常運作（例如真車開機）可以一行帶起驅動＋導航：`ros2 launch amr_bringup robot.launch.xml hardware:=sim x:=1 y:=1 mode:=navigation map:=warehouse_small`。缺點是之後要建圖得重啟整個車子系統（車會被移回出生點）；建圖一律用第 5 步的方式。

---

## 參考

### launch 參數

launch 檔用 XML 寫（和 ROS 1 的 `<arg>` 相同概念），預設值寫在 launch 檔裡；用 `名稱:=值` 覆寫，`--show-args` 列出所有參數。

| launch | 參數 | 預設 |
|---|---|---|
| `amr_worlds world.launch.xml` | `world`（`worlds/<world>.sdf`） | `warehouse_small` |
| | `headless`（`true` = 不開 GUI） | `false` |
| `amr_bringup robot.launch.xml` | **`hardware`：`sim` 或 `real`（必填）** | 無 |
| | `robot_id`（namespace 與 TF 前綴） | `amr1` |
| | `x`、`y`、`yaw`：模擬時車輛放進世界的位置 | `0` |
| | `mode`：`none`、`navigation` | `none` |
| | `map`：`mode:=navigation` 時載入的地圖 | `warehouse_small` |
| `amr_rviz_plugins mapping_ui.launch.xml` | `robot_id`、`use_sim_time`（模擬時要 `true`） | `amr1`、`false` |
| `amr_navigation mapping.launch.xml` | `robot_id`、`use_sim_time` | `amr1`、`false` |
| `amr_navigation navigation.launch.xml` | `robot_id`、`use_sim_time`、`map` | `amr1`、`false`、`warehouse_small` |

其他設定：
- `docker/amr_sim/config/ros.env`：兩個容器共用的 `ROS_DOMAIN_ID`（同網段有別人跑 ROS 2 時改成少見的數字；改完 `up.sh gpu all` 重建容器）。
- `docker/amr_sim/data/`：執行時產生的資料（地圖），掛載到 robot 容器的 `/data`，檔案在主機上屬於你。
- UID 不是 1000 的主機：`build.sh` 會自動帶入；直接用 `docker compose build` 時先 `export USER_UID=$(id -u) USER_GID=$(id -g)`。

### 沒有 NVIDIA GPU：軟體渲染

```bash
docker/amr_sim/up.sh cpu all     # 兩個容器改用 llvmpipe（CPU 繪圖）
docker/amr_sim/up.sh gpu all     # 切回 GPU
docker/amr_sim/up.sh cpu robot   # 只有 robot 用 CPU（排查繪圖問題時；sim 不受影響）
```

### 測試

```bash
# robot 容器內（整合測試會同時啟動世界與車子系統，導航測試需要 /data 的地圖）
cd /ros_ws && colcon build --symlink-install
colcon test && colcon test-result --verbose                     # 全部（含 3 個啟動模擬的冒煙測試，約 2 分鐘）
cd src/amr_hw_sim && launch_test test/test_navigation_smoke.py   # 單一冒煙測試的每項結果

# 純邏輯測試不需要 ROS（任一容器）
cd /ros_ws/src/amr_worlds && env -i PATH=/usr/bin:/bin python3 -m pytest -q test
```

冒煙測試：`test_sim_smoke`（車輛介面）、`test_mapping_smoke`（建圖、存圖）、`test_navigation_smoke`（定位、導航、失敗回報；用 `warehouse_small` 地圖）。模擬開著時也能跑：先 `export ROS_DOMAIN_ID=<少見的數字> IGN_PARTITION=test`，就不會和開著的世界互相干擾。

### 疑難排解

| 症狀 | 原因與處理 |
|---|---|
| `docker: permission denied` | 沒加入 docker 群組或沒重新登入（筆記 01） |
| Gazebo 開得很慢、renderer 是 llvmpipe | 容器內 `glxinfo -B` 檢查；確認 toolkit 與驅動（筆記 02、03），或是不小心用了 `up.sh cpu` |
| `ros2 topic list` 看得到 topic 但收不到資料 | 容器沒有 `ipc: host`（筆記 06） |
| `Unable to find or download file`，世界的 launch 隨即結束 | world 名稱打錯，或新產生的 world 還沒 `colcon build`（launch 第一行會印出嘗試載入的路徑） |
| `gen_world` 報錯 | 訊息會指出哪個元素哪個欄位；不會寫入任何檔案，改好 YAML 再執行 |
| 車子系統啟動報 `missing required argument 'hardware'` | 要加 `hardware:=sim` |
| RViz 面板的中文是方塊 | 容器是舊映像：`build.sh` 後 `up.sh gpu all` |
| map_saver 一直等不到地圖 | 少了 `-r map:=/amr1/map`；或建圖沒在跑 |
| RViz 沒有地圖 | Map 的 Durability 要 Transient Local；建圖剛啟動要等幾秒（每 2 秒更新一次） |
| 導航啟動後一直印等待 `map` 的訊息、`ros2 lifecycle get` 卡住 | 還沒給初始位姿：在 RViz 點 2D Pose Estimate |
| RViz 點 2D Pose Estimate／2D Goal Pose 沒反應 | 工具的 topic 沒帶 namespace；用 `navigate.rviz` 開 RViz（`/amr1/initialpose`、`/amr1/goal_pose`） |
| `Failed to load map yaml file: /data/maps/xxx.yaml` | 地圖名稱打錯，或 robot 容器沒有 `/data` 掛載（`up.sh gpu all` 重建容器） |
| `Lookup would require extrapolation`、costmap 一直等 TF | 有節點沒用模擬時間：單獨啟動建圖／導航時要加 `use_sim_time:=true` |
| 目標點在牆邊回報失敗 | 目標落在障礙物或膨脹範圍內；點遠一點（刻意不改去附近的替代點，避免停在錯的位置卻回報成功） |
| build 報 `can't copy ... doesn't exist` | 刪除或改名原始檔後 `build/` 留下斷掉的 symlink：刪除該套件的 `ros_ws/build/<套件>`、`ros_ws/install/<套件>` 後重建 |
| 外接螢幕接在 NVIDIA、Wayland 黑畫面 | `/etc/gdm3/custom.conf` 設 `WaylandEnable=false` 改用 Xorg（筆記 02） |
