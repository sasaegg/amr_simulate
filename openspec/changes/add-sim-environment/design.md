# Design

## Context

專案從零開始（前一版以 WSL2 為前提的程式與 change 已刪除）。動機見 proposal.md；需求見 specs/。

主機現況（2026-10-06 實查）：
- Ubuntu 22.04.5，GNOME on **Xorg**（`DISPLAY=:0`）。原本為 Wayland，但筆電的 HDMI 輸出接在 NVIDIA 獨顯上，Wayland（mutter 42）下外接螢幕黑畫面，故以 `/etc/gdm3/custom.conf` 的 `WaylandEnable=false` 改用 Xorg（Xorg 以 reverse PRIME 讓 NVIDIA-G0 負責 HDMI 輸出）
- Docker Engine 29.8 已安裝並執行，但使用者尚未加入 `docker` 群組
- 雙顯卡：Intel Alder Lake-P 內顯 + NVIDIA GA106M（RTX 3060 Mobile）；已安裝 `nvidia-driver-580-open`（580.178.04，預編譯模組 `linux-modules-nvidia-580-open-generic-hwe-22.04`）；`ubuntu-drivers` 原推薦 595-open，排查黑畫面過程中改用 580-open 並維持
- Secure Boot 已關閉（安裝驅動不需 MOK 簽章）
- 20 核、30 GB RAM、磁碟可用 219 GB

前一版在 WSL 上實測得到、本次沿用的結論：
- Gazebo 一律使用 ogre2；ogre1 下 gpu_lidar 全部回報 0.12 m，不可用
- Fortress 外掛名稱為 `ignition-gazebo-*`、感測器 frame 用 `<ignition_frame_id>`（`gz-sim-*` 是 Garden 以後的名稱）
- Fortress diff-drive 外掛沒有指令逾時參數

## Goals / Non-Goals

**Goals:**
- 在這台筆電上 `docker compose up sim` 一個指令看到 GPU 加速的倉庫與車，鍵盤可開車。
- 映像不綁定主機驅動版本；同一份 compose 可用於任何裝有 NVIDIA 驅動與 Container Toolkit 的 Ubuntu 主機。
- 車輛介面（topic／frame 命名）一次定型，後續子專案直接沿用。
- 每一步可被解釋：學習筆記記錄原因、驗證與面試追問。

**Non-Goals:**
- slam_toolbox、Nav2 的設定與啟動（子專案 2）。
- 多台車同時模擬（只預留 namespace 與 spawn 結構）。
- 圖形化建築編輯器。
- 真實車輛驅動／硬體介面。
- 自動修改主機系統設定（驅動、toolkit、群組由使用者依筆記親手執行）。

## Decisions

### D1：主機準備順序
`git init` → 加入 `docker` 群組 → NVIDIA 驅動 `nvidia-driver-580-open` → NVIDIA Container Toolkit（`nvidia-ctk runtime configure --runtime=docker`）→ X 存取權確認。
- 驅動必須在 toolkit 之前：toolkit 執行時注入的是主機已安裝的驅動函式庫。
- 選 `-open` kernel module：Turing 之後架構 NVIDIA 官方建議使用開源 kernel module；RTX 3060 為 Ampere。
- `docker` 群組等同 root 權限（可掛載 `/` 進容器），筆記中說明此取捨與 rootless Docker 替代方案。
- X 存取權：容器以與主機相同 UID 執行（見 D3）。實查（2026-10-07，Xorg）`xhost` 已含 `SI:localuser:myuser`，因此預期不需額外放寬；task 2.3 以 xeyes 實測確認，只有不允許時才加 `xhost +SI:localuser:<使用者>`（優於 `+local:`，不開放給本機其他使用者），並包成 `scripts/allow_x.sh`，不修改系統開機設定。

### D2：GPU 透過 NVIDIA Container Toolkit 注入，映像內不裝驅動
compose 以 `deploy.resources.reservations.devices: [{driver: nvidia, count: all, capabilities: [gpu]}]` 要求 GPU，並設定 `NVIDIA_DRIVER_CAPABILITIES=all`。
- 容器與主機共用 kernel，kernel module 只能在主機；使用者層函式庫（libGLX_nvidia、libcuda…）與 kernel module 之間是私有介面、版本必須完全一致。toolkit 在容器啟動時注入與主機匹配的使用者層函式庫與 `/dev/nvidia*`，因此映像可攜、主機升級驅動不需重建映像。
- 注入路徑（實測 2026-10-07，Docker 29.8 + Toolkit 1.20.1）：`--gpus`／compose `deploy.devices` 由 Docker 直接走 **CDI**（spec 由 `nvidia-cdi-refresh` 自動產生於 `/var/run/cdi/nvidia.yaml`）；`--runtime=nvidia` 在 `mode = "auto"` 下也解析為 CDI。CDI 模式會注入全部驅動函式庫（實測 59 個，含 GLX／EGL），**不受 `NVIDIA_DRIVER_CAPABILITIES` 影響**。
- 仍設定 `NVIDIA_DRIVER_CAPABILITIES=all`：在舊版 toolkit 或 legacy 模式（預設只有 `compute,utility`，不含 OpenGL 所需的 `graphics`）的主機上，不設定會導致 Gazebo 退回軟體渲染或崩潰；設定後兩種模式都正確，成本為零。
- 替代方案：映像內裝相同版本的使用者層驅動（`--no-kernel-module`）→ 映像綁死驅動版本、主機自動更新後即壞（錯誤如 `Driver/library version mismatch`，或無聲退回 llvmpipe）。用 Intel 內顯（掛 `/dev/dri`、Mesa 在容器內）→ Mesa 經穩定的 DRM uAPI 與 kernel 溝通所以可行，但 ogre2 + gpu_lidar 效能不足，且 3D SLAM 子專案終究需要 NVIDIA。
- 雙顯卡：設 `__NV_PRIME_RENDER_OFFLOAD=1`、`__GLX_VENDOR_LIBRARY_NAME=nvidia`，讓 GLVND 把 OpenGL 分派給 NVIDIA，再把畫面交給負責顯示的 X server。

### D3：映像
單一 `docker/ros.Dockerfile`，`FROM osrf/ros:humble-desktop`（含 rviz2、rqt；官方 `ros:humble` 只有 core/base），一個 `RUN` 內 `apt-get update && apt-get install --no-install-recommends … && rm -rf /var/lib/apt/lists/*` 安裝 `ros-humble-ros-gz`、`navigation2`、`nav2-bringup`、`slam-toolbox`、`teleop-twist-keyboard`、`xacro`、`python3-pytest`、`python3-yaml`、`mesa-utils`、`x11-apps`。
- update 與 install 同層：避免 update 層被快取而用到過期索引；清除 apt 清單必須在同層才會縮小映像。
- 層順序由少變動到常變動。
- 以 `ARG USER_UID`／`USER_GID`（預設 1000，compose 由 `.env` 傳入）建立與主機同 UID 的使用者並以其執行：掛載的工作區中產生的檔案不會變成 root 擁有；同 UID 也讓 X 存取權不需對外放寬。
- Nav2／slam_toolbox 先裝：換取子專案 2 不需重建映像，代價約 +1 GB。
- 不用 `nvidia/cuda` 基底：Gazebo 繪圖只需要 OpenGL，驅動函式庫由 toolkit 注入。
- 不用 rosdep 自動安裝：第一版相依明確且少，直接列出較易解釋；套件 `package.xml` 仍完整宣告相依。

### D4：entrypoint 與程序管理
`docker/entrypoint.sh`：source `/opt/ros/humble/setup.bash` → 若 `/ros_ws/install` 不存在或 `BUILD=1` 則 `colcon build --symlink-install` → source `install/setup.bash` → `exec "$@"`。compose 設 `init: true`。
- `exec` 讓目標程式成為 PID 1 的直接子程序（init 之下），訊號可正確送達，Ctrl+C／`docker stop` 能正常收尾。
- `init: true`（tini）回收 Gazebo 產生的子程序，避免殭屍程序與關閉時殘留。
- `--symlink-install`：Python 與 launch 檔以 symlink 安裝，修改後免重建。

### D5：compose 結構
- 根目錄 `compose.yaml`（專案根目錄直接 `docker compose up sim`）；`.env` 移至根目錄（compose 只自動讀取專案目錄的 `.env`），內含 `ROS_DOMAIN_ID`、`WORLD`、`USER_UID`、`USER_GID`。
- 共用設定以 extension field + YAML anchor（`x-ros-common: &ros-common`）定義，供之後 `nav`、`backend` service 沿用。
- `sim` service：`network_mode: host`、`ipc: host`、`init: true`、GPU 設定（D2）、`DISPLAY`、`/tmp/.X11-unix:/tmp/.X11-unix:ro`、`./ros_ws:/ros_ws`、`command: ros2 launch amr_bringup sim.launch.py world:=${WORLD}`。
- `network_mode: host`：DDS 以 multicast 探索，bridge 網路下不穩；host 網路讓主機與其他容器直接可見。
- `ipc: host`：Fast DDS 對同主機節點預設使用 shared memory 傳輸；容器若 IPC namespace 不同，會出現「topic 列得出來但收不到資料」。同時讓 X11 MIT-SHM 可用，不需要 `QT_X11_NO_MITSHM`。
- `compose.software.yaml` 疊加檔：以 `deploy: !reset {}` 移除 GPU 要求，設 `LIBGL_ALWAYS_SOFTWARE=1`、`__GLX_VENDOR_LIBRARY_NAME=mesa`、`__NV_PRIME_RENDER_OFFLOAD=0`、`MESA_GL_VERSION_OVERRIDE=3.3`；使用方式 `docker compose -f compose.yaml -f compose.software.yaml up sim`。

### D6：工作區三個套件
依「變動原因」切分：地圖、車、組裝各自獨立；子專案 2 起只在 bringup 層新增 launch。

- `amr_worlds`（ament_python）：`gen_world`（`ros2 run amr_worlds gen_world <yaml>`）。純 Python：pyyaml 讀檔 → 自寫 schema 驗證（欄位少，不引入 jsonschema）→ `xml.etree` 輸出 SDF。固定元素順序與數值格式以保證輸出可重現。先寫到暫存檔、驗證全部通過後才取代目標檔，確保失敗時不動既有輸出。牆為 box link（長度=兩點距離、中心=中點、yaw=atan2），貨架 box，障礙物 box／cylinder，全部放在一個 `static` model 中、每個元素一個 link，具 visual 與 collision。world 載入 `ignition-gazebo-physics-system`、`-user-commands-system`、`-scene-broadcaster-system`、`-sensors-system`（`render_engine` ogre2）、`-imu-system`。`.sdf` 納入版控；`*_edited.sdf` 同目錄，產生器只寫 `<name>.sdf`。launch 經環境變數 `AMR_WORLDS_DIR` 從原始碼目錄讀 world 與場景，改 YAML 不需 colcon build。
- `amr_description`（ament_cmake，只安裝資料檔）：`urdf/amr.urdf.xacro`，參數 `robot_id`。底盤 0.5×0.4×0.2 m、兩驅動輪、前後萬向輪（低摩擦球）、`laser_link`、`imu_link`，各 link 具 visual／collision／inertial。外掛：`ignition-gazebo-diff-drive-system`（topic `/<id>/cmd_vel_gz`、odom ≥ 20 Hz、frame `<id>/odom → <id>/base_footprint`、速度上限 1.0 m/s／1.5 rad/s）、`ignition-gazebo-joint-state-publisher-system`、`gpu_lidar`（360 樣本、0.12–12 m、10 Hz）、`imu`（100 Hz）。gpu_lidar 以 GPU 深度影像換算距離，因此依賴渲染引擎——這是 ogre1 失效、以及需要 GPU 的原因。
- `amr_bringup`（ament_python）：
  - `sim.launch.py`：參數 `world`、`robot_id`、`headless`（預設 false）。啟動 `ign gazebo`（headless 時 `-s --headless-rendering`，以 EGL 離屏渲染）→ 由場景 YAML 讀取 spawn（edited world 退回同名去 `_edited` 的 YAML，再退回原點）→ `ros_gz_sim create` → `ros_gz_bridge`（YAML 設定，由 robot_id 產生）→ `robot_state_publisher`（namespace、`frame_prefix: <id>/`、`use_sim_time`）→ watchdog。生成車輛的部分包成 `spawn_robot(robot_id, pose)`，多車時迴圈呼叫。
  - `cmd_vel_watchdog`：判斷邏輯為純 Python 類別、時間由外部傳入（可不等真實時間、不啟動 ROS 即測試）；rclpy 節點只是外殼。只做轉發與逾時（0.5 s 送一次零速度，之後不重複），截斷交給外掛。理由：Fortress diff-drive 無逾時參數，teleop 當掉時車會持續前進——deadman 設計。
  - bridge：`/clock`（gz→ros）、`/<id>/odom`、`/<id>/scan`、`/<id>/imu`、`/<id>/joint_states`、`/tf`（diff-drive 的 odom tf，gz→ros）、`/<id>/cmd_vel_gz`（ros→gz）。

TF 樹：`amr1/odom → amr1/base_footprint → amr1/base_link → amr1/{laser_link, imu_link, 輪}`；子專案 2 的 slam_toolbox 再加 `map → amr1/odom`（REP-105：odom 連續會漂移、map 不漂移會跳動）。

### D7：測試策略
- 單元（pytest，無 ROS）：`gen_world` 的產生、預設值、各驗證錯誤、可重現性、牆座標計算、失敗不覆蓋；watchdog 邏輯類別。先寫測試、確認失敗、再實作。
- 靜態：pytest 中執行 xacro 展開並 `check_urdf`，檢查外掛參數存在。
- 整合：`launch_testing` 冒煙測試，以 `headless:=true` 啟動，涵蓋 simulated-amr 與 sim-runtime 中可自動化的情境（scan/odom 30 s 內有資料、namespace、TF、位移、逾時停車、超速截斷、暫停 `/clock`、正前方光達讀值）。以 `docker compose run --rm sim colcon test --packages-select amr_bringup` 執行。
- 手動驗收：GPU renderer、`nvidia-smi` 看得到 gazebo、軟體渲染疊加檔、GUI 互動、teleop、RViz、另一容器 echo、改 YAML 不重建、edited world。

### D8：學習筆記與 commit 節奏
`docs/學習筆記/NN-主題.md`，固定段落：為什麼要做／做了什麼／怎麼驗證／面試追問／踩坑紀錄（無則省略）；`README.md` 為目錄。每完成一步，程式與筆記同一個 commit。篇目：00 git、01 docker 群組、02 NVIDIA 驅動、03 Container Toolkit、04 Dockerfile、05 entrypoint、06 compose 與容器內 GPU／X11、07 ROS 工作區與 colcon、08 場景產生器、09 車輛 xacro、10 bridge 與 watchdog、11 launch 整合、12 冒煙測試、13 README 與最終驗收。

## Risks / Trade-offs

- [外接螢幕接在 NVIDIA 時 Wayland 黑畫面]（已發生）→ 改用 Xorg（`WaylandEnable=false`）；容器只依賴標準 X11，不受影響。日後升級到 Ubuntu 24.04（mutter 較新）可再評估 Wayland。
- [PRIME offload 設定後仍由 Intel 繪圖] → 以 `glxinfo -B` 驗證 renderer；若失敗，檢查容器內是否有 `libGLX_nvidia.so.0`（legacy 模式下需 `NVIDIA_DRIVER_CAPABILITIES` 含 graphics）、`prime-select query` 是否為 `on-demand` 或 `nvidia`。
- [headless 模式的 EGL 離屏渲染在此驅動組合下失敗] → 冒煙測試先嘗試 `--headless-rendering`；不行則改為在有 `DISPLAY` 的環境下以 `-s` 執行（server 端仍會以 GPU 渲染光達），並記錄於踩坑紀錄。
- [`deploy: !reset` 需要 compose v2.24+] → 主機為 Docker 29.8 附帶的 compose plugin，符合；筆記註明版本需求。
- [同 UID 使用者在其他主機 UID 不是 1000] → `USER_UID`／`USER_GID` 由 `.env` 設定，README 說明以 `id -u` 填入。
- [`docker` 群組等同 root] → 單人開發機可接受；筆記說明 rootless Docker 替代方案。
- [GUI 另存的 `_edited.sdf` 與 YAML 不再同步] → 刻意取捨：結構變更改 YAML，細節微調用 GUI 另存。
- [預先安裝 Nav2／slam_toolbox 讓映像變大] → 換取子專案 2 不需重建。

## Migration Plan

全新專案。舊 change 已刪除（`docker/.env` 移至根目錄 `.env`）。回滾即刪除容器與映像；主機端驅動與 toolkit 可用 apt 移除。
