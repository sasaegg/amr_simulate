# AMR SLAM 模擬

ROS 2 Humble + Gazebo Fortress 的倉庫 AMR 模擬環境：可編輯的倉庫場景、一台帶 2D 光達與 IMU 的差速車，世界與車子系統分開執行——車子系統以「硬體模式」切換虛擬（Gazebo）或真實驅動，之後的 SLAM、導航、派車都建立在同一套車子系統上。

子專案 1（本 repo 目前的範圍）：模擬環境。規格見 [`openspec/specs/`](openspec/specs/)，設計與任務紀錄見 [`openspec/changes/archive/2026-10-08-add-sim-environment/`](openspec/changes/archive/2026-10-08-add-sim-environment/)，逐步學習筆記見 [`docs/學習筆記/`](docs/學習筆記/README.md)。

## 架構

```
┌──────────────── robot 容器：車子系統（之後部署到真車）────────────────┐   ┌──── sim 容器 ────┐
│ robot.launch.xml（中控）  hardware:=sim | real                         │   │ world.launch.xml │
│  ├ robot_state_publisher                                               │   │  ├ Gazebo 世界   │
│  └ hardware: sim → 虛擬驅動（amr_hw_sim）                               │◀─▶│  └ /clock        │
│       ├ 虛擬底盤：把車放進世界、cmd_vel 逾時停車、odom／TF／joint_states │   │                  │
│       ├ 虛擬光達：/amr1/scan（Gazebo 依車輛實際位置計算）                │   │  真車上不存在     │
│       └ 虛擬 IMU：/amr1/imu                                             │   └──────────────────┘
│    hardware: real → 真車驅動（尚未提供）                                │
└────────────────────────────────────────────────────────────────────────┘
```

| 套件 | 內容 | 真車需要 |
|---|---|---|
| `amr_description` | 車輛模型（xacro） | ✅ |
| `amr_bringup` | 車子系統中控 `robot.launch.xml` | ✅ |
| `amr_worlds` | 場景產生器、world、`world.launch.xml` | ❌ |
| `amr_hw_sim` | 虛擬驅動 `sim_hardware.launch.xml`、冒煙測試 | ❌ |
| `amr_navigation` | 建圖 `mapping.launch.xml`、RViz 設定檔（導航：子專案 2 進行中） | ✅ |

車輛對外介面（硬體介面）：`/amr1/cmd_vel`（輸入）、`/amr1/scan`、`/amr1/odom`、`/amr1/imu`、`/amr1/joint_states`、`/tf`（`amr1/odom → amr1/base_footprint`）、`/tf_static`；模擬時另有 `/clock`。所有 frame 帶 `amr1/` 前綴。

## 主機準備

Ubuntu 22.04，依學習筆記操作（需要 sudo 的步驟由你自己執行）：

1. [docker 群組](docs/學習筆記/01-docker群組.md)：`sudo usermod -aG docker $USER` 後重新登入
2. [NVIDIA 驅動](docs/學習筆記/02-NVIDIA驅動.md)：`nvidia-smi` 看得到 GPU
3. [NVIDIA Container Toolkit](docs/學習筆記/03-NVIDIA-Container-Toolkit.md)：`docker run --rm --gpus all ubuntu nvidia-smi` 成功

沒有 NVIDIA GPU 時可以跳過 2、3，改用軟體渲染（見下方）。

## 建置與啟動

```bash
docker/amr_sim/build.sh          # 建置映像（自動帶入你的 UID/GID）
docker/amr_sim/up_gpu.sh         # 背景啟動 sim、robot 兩個長駐容器（不會開任何視窗）
```

開兩個終端機：

```bash
docker/amr_sim/exec.sh sim       # 終端機 1：進入 sim 容器
ros2 launch amr_worlds world.launch.xml
```

```bash
docker/amr_sim/exec.sh robot     # 終端機 2：進入 robot 容器
ros2 launch amr_bringup robot.launch.xml hardware:=sim x:=1 y:=1
```

Gazebo 視窗出現倉庫，車子系統啟動後車輛出現在 (1, 1)。

- 容器啟動時若工作區還沒建置過（沒有 `ros_ws/install`），entrypoint 會自動 `colcon build`；之後修改 Python／launch／YAML 不需要重新 build，**新增檔案**（新的套件、場景、world）才要在容器內 `cd /ros_ws && colcon build --symlink-install`。
- 停止：各自在 launch 的終端機按 Ctrl+C（或直接關掉 Gazebo 視窗，世界的 launch 會跟著結束）。停止車子系統時車輛會停下並留在世界中；再次啟動會移回出生點。
- 收工：`cd docker/amr_sim && docker compose down`。
- 修改 Dockerfile 後：`docker/amr_sim/up_gpu.sh --build`。
- `exec.sh` 必須指定 `sim` 或 `robot`。

### UID 不是 1000 的主機

`build.sh` 會自動帶入 `id -u`／`id -g`。若直接用 `docker compose build`，先執行：

```bash
export USER_UID=$(id -u) USER_GID=$(id -g)
```

## 設定

launch 檔用 XML 寫（和 ROS 1 的 `<arg>` 相同概念），設定全部是 launch 參數，預設值寫在 launch 檔裡；用 `名稱:=值` 覆寫。

| launch | 參數 | 預設 |
|---|---|---|
| `amr_worlds world.launch.xml` | `world`（`worlds/<world>.sdf`） | `warehouse_small` |
| | `headless`（`true` = 不開 GUI） | `false` |
| `amr_bringup robot.launch.xml` | **`hardware`：`sim` 或 `real`（必填）** | 無 |
| | `robot_id`（namespace 與 TF 前綴） | `amr1` |
| | `x`、`y`、`yaw`：模擬時車輛放進世界的位置（公尺、弧度） | `0` |

```bash
ros2 launch amr_worlds world.launch.xml world:=warehouse_small_edited
ros2 launch amr_bringup robot.launch.xml hardware:=sim x:=3 y:=1 yaw:=1.57
ros2 launch amr_bringup robot.launch.xml --show-args     # 列出所有參數與說明
```

兩個容器共用的 ROS 環境變數在 `docker/amr_sim/config/ros.env`：`ROS_DOMAIN_ID`（同網段有別人跑 ROS 2 時改成少見的數字；改完要 `up_gpu.sh` 重建容器）。

## 場景（Gazebo world）

場景以 YAML 描述，產生 Gazebo world（格式與驗證規則見 [`amr_worlds/README.md`](ros_ws/src/amr_worlds/README.md)）：

```bash
# sim 容器內
ros2 run amr_worlds gen_world /ros_ws/src/amr_worlds/scenes/warehouse_small.yaml
```

- 結構變更（牆、貨架、障礙物）：改 YAML → 重新產生 → 重啟世界。
- 細節微調：在 Gazebo GUI 修改後另存為 `ros_ws/src/amr_worlds/worlds/<name>_edited.sdf`，`colcon build` 後以 `world:=<name>_edited` 啟動世界。產生器不會覆蓋 `_edited.sdf`。
- 車輛出生點不屬於場景，在啟動車子系統時以 `x:=`、`y:=`、`yaw:=` 指定。

## 開車與觀察

robot 容器內另開 shell（`docker/amr_sim/exec.sh robot`）：

```bash
# 鍵盤開車（i 前進、j/l 轉向、k 停止）；關掉後 1 秒內停車
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/amr1/cmd_vel

# 觀察
ros2 topic list
ros2 topic hz /amr1/scan
ros2 run tf2_ros tf2_echo amr1/odom amr1/laser_link
rviz2
```

RViz：Fixed Frame 設 `amr1/odom`；Add → `LaserScan`（Topic `/amr1/scan`）、`TF`、`RobotModel`（Description Source `Topic`、Description Topic `/amr1/robot_description`、Durability Policy `Transient Local`、**TF Prefix `amr1`**——URDF 裡的 link 名稱沒有前綴，TF 裡有）。

Gazebo 看光達光束：右上角 ⋮ → Visualize Lidar → Topic 選 `/amr1/scan`（沒有就按 refresh）。

## 建圖與存圖

建圖用 slam_toolbox：一邊用 teleop 開車，一邊把光達掃到的東西畫成 2D 佔據格地圖。地圖存在 `data/maps/`（robot 容器的 `/data/maps`）。

```bash
# 世界與車子系統已在執行（見「建置與啟動」）；robot 容器內另開 shell：
ros2 launch amr_navigation mapping.launch.xml use_sim_time:=true

# 再開一個 shell：RViz（地圖、光達、車身都已設定好）
rviz2 -d $(ros2 pkg prefix amr_navigation)/share/amr_navigation/config/navigate.rviz

# 再開一個 shell：teleop 開車
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/amr1/cmd_vel
```

開法建議：
- **慢慢開**：teleop 按幾次 `z`（每次把速度上限降 10%，預設 0.5 m/s）降到 0.3 m/s 左右；開太快掃描比對容易失敗，地圖會扭曲。
- **沿著牆繞一圈，最後回到起點**：回到看過的地方時 slam_toolbox 會「閉環」（loop closure），修正累積的誤差。
- 從出生點 `x:=1 y:=1 yaw:=0` 開始建圖：`map` 座標系的原點就是開始建圖時車子的位置，repo 內的地圖都遵守這個慣例，所以「世界座標 = 地圖座標 + (1, 1)」。

存圖（建圖中隨時可以存，不需要停止）：

```bash
ros2 run nav2_map_server map_saver_cli -f /data/maps/warehouse_small --ros-args -r map:=/amr1/map -p use_sim_time:=true
```

- 產生 `data/maps/warehouse_small.pgm`（灰階圖片：白＝空曠、黑＝障礙、灰＝未知）與 `warehouse_small.yaml`（解析度、原點、門檻）。
- `-r map:=/amr1/map`：map_saver 預設訂閱 `/map`，地圖在 namespace 下。
- **同名會直接覆蓋**，建新圖請換名字；`data/maps/` 有進 git，覆蓋錯了可以用 git 還原。

## 沒有 NVIDIA GPU：軟體渲染

```bash
docker/amr_sim/up_cpu.sh         # 兩個容器改用 llvmpipe（CPU 繪圖）
docker/amr_sim/up_gpu.sh         # 切回 GPU
```

## 測試

```bash
# sim 容器內
cd /ros_ws && colcon build --symlink-install
colcon test && colcon test-result --verbose            # 全部（含啟動模擬的冒煙測試）
cd src/amr_hw_sim && launch_test test/test_sim_smoke.py   # 冒煙測試的每項結果

# 純邏輯測試不需要 ROS（任一容器）
cd /ros_ws/src/amr_worlds && env -i PATH=/usr/bin:/bin python3 -m pytest -q test
```

## 疑難排解

| 症狀 | 原因與處理 |
|---|---|
| `docker: permission denied` | 沒加入 docker 群組或沒重新登入（筆記 01） |
| Gazebo 開得很慢、renderer 是 llvmpipe | 容器內 `glxinfo -B` 檢查；確認 toolkit 與驅動（筆記 02、03） |
| `ros2 topic list` 看得到 topic 但收不到資料 | 容器沒有 `ipc: host`（筆記 06） |
| map_saver 一直等不到地圖 | 少了 `-r map:=/amr1/map`；或建圖沒在跑 |
| RViz 沒有地圖 | Map 的 Durability 要 Transient Local；建圖剛啟動要等幾秒（每 2 秒更新一次） |
| `Unable to find or download file`，世界的 launch 隨即結束 | world 名稱打錯，或新增的 world 還沒 `colcon build`（launch 第一行會印出嘗試載入的路徑） |
| 車子系統啟動報 `missing required argument 'hardware'` | 啟動時要加 `hardware:=sim` |
| build 報 `can't copy ... doesn't exist` | 刪除原始檔後 `build/` 留下斷掉的 symlink：刪除該套件的 `ros_ws/build/<套件>`、`ros_ws/install/<套件>` 後重建 |
| 外接螢幕接在 NVIDIA、Wayland 黑畫面 | `/etc/gdm3/custom.conf` 設 `WaylandEnable=false` 改用 Xorg（筆記 02） |
