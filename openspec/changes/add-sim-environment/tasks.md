# Tasks

每個 task 的節奏：說明原因 → 執行（`sudo` 指令由使用者親手執行；檔案由 Claude 撰寫並逐段解釋）→ 驗證 → 寫學習筆記 → commit → 使用者確認後才進下一個。筆記格式見 design.md D8。

## 1. 主機準備

- [x] 1.1 （筆記 00）`git init`；建立 `.gitattributes`（`* text=auto eol=lf`）、`.gitignore`（`build/`、`install/`、`log/`、`__pycache__/`、`.pytest_cache/`、`.env.local`）、`docs/學習筆記/README.md` 目錄頁與 `00-git與換行設定.md`；把現有 `openspec/`、`docs/開發摘要.md` 一併納入首次 commit。驗證：`git status` 乾淨、`git log` 有首次 commit、`git check-attr eol -- openspec/config.yaml` 顯示 `lf`
- [x] 1.2 （筆記 01）使用者執行 `sudo usermod -aG docker $USER` 後重新登入；筆記說明 socket 權限、docker 群組等同 root、rootless 替代方案。驗證：`id -nG` 含 `docker`、不加 sudo 執行 `docker run --rm hello-world` 成功
- [x] 1.3 （筆記 02）使用者安裝 `nvidia-driver-580-open`（原計畫 595-open，排查黑畫面時改用）並重開機；筆記說明 kernel 層／使用者層、open kernel module、Secure Boot 與 MOK、PRIME `on-demand`、登入後 session 類型。驗證：`nvidia-smi` 顯示 RTX 3060 與驅動版本、`prime-select query` 輸出、`echo $XDG_SESSION_TYPE` 記錄於筆記
- [x] 1.4 （筆記 03）使用者加入 NVIDIA Container Toolkit apt 來源、安裝 `nvidia-container-toolkit`、執行 `sudo nvidia-ctk runtime configure --runtime=docker` 並重啟 docker；筆記說明 toolkit 注入機制、`daemon.json` 變化、為何映像不裝驅動、Intel/Mesa 對照。驗證：`cat /etc/docker/daemon.json` 含 `nvidia` runtime、`docker run --rm --gpus all ubuntu nvidia-smi` 顯示 RTX 3060

## 2. 映像與 compose

- [x] 2.1 （筆記 04）撰寫 `docker/amr_sim/Dockerfile`（D3：`osrf/ros:humble-desktop`、單一 RUN 安裝套件並清 apt 清單、`USER_UID`／`USER_GID` 建立同 UID 使用者）。驗證：`docker build -t amr-sim:humble docker/amr_sim` 成功；`docker run --rm <image> ign gazebo --version` 顯示 Fortress 6.x；`docker history` 觀察層與大小並記錄於筆記
- [x] 2.2 （筆記 05）撰寫 `docker/amr_sim/entrypoint.sh`（D4：source ROS、條件式 `colcon build --symlink-install`、`exec "$@"`）並接入 Dockerfile；Dockerfile 將 ROS／工作區 setup 寫入 `~/.bashrc`。驗證：重建映像後 `docker run --rm <image> bash -c 'echo $ROS_DISTRO'` 輸出 `humble`；筆記以 `ps` 說明有無 `exec` 時 PID 的差異；`docker exec -it <container> bash` 進入後 `ros2 --help` 可用（驗證 `.bashrc`）
- [x] 2.3 （筆記 06）撰寫 `docker/amr_sim/compose.yaml`（D5：`name: amr_sim`、sim 完整展開、`command: ["sleep", "infinity"]`、host 網路、`ipc: host`、`init: true`、GPU 設定、PRIME 變數、X11、`../../ros_ws` 掛載），建立 `docker/amr_sim/config/ros.env`（`ROS_DOMAIN_ID=0`）以 `env_file` 載入、`./config` 可寫掛載到 `/config`，`USER_UID`／`USER_GID` 以 compose 預設值 `${USER_UID:-1000}` 傳入；撰寫 D5a 的 `build.sh`、`up_gpu.sh`、`exec.sh`；依 D1 以 `xhost` 檢查 X 存取權，必要時加 `allow_x.sh`。驗證：在專案外的目錄執行 `docker/amr_sim/build.sh` 成功；`up_gpu.sh` 立即返回且容器持續執行、PID 1 為 `docker-init`；以 `exec.sh` 進入後：`xeyes` 視窗出現在桌面、`glxinfo -B` renderer 為 NVIDIA、`ign gazebo shapes.sdf` 開啟且可旋轉且主機 `nvidia-smi` 看得到該程序、`echo $ROS_DOMAIN_ID` 輸出 0、在 `/ros_ws` 與 `/config` 建立的檔案於主機上屬於使用者（驗證後刪除）；`docker compose down` 1 秒內完成
- [x] 2.4 （筆記 06 補充段）撰寫 `compose.software.yaml` 與 `up_cpu.sh`（up.sh 改名為 `up_gpu.sh`）（`deploy: !reset {}`、`LIBGL_ALWAYS_SOFTWARE=1`、`__GLX_VENDOR_LIBRARY_NAME=mesa`、`__NV_PRIME_RENDER_OFFLOAD=0`）。放在 `docker/amr_sim/`。驗證：於 `docker/amr_sim/` 執行 `docker compose -f compose.yaml -f compose.software.yaml up -d sim` 後 exec 進入，`glxinfo -B` renderer 為 `llvmpipe`，且 `ign gazebo shapes.sdf` 可開啟；之後以 `up_gpu.sh` 恢復 GPU 設定
- [x] 2.5 （筆記 06 補充段）驗證容器間 DDS 互通：長駐容器（`exec.sh`）與另一個一次性容器（於 `docker/amr_sim/` 執行 `docker compose run --rm sim bash`）分別執行 `ros2 run demo_nodes_cpp talker` 與 `listener`，listener 持續收到訊息；筆記記錄暫時拿掉 `ipc: host` 時的現象（看得到 topic 但收不到資料或收得到——如實記錄）後恢復設定

## 3. ROS 工作區與場景產生器（world-generation）

- [ ] 3.1 （筆記 07）建立 `ros_ws/src/amr_worlds`（ament_python：`package.xml`、`setup.py`、`setup.cfg`、`resource/`，安裝 `worlds/`、`scenes/`，entry point `gen_world`）；筆記說明 colcon、ament_python 與 ament_cmake 差異、`--symlink-install`、overlay 與 underlay。驗證：容器內 `colcon build` 成功、`ros2 pkg list` 含 `amr_worlds`
- [ ] 3.2 （筆記 08）先寫 `amr_worlds/test/test_gen_world.py` 的正向測試：範例場景可產生、檔名 = `name`、兩次輸出逐位元組相同、地板與四面外牆存在、牆中心／長度／yaw 計算正確、省略 thickness/height 用預設 0.2／2.0、每個元素具 visual 與 collision。驗證：在未 source ROS 的 shell 執行 `python3 -m pytest` 全部失敗（尚未實作）
- [ ] 3.3 （筆記 08）補驗證錯誤測試：缺 `size`、尺寸 ≤ 0、型別錯誤、元素超出邊界（訊息含類型與索引）、spawn 落在元素內或距離 < 0.35 m（訊息含 robot_id 與衝突元素）、錯誤時不產生 `.sdf` 且結束碼非零、既有 `.sdf` 在失敗時內容不變、`<name>_edited.sdf` 不被覆寫。驗證：新增測試全部失敗
- [ ] 3.4 （筆記 08）實作 `amr_worlds/gen_world.py`（D6：載入 → 驗證 → SDF、固定順序與數值格式、暫存檔後取代、world 含 physics／user-commands／scene-broadcaster／sensors(ogre2)／imu 系統）。驗證：3.2、3.3 測試在未 source ROS 的 shell 中全部通過
- [ ] 3.5 （筆記 08）撰寫 `scenes/warehouse_small.yaml`（20×15 m、內牆、兩排貨架含 `[3, 8]` 一座、數個 box／cylinder 障礙物、`spawn: {amr1: [1, 1, 0]}`），以 `ros2 run amr_worlds gen_world` 產生 `worlds/warehouse_small.sdf` 並納入版控；撰寫 `amr_worlds/README.md`（YAML 欄位、預設值、產生指令、「結構改 YAML、細節用 GUI 另存 `_edited.sdf`」）。驗證：`docker compose run --rm sim ign gazebo /ros_ws/src/amr_worlds/worlds/warehouse_small.sdf` 載入無錯誤並顯示場景；依 README 指令重新產生後 `git diff` 無變化

## 4. 模擬車輛（simulated-amr）

- [ ] 4.1 （筆記 09）建立 `ros_ws/src/amr_description`（ament_cmake，安裝 `urdf/`）與 `urdf/amr.urdf.xacro`（參數 `robot_id`；底盤、驅動輪、萬向輪、`laser_link`、`imu_link` 的 visual／collision／inertial，名稱帶 `<robot_id>/` 前綴）；新增 pytest：xacro 展開成功且 `check_urdf` 通過、所有 link 帶前綴。驗證：`colcon test --packages-select amr_description` 通過
- [ ] 4.2 （筆記 09）於 xacro 加入 Fortress 外掛與感測器（D6：diff-drive 的 topic／frame／odom 頻率／速度上限、joint-state-publisher、gpu_lidar 360 樣本 0.12–12 m 10 Hz `<ignition_frame_id>`、imu 100 Hz）；擴充 pytest 檢查上述參數值。筆記說明 URDF 與 SDF、inertial 的意義、gpu_lidar 依賴渲染。驗證：`colcon test --packages-select amr_description` 通過

## 5. bridge、watchdog 與啟動整合（sim-runtime、simulated-amr）

- [ ] 5.1 （筆記 10）建立 `ros_ws/src/amr_bringup`（ament_python）；先寫 watchdog 邏輯類別的 pytest（收到指令即轉發、0.5 s 無指令輸出一次零速度、之後不重複、恢復指令後再次轉發；時間由測試注入）。驗證：測試失敗（尚未實作）
- [ ] 5.2 （筆記 10）實作 watchdog 邏輯類別與 `cmd_vel_watchdog` rclpy 節點（訂閱 `cmd_vel`、發布 `cmd_vel_gz`，皆為相對名稱以吃 namespace）。驗證：5.1 測試通過
- [ ] 5.3 （筆記 10）撰寫 ros_gz_bridge 設定產生方式（D6 列出的 topic 與方向，以 robot_id 參數化）；筆記說明 gz transport 與 ROS 2 是兩套獨立的通訊系統、bridge 的方向與型別對應。驗證：pytest 檢查以 `amr1` 產生的設定含全部 topic 且方向正確
- [ ] 5.4 （筆記 11）撰寫 `launch/sim.launch.py`（參數 `config`、`world`、`robot_id`、`headless`，依「套件預設 ← `sim.yaml` ← 命令列」合併，合併邏輯抽成純函式並寫 pytest：無設定檔用預設、設定檔覆寫預設、命令列覆寫設定檔；`AMR_WORLDS_DIR`；spawn 位姿解析含 `_edited` 退回規則；`spawn_robot(robot_id, pose)` 函式；robot_state_publisher 的 namespace、`frame_prefix`、`use_sim_time`）；spawn 解析邏輯抽成可測函式並寫 pytest。驗證：pytest 通過；`exec.sh` 進入後 `ros2 launch amr_bringup sim.launch.py` 後 Gazebo 顯示倉庫與位於 (1,1) 朝 +x 的車，bridge 無錯誤訊息
- [ ] 5.5 （筆記 11）新增 `docker/amr_sim/config/sim.yaml`（`world: warehouse_small`、`robot_id: amr1`、`headless: false`）。驗證：`up_gpu.sh` → `exec.sh` → `ros2 launch amr_bringup sim.launch.py config:=/config/sim.yaml` 顯示倉庫與車；launch 按 Ctrl+C 後主機 `nvidia-smi` 無殘留 gazebo 程序、容器仍在執行且可再次 launch；在 GUI 另存 `warehouse_small_edited.sdf` 後把 `sim.yaml` 的 `world` 改為 `warehouse_small_edited` 重新 launch 可載入（之後改回）；`ros.env` 改為 `ROS_DOMAIN_ID=42` 後 `up_gpu.sh` 重建容器，exec 進入的 shell 與另一個 `docker compose run` 容器皆為 42 且收得到 `/amr1/scan`（之後改回 0）
- [ ] 5.6 （筆記 11）驗證車輛介面：另開一個 `exec.sh` shell 執行 `teleop_twist_keyboard --ros-args -r cmd_vel:=/amr1/cmd_vel` 可開車、關閉 teleop 後車在 1 秒內停下；`ros2 topic list` 只有帶 namespace 的車輛 topic；`ros2 topic hz` 記錄 scan／odom／imu 頻率；`ros2 run tf2_ros tf2_echo amr1/odom amr1/laser_link` 有輸出；RViz（Fixed Frame `amr1/odom`）看得到 `/amr1/scan` 掃到牆與貨架

## 6. 自動化冒煙測試

- [ ] 6.1 （筆記 12）撰寫 `amr_bringup/test/test_sim_smoke.py`（launch_testing，`headless:=true`）：30 s 內收到 `/amr1/scan` 與 `/amr1/odom`、無未帶 namespace 的車輛 topic、`amr1/odom → amr1/laser_link` TF 可查、送 `cmd_vel` 後 odom 位移 > 0、送 `linear.x = 5.0` 時 odom 線速度 ≤ 1.0、停送 1 s 內速度為 0、暫停模擬後 `/clock` 停止、正前方光達讀值與場景幾何相符（±0.1 m）。筆記說明 headless 與 `--headless-rendering`（EGL）。驗證：`exec.sh` 進入後 `colcon test --packages-select amr_bringup && colcon test-result --verbose` 全部通過；若 EGL 不可用，依 design Risks 改用替代方式並記錄於踩坑紀錄

## 7. 文件與整體驗收

- [ ] 7.1 （筆記 13）撰寫根目錄 `README.md`：主機前置（連結學習筆記 01–03）、`docker/amr_sim/config/`（`ros.env`、`sim.yaml`）說明與 UID 非 1000 時的 `export USER_UID=$(id -u) USER_GID=$(id -g)`、建置與啟動、切換 world、軟體渲染疊加檔、teleop、RViz／另一容器觀察 topic、執行所有測試。驗證：依 README 從 `docker/amr_sim/build.sh` 開始操作可完成啟動
- [ ] 7.2 （筆記 13）使用者依 design D7 手動驗收清單逐項確認（NVIDIA renderer、`nvidia-smi` 看得到 gazebo、軟體渲染可用、GUI 旋轉／平移／縮放、teleop 開車與放開停車、RViz 看到 scan、另一容器 echo `/amr1/scan` 有資料、改 YAML 重新產生重啟後看到變化且未重建映像、edited world 可載入），結果記錄於筆記 13；更新 `docs/開發摘要.md` 子專案 1 狀態

## Workflow follow-up

- 全部完成後執行 `openspec archive add-sim-environment`，把 specs 併入 `openspec/specs/`
- 子專案 2（建圖／定位／導航）另開 brainstorming 與新 change
