# 06 compose：容器內的 GPU 與 X11

檔案：[`docker/amr_sim/compose.yaml`](../../docker/amr_sim/compose.yaml)、[`build.sh`](../../docker/amr_sim/build.sh)、[`up_gpu.sh`](../../docker/amr_sim/up_gpu.sh)、[`up_cpu.sh`](../../docker/amr_sim/up_cpu.sh)、[`exec.sh`](../../docker/amr_sim/exec.sh)、[`config/ros.env`](../../docker/amr_sim/config/ros.env)

## 為什麼要做

同一個容器需要一長串 `docker run` 參數（GPU、X11、網路、IPC、掛載、環境變數…）。compose.yaml 把這些寫成檔案、進版控，每次啟動都一樣。這一步也第一次驗證「容器裡用 NVIDIA 繪圖、視窗畫到主機桌面」。

## compose 基本觀念

- **compose.yaml 是宣告式的說明書**：描述「要有哪些容器、怎麼設定」，`docker compose up` 負責讓實際狀態符合它（映像不存在就 build、建立並啟動容器；設定改了會自動重建容器）。
- **image / service / container**：image 是軟體快照；service 是「用哪個 image、怎麼執行」的定義；container 是依 service 跑起來的實體（類比 class 與 instance）。一個 service 預設一個容器；`run` 會另開一次性容器；多個 service 可共用同一個 image。
- **`docker compose build`**：找到 compose.yaml（從目前目錄往**上層**找），對有 `build:` 的 service 建置，等同 `docker build -t <image> --build-arg ... <context>`，與手動 docker build 共用同一份 BuildKit 快取。
- **`up` 不會自動重建映像**：映像已存在就直接用。改了 Dockerfile 要 `build.sh` 或 `up_gpu.sh --build`。

## 做了什麼

### 目錄

```
docker/amr_sim/          ← 一個映像一個資料夾：材料、設定、compose、腳本都在這
  Dockerfile  entrypoint.sh
  compose.yaml
  build.sh  up_gpu.sh  up_cpu.sh  exec.sh
  config/ros.env
```

compose 檔內的**相對路徑以 compose.yaml 所在資料夾為基準**：`context: .`、`./config`、`../../ros_ws`。

### compose.yaml 逐項

```yaml
name: amr_sim
```
專案名稱：容器名前綴（`amr_sim-sim-1`）、`ps`／`down` 依標籤 `com.docker.compose.project` 判斷歸屬。不寫時用資料夾名稱（現在剛好也是 `amr_sim`）；明確寫出是為了資料夾改名或搬移時，專案名稱不變、舊容器不會變孤兒。優先序：`-p` > `COMPOSE_PROJECT_NAME` > `name:` > 資料夾名。

```yaml
command: ["sleep", "infinity"]
```
**長駐容器**：容器的生命週期 = 主程式的生命週期。主程式是不會結束的 `sleep`，容器就一直開著；模擬由使用者 exec 進去後自己 launch，可反覆啟動／停止而不重建容器。
（若維持 Dockerfile 的 `CMD ["bash"]`：`up` 不配置終端機，bash 讀到 EOF 立即結束、容器 `exited with code 0`——實際遇過。）

```yaml
build:
  context: .
  args: { USER_UID: ${USER_UID:-1000}, USER_GID: ${USER_GID:-1000} }
```
`${VAR:-預設}`：shell 環境變數有值就用，否則用預設。建置參數不放 `.env`、也不能放 config（建置時 config 還沒掛載）。

| 設定 | 作用 |
|---|---|
| `network_mode: host` | DDS 以 multicast 探索節點；共用主機網路，主機與其他容器直接互相看見 |
| `ipc: host` | Fast DDS 對同主機節點走 shared memory；IPC namespace 不同會「看得到 topic、收不到資料」（2.5 實驗）。也讓 X11 MIT-SHM 可用 |
| `init: true` | tini（`docker-init`）當 PID 1：轉發訊號、回收殭屍程序（筆記 05） |
| `env_file: ./config/ros.env` | `ROS_DOMAIN_ID` 等設成**容器層級**環境變數；`docker exec` 不經 entrypoint，只有這樣 exec 進去也拿得到 |
| `DISPLAY: ${DISPLAY:-:0}` | X11：要畫到哪個 X server |
| `NVIDIA_DRIVER_CAPABILITIES: all` | legacy 模式需含 graphics 才注入 OpenGL；CDI 模式不受影響（筆記 03 實測），設了兩邊都正確 |
| `__NV_PRIME_RENDER_OFFLOAD: "1"`、`__GLX_VENDOR_LIBRARY_NAME: nvidia` | 雙顯卡：讓 GLVND 把 OpenGL 交給 NVIDIA（筆記 02） |
| `/tmp/.X11-unix:/tmp/.X11-unix:ro` | X11 的 unix socket，容器透過它連主機 X server |
| `../../ros_ws:/ros_ws` | 原始碼掛載，改了不用重建映像 |
| `./config:/config` | 執行設定，可寫 |

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```
等同 `docker run --gpus all`。
- `deploy` 原是 Docker Swarm 的部署設定（所以巢狀這麼深），單機 compose 採用其中的 `resources`。
- `limits` 是上限，`reservations` 是「必須拿到」；devices 只能放在 reservations——沒有 GPU 時容器**啟動失敗**，而不是無聲退回軟體渲染。
- `driver: nvidia` 交給 NVIDIA Container Toolkit（本機走 CDI）；`count: all`（config 輸出顯示為 `-1`）或 `device_ids: ["0"]`（二擇一）；`capabilities: [gpu]` 必填。
- 其他等價寫法：`--device nvidia.com/gpu=all`（CDI）、compose `devices: ["nvidia.com/gpu=all"]`、舊格式 `runtime: nvidia`（不建議）。

### 為什麼 sim 完整展開、不用 anchor

`x-` 開頭的頂層鍵 compose 會忽略（擴充欄位）；`&name`／`*name`／`<<:` 是 YAML 的錨點、別名、合併。原本用它們讓之後的 nav／backend 共用設定，但改成完整展開：一目了然，也避開 `<<:` **只做淺層合併**的陷阱（service 自己寫 `environment:` 會整個取代共用的 environment，DISPLAY 等全部消失）。之後加 service 時再評估。

### config/ros.env

```
ROS_DOMAIN_ID=0
```
DDS 依 domain ID 算出 UDP port（約 `7400 + 250 × id`），只有同 domain 的節點互相發現。所有 ROS 容器必須一致；同網段有別人跑 ROS 2 時改成少見的數字（建議 0–101）。

### 便利腳本

共同結構：
```bash
#!/bin/bash
set -euo pipefail          # -e 出錯即停；-u 未定義變數報錯；pipefail 管線任一段失敗都算失敗
cd "$(dirname "$0")"       # 切到腳本所在資料夾（compose.yaml 就在這），任何目錄執行都可以
exec docker compose ...    # exec：compose 取代腳本程序，Ctrl+C 直接送到 compose
```

| 腳本 | 內容 | 重點 |
|---|---|---|
| `build.sh` | `export USER_UID="$(id -u)" USER_GID="$(id -g)"` → `docker compose build "$@"` | bash 的 `$UID` 是**未 export 的 shell 變數**，compose 讀不到，所以在這裡 export |
| `up_gpu.sh` | `docker compose up -d sim "$@"` | `-d` 背景執行，立刻返回；GPU 繪圖 |
| `up_cpu.sh` | `docker compose -f compose.yaml -f compose.software.yaml up -d sim "$@"` | 同上，軟體渲染（task 2.4） |
| `exec.sh` | `docker compose exec sim bash` | 固定開互動式 bash → 一定讀 `~/.bashrc` → 一定有 ROS 環境；可開多個終端機各自進入 |

刻意不做：`run.sh`（長駐流程下改為 exec 操作；跨容器測試時手動 `docker compose run --rm sim bash`）、`down.sh`（手動 `docker compose down` 或 `docker stop amr_sim-sim-1`）、`sim.sh`（launch 在容器內手動執行）。

日常流程：
```
docker/amr_sim/up_gpu.sh       # 啟動長駐容器
docker/amr_sim/exec.sh     # 進入（可開多個）
  ros2 launch ...          # 啟動模擬；Ctrl+C 停止，容器仍在
docker compose down        # 在 docker/amr_sim/ 收工
```

## 怎麼驗證（2026-10-07 實測）

| 項目 | 結果 |
|---|---|
| `xhost` | 含 `SI:localuser:myuser`；容器以 UID 1000 執行，**不需要 `xhost +`**（不做 `allow_x.sh`） |
| 從 `/tmp` 執行 `build.sh` | `Image amr-sim:humble Built`，各層 CACHED（UID 1000 與預設相同，快取不失效） |
| `up_gpu.sh` | 立即返回，`amr_sim-sim-1` running |
| 容器內 `ps` | PID 1 `docker-init`、`sleep` 為其子程序 |
| `echo $ROS_DOMAIN_ID`（exec 進入） | `0` |
| `glxinfo -B` | `OpenGL renderer string: NVIDIA GeForce RTX 3060 Laptop GPU/PCIe/SSE2`、core profile 4.6、驅動 580.178.04 |
| `xeyes` | 視窗出現在主機桌面 |
| `ign gazebo shapes.sdf` | 開啟、可旋轉；主機 `nvidia-smi` 的 Processes 看得到 gazebo 程序 |
| 在 `/ros_ws`、`/config` 建立檔案 | 主機上擁有者 UID 1000 |
| `docker compose down` | 0.13 秒 |

## 補充：軟體渲染疊加檔（task 2.4）

檔案：[`docker/amr_sim/compose.software.yaml`](../../docker/amr_sim/compose.software.yaml)

```yaml
services:
  sim:
    deploy: !reset {}                       # 清空整個 GPU 要求
    environment:
      __GLX_VENDOR_LIBRARY_NAME: mesa       # OpenGL 交給 Mesa
      __NV_PRIME_RENDER_OFFLOAD: "0"
      LIBGL_ALWAYS_SOFTWARE: "1"            # Mesa 用 CPU 繪圖（llvmpipe）
```

```bash
cd docker/amr_sim
./up_cpu.sh                                                          # 切到軟體渲染（= -f compose.yaml -f compose.software.yaml up -d sim）
./up_gpu.sh                                                              # 切回 GPU（設定不同 → 自動重建容器）
```

- **`-f a -f b` 合併規則**：後者覆寫前者；map（如 `environment`）逐鍵合併，沒寫到的鍵保留。一般覆寫只能改值不能刪除，要刪整個鍵用 `!reset`（compose v2.24+，本機 v5.6）。
- **為什麼要同時把 vendor 改成 mesa**：`LIBGL_ALWAYS_SOFTWARE` 只有 Mesa 看得懂。若 GLVND 仍被要求用 nvidia，而容器內已沒有 NVIDIA 函式庫，OpenGL 直接失敗。
- **不需要 `MESA_GL_VERSION_OVERRIDE`**：llvmpipe 已提供 OpenGL 4.5 core，高於 ogre2 需要的 3.3。舊設定是 WSL d3d12 只回報 4.2 時的權宜之計。

實測（2026-10-07）：

| 項目 | GPU 模式 | 軟體模式 |
|---|---|---|
| renderer | NVIDIA GeForce RTX 3060 Laptop GPU | llvmpipe (LLVM 15.0.7, 256 bits) |
| OpenGL core | 4.6 | 4.5（Mesa 23.2.1） |
| 容器內 nvidia 函式庫／`/dev/nvidia*` | 59 個／5 個 | 0／0 |
| `shapes.sdf` 操作流暢度 | 流暢 | 差別不大 |
| RTF | — | 約 0.9 |
| 主機 CPU | — | 約 55%（20 核） |

`shapes.sdf` 只有幾個簡單幾何體，llvmpipe 用多核心 CPU 就應付得來；差距會在倉庫場景加上 gpu_lidar（每秒 10 次深度渲染）時才明顯，屆時可再比較。軟體模式的代價是吃 CPU、RTF 掉到 1 以下（模擬比真實時間慢）。

## 補充：容器間 DDS 互通與 `ipc: host` 實驗（task 2.5）

ROS 2 Humble 預設 RMW 是 `rmw_fastrtps_cpp`（Fast DDS）。

| 實驗 | talker | listener | `ros2 topic list` | listener 收到資料 |
|---|---|---|---|---|
| A | 長駐容器（`ipc: host`） | `docker compose run`（`ipc: host`） | 有 `/chatter` | ✅ 每秒一則 |
| B | 同上 | `docker run`，**沒有** `--ipc host`（其餘相同） | **有 `/chatter`** | ❌ 5 秒內 0 則 |
| C | 同上 | 同 B，但以 XML profile 強制只用 UDPv4 | 有 | ✅ |

`/dev/shm` 中 Fast DDS 的共享記憶體檔（`fastrtps_*`）：

| 位置 | 數量 |
|---|---|
| 長駐容器（`ipc: host`） | 17 |
| 主機 | 17（同一份） |
| 獨立 IPC 的容器 | 0（另一個 64 MB 的空 tmpfs） |

**原因**：

```
① 探索：UDP multicast → host 網路下成功 → topic list 看得到
② 資料：Fast DDS 判斷對方在同一台主機 → 自動改走 shared memory（比 UDP 快）
        → talker 寫進自己 IPC namespace 的 /dev/shm
        → listener 到自己的 /dev/shm 找 → 不同的 tmpfs → 找不到
        → 沒有任何錯誤訊息，資料靜靜消失
```

Docker 預設每個容器有獨立的 IPC namespace，`/dev/shm` 也各自獨立（預設只有 64 MB）。`ipc: host` 讓容器共用主機的 IPC namespace，所有容器與主機上的 ROS 程序看到同一個 `/dev/shm`；附帶好處是 `/dev/shm` 不再受 64 MB 限制（影像、點雲等大訊息會用到）。

**其他解法**：
- 強制 Fast DDS 只用 UDP（實驗 C 的 XML profile：`useBuiltinTransports=false` + 只宣告 UDPv4 transport，經 `FASTRTPS_DEFAULT_PROFILES_FILE` 載入）——犧牲同主機的傳輸效能。較新的 Fast DDS（2.12+，ROS 2 Jazzy）可直接用環境變數 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`；Humble 的 Fast DDS 2.6 不支援。
- 改用其他 RMW（如 Cyclone DDS），各家行為不同。

本專案選 `ipc: host`：設定最少、同主機效能最好，且開發機上的隔離需求低。

實驗 C 用的 profile：

```xml
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor><transport_id>udp</transport_id><type>UDPv4</type></transport_descriptor>
  </transport_descriptors>
  <participant profile_name="udp_only" is_default_profile="true">
    <rtps>
      <userTransports><transport_id>udp</transport_id></userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
```

## 面試追問

**Q：compose 和 docker run 差在哪？**
A：docker run 是命令式，參數靠人記；compose.yaml 是宣告式，把容器的完整設定寫成檔案進版控，`up` 讓實際狀態符合描述，設定改了會自動重建容器，也能一次管理多個容器。

**Q：容器怎麼把視窗畫到主機？**
A：X11 是 client-server 架構。把主機的 `/tmp/.X11-unix` socket 掛進容器、設 `DISPLAY`，容器內的程式就像本機程式一樣連到主機 X server。權限上，X server 的允許清單有 `SI:localuser:myuser`（依 UID 比對），容器以相同 UID 執行所以不需要 `xhost +`。

**Q：容器怎麼用到 NVIDIA GPU？雙顯卡呢？**
A：compose 以 `deploy.resources.reservations.devices` 要求 GPU，Container Toolkit（CDI）注入裝置節點與驅動函式庫；雙顯卡再加 `__NV_PRIME_RENDER_OFFLOAD=1`、`__GLX_VENDOR_LIBRARY_NAME=nvidia` 讓 OpenGL 走 NVIDIA。用 `glxinfo -B` 確認 renderer。

**Q：為什麼 `network_mode: host` 和 `ipc: host`？**
A：DDS 靠 multicast 探索，bridge 網路下不穩；Fast DDS 同主機走 shared memory，IPC namespace 不同會收不到資料。代價是容器間隔離變弱，對本機開發可接受。

**Q：長駐容器有什麼好處？主程式為什麼是 `sleep infinity`？**
A：啟動容器與啟動程式分離，可反覆 launch／停止、多個終端機各自 exec 進去（launch、teleop、RViz）。容器生命週期跟著主程式，所以主程式要是不會結束的程式；有 tini 當 PID 1，停止時 sleep 正常收到 SIGTERM，0.1 秒就停。

**Q：`docker exec` 進去的程序和容器主程式是什麼關係？**
A：exec 是從外部把新程序放進容器的 namespace，不是 PID 1 的子程序（容器內 `ps` 看到它的 PPID 是 0），也不經過 entrypoint，所以 ROS 環境要靠 `.bashrc` 或容器層級的環境變數（env_file）。

**Q：兩個 ROS 2 容器「看得到 topic 但收不到資料」，可能是什麼原因？怎麼查？**
A：最常見是 Fast DDS 的 shared memory 傳輸：探索走 UDP 所以看得到 topic，但同主機的資料走 `/dev/shm`，容器 IPC namespace 不同就讀不到，而且不報錯。我實測重現過：拿掉 `ipc: host` 後 listener 5 秒收 0 則，檢查兩邊 `/dev/shm`，一邊有 17 個 `fastrtps_*` 檔、一邊是空的；強制只用 UDP 就恢復。解法是 `ipc: host` 或限制 Fast DDS 只用 UDP。其他要檢查的還有 `ROS_DOMAIN_ID` 是否一致、QoS 是否相容（例如 reliable 對 best_effort）。

**Q：沒有 GPU 的機器怎麼跑？**
A：用疊加檔：`-f compose.yaml -f compose.software.yaml`，以 `!reset` 拿掉 GPU 要求，把 GLVND vendor 換成 mesa 並設 `LIBGL_ALWAYS_SOFTWARE=1`，改用 llvmpipe 以 CPU 繪圖。不改主檔、切換只差一個 `-f`。實測簡單場景 RTF 約 0.9、CPU 55%。

**Q：RTF 是什麼？**
A：Real Time Factor，模擬時間前進速度 ÷ 真實時間。1.0 表示和真實時間同步；小於 1 表示電腦算不動、模擬變慢。所有 ROS 節點用 `/clock`（模擬時間），所以 RTF 小於 1 時行為仍一致，只是整體變慢。

**Q：YAML anchor 合併有什麼陷阱？**
A：`<<:` 是淺層合併，service 自己寫了同名鍵會整個取代；例如自己寫 `environment` 就會丟掉共用的 DISPLAY 等變數。

## 踩坑紀錄

- **`up` 後容器立刻 `exited with code 0`**：CMD 是 `bash`，`up` 不配置 tty，bash 讀到 EOF 正常結束。改 `command: ["sleep", "infinity"]`。
- **腳本搬到 `docker/amr_sim/` 後路徑錯**：`cd "$(dirname "$0")"` 已經在 compose.yaml 所在資料夾，若還寫 `-f docker/amr_sim/compose.yaml` 會變成找 `docker/amr_sim/docker/amr_sim/compose.yaml`。腳本與 compose 同資料夾時直接 `docker compose ...`。
- **compose 搬家導致專案名稱改變**：從根目錄（專案名 `amr_slam_simulate`）搬到 `docker/amr_sim/`（`amr_sim`）後，舊名稱的容器不會被新名稱的 `down` 清掉，需手動清理。因此固定寫 `name:`。
