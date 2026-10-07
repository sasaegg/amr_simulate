# Proposal

## Why

整個 AMR 模擬與派車系統（建圖、定位、導航、前端、任務佇列）都需要一個可重現、可編輯的模擬環境作為地基。專案目前沒有任何程式碼，執行環境也已從 WSL2 改為 Ubuntu 22.04 實機（NVIDIA RTX 3060 Mobile），必須先在這台主機上以容器啟動 GPU 加速的 Gazebo、載入倉庫場景並讓一台帶光達的模擬車可以被操控，後續子專案才有東西可以接。

## What Changes

- 新增 Docker 化的 ROS 2 Humble + Gazebo Fortress 執行環境：容器透過 NVIDIA Container Toolkit 使用主機 GPU 繪圖（雙顯卡以 PRIME render offload 指定 NVIDIA），以標準 X11 把畫面送到主機桌面，可用滑鼠旋轉／縮放 3D 視角；另提供軟體渲染疊加設定作為無 GPU 時的退路。
- 新增「場景描述 YAML → Gazebo SDF world」產生器，讓倉庫地圖（外牆、內牆、貨架、障礙物、車輛出生點）以文字檔編輯與版本控制；產生後的 world 仍可在 Gazebo GUI 中微調並另存。
- 新增一台模擬差速 AMR：2D 光達、IMU、里程計，接受速度指令並具指令逾時停車；所有 topic 與 TF frame 置於 `amr1` namespace，為多車預留。
- 新增長駐的模擬容器與 launch 入口：容器啟動後進入其中以單一 launch 指令啟動模擬（world + 車輛 + ROS↔Gazebo 橋接）；另提供不開 GUI 的冒煙測試。
- 提供一份範例倉庫場景 `warehouse_small`。
- 新增主機準備步驟與逐步學習筆記（`docs/學習筆記/`），記錄每一步的原因、驗證方式與面試追問。

## Capabilities

### New Capabilities
- `world-generation`: 以宣告式 YAML 描述倉庫場景並產生 Gazebo 可載入的 world，包含輸入驗證與錯誤回報。
- `simulated-amr`: 模擬 AMR 的對外介面——以 namespace 隔離的速度指令、里程計、光達、IMU、TF、模擬時間與出生位置。
- `sim-runtime`: 以容器啟動整個模擬的使用方式與行為，包含 GPU／軟體渲染、X11 顯示、容器間 ROS 互通與原始碼掛載開發。

### Modified Capabilities
（無）

## Impact

- 新增檔案：根目錄 `.gitignore`、`.gitattributes`、`README.md`；`docker/amr_sim/`（Dockerfile、entrypoint、`compose.yaml`、`compose.software.yaml`、便利腳本 `build.sh`、`up_gpu.sh`、`up_cpu.sh`、`exec.sh`、`config/ros.env`、`config/sim.yaml`）；`ros_ws/src/amr_worlds`、`amr_description`、`amr_bringup`；`docs/學習筆記/`。
- 移除：`docker/.env`（內容拆至 `docker/amr_sim/config/ros.env` 與 compose 預設值）；舊版以 WSL 為前提的 `add-sim-environment` change 已刪除並由本 change 取代。
- 新增相依：`osrf/ros:humble-desktop` 基底映像、`ros-humble-ros-gz`、`teleop_twist_keyboard`、`xacro`、Python `pyyaml`、`pytest`；Nav2 與 slam_toolbox 先裝入映像供子專案 2 使用。
- 主機需求：Ubuntu 22.04、原生 Docker Engine（使用者在 `docker` 群組）、NVIDIA 專有驅動、NVIDIA Container Toolkit；主機設定屬使用者系統設定，以學習筆記提供步驟，由使用者執行。
- 不影響任何既有程式（專案為全新）。
