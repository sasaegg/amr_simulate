# 04 Dockerfile

檔案：[`docker/amr_sim/Dockerfile`](../../docker/amr_sim/Dockerfile)

## 為什麼要做

需要一個固定、可重現的環境：ROS 2 Humble + Gazebo Fortress + 之後要用的 Nav2／slam_toolbox。把環境寫成 Dockerfile，任何裝了 Docker（加 NVIDIA toolkit）的 Ubuntu 都能建出一模一樣的環境，不污染主機。GPU 驅動不在映像內（筆記 03）。

## 做了什麼

### 目錄與 build context

```
docker/
  amr_sim/          ← build context = 這個映像的全部材料（Dockerfile、之後的 entrypoint、config）
    Dockerfile
```

```bash
docker build -t amr-sim:humble docker/amr_sim
```

- 最後的路徑是 **build context**：CLI 把這個資料夾整包送給 dockerd，`COPY` 只能取用其中的檔案（daemon 不一定在本機，看不到你的檔案系統）。
- 開發映像不放原始碼（`ros_ws` 執行時以 volume 掛載），所以 context 只需要這個小資料夾，不用 `.dockerignore`。
- 檔名用預設的 `Dockerfile`，不需要 `-f`。
- `-t 名稱:標籤`：替映像命名。

### 逐段

**① 基底**：`FROM osrf/ros:humble-desktop`——官方 `ros:humble` 只有 core/base；osrf 的 desktop 版含 rviz2、rqt，且已設好 ROS apt 來源。不用 `nvidia/cuda`：Gazebo 只需 OpenGL，驅動函式庫由 toolkit 注入。

**② `ARG DEBIAN_FRONTEND=noninteractive`**：避免 `tzdata` 之類套件在建置時跳出互動問題卡住。用 `ARG` 而非 `ENV`：ARG 只在建置期有效，ENV 會永久留在映像裡，影響之後在容器內手動 apt。

**③ 安裝套件（單一 RUN）**
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        ... \
    && rm -rf /var/lib/apt/lists/*
```
- 映像由**層**疊成，每個 `RUN`／`COPY` 一層，每層記錄相對上一層的檔案變化，**寫入後不可改**。
- `update` 與 `install` 同層：分開的話 `update` 層會被快取，之後改 install 清單時用到過期索引 → 404。
- `rm -rf /var/lib/apt/lists/*` 同層：在下一層才刪，檔案仍留在上一層，映像不會變小（只多一個 whiteout 標記）。
- `--no-install-recommends`：只裝必要相依。
- 套件依字母排序，方便 diff。

| 套件 | 用途 |
|---|---|
| `ros-humble-ros-gz` | Gazebo Fortress + ROS↔Gazebo bridge |
| `ros-humble-navigation2`、`nav2-bringup`、`slam-toolbox` | 子專案 2 用，先裝免重建（約 +1 GB） |
| `ros-humble-teleop-twist-keyboard` | 鍵盤開車 |
| `ros-humble-xacro` | 展開車輛模型巨集 |
| `python3-pytest`、`python3-yaml` | 測試、場景產生器 |
| `mesa-utils`、`x11-apps` | `glxinfo`、`xeyes`，驗證 GPU 與顯示 |
| `sudo` | 容器內臨時除錯安裝 |
| `liburdfdom-tools` | `check_urdf`——**實測後發現多餘**，見踩坑紀錄 |

**④ 同 UID 使用者**
```dockerfile
ARG USER_UID=1000
RUN groupadd --gid ${USER_GID} ros && useradd --uid ${USER_UID} ... ros \
    && echo "ros ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ros
USER ros
WORKDIR /ros_ws
```
- 容器預設 root；掛載的 `ros_ws` 裡 `colcon build` 產生的檔案會變成 root 擁有，主機上刪不掉。
- Linux 權限只看**數字** UID：容器內叫 `ros`、主機叫 `myuser` 都沒關係，UID 都是 1000 就是同一人。
- 附帶好處：X server 允許清單 `SI:localuser:myuser` 也是比對 UID。
- `NOPASSWD` sudo 只適合本機開發映像。
- apt 那段必須在 `USER` 之前（一般使用者不能 apt install）。

**⑤ 層的順序**：少變動的在前（基底 → 系統套件 → 使用者 →（之後）COPY entrypoint）。某層改變，其後所有層都要重建。

## 怎麼驗證

| 指令 | 實際結果（2026-10-07） |
|---|---|
| `docker run --rm amr-sim:humble ign gazebo --version` | `Gazebo Sim, version 6.18.0` |
| `docker run --rm amr-sim:humble id` | `uid=1000(ros) gid=1000(ros) groups=1000(ros)` |
| `docker image ls` | `amr-sim:humble` 5.61 GB（基底 `osrf/ros:humble-desktop` 4.85 GB） |
| 容器內 `pwd`、`which xacro glxinfo xeyes check_urdf` | `/ros_ws`，工具都找得到 |

`docker history amr-sim:humble`（由新到舊）：

| 大小 | 層 |
|---|---|
| 8.19 kB | `WORKDIR /ros_ws` |
| 0 B | `USER ros` |
| 406 kB | 建立使用者的 RUN |
| 0 B | `ARG` ×3（只是 metadata，不產生檔案） |
| **602 MB** | apt 安裝的 RUN |
| 0 B | `ARG DEBIAN_FRONTEND` |
| … | 以下為基底映像的層 |

- 映像比基底大約 760 MB，幾乎全來自 apt 那一層。
- `ARG`、`USER` 等指令是 0 B：它們只改映像的設定（metadata），不改檔案。

**快取實驗**：不改任何東西再 build 一次，`RUN` 步驟全部 `CACHED`，0.5 秒完成。

## `ign gazebo --version` 與 Gazebo 命名

| 世代 | 代號 | 版本 | CLI | 外掛前綴 |
|---|---|---|---|---|
| Gazebo Classic | Gazebo 11 | 11.x | `gazebo` | `libgazebo_ros_*` |
| Ignition | Citadel、**Fortress** | 3.x、**6.x** | **`ign gazebo`** | **`ignition-gazebo-*`** |
| Gazebo（新） | Garden、Harmonic | 7.x、8.x | `gz sim` | `gz-sim-*` |

Humble 官方對應 Fortress。驗證版本是 6.x 才能確定之後外掛名稱用 `ignition-gazebo-*`。注意：Fortress 6.18 的 `--version` 印出的是 **`Gazebo Sim`**（後期版本已改了顯示名稱），但 CLI 與外掛名稱仍是 Ignition 時期的——**判斷依據是版本號 6.x，不是顯示名稱**。

## 面試追問

**Q：為什麼 `apt-get update` 和 `install` 要寫在同一個 RUN？**
A：層快取以指令文字判斷是否重用；分開時 update 層被快取，之後改 install 清單會用到過期索引。同層確保 install 一變就重新 update。

**Q：為什麼在下一層刪檔案不會讓映像變小？**
A：每層是不可變的檔案差異；下一層刪除只是加 whiteout 標記遮住，原檔案仍在上一層佔空間。要在產生檔案的同一層刪掉。（多階段建置是另一種解法：只把需要的產物 COPY 到乾淨的最終階段。）

**Q：ARG 和 ENV 差在哪？**
A：ARG 只在建置期，可用 `--build-arg` 覆寫；ENV 寫入映像，容器執行時也存在。建置期才需要的設定用 ARG。

**Q：容器內為什麼不用 root？**
A：掛載目錄的檔案擁有權問題（同 UID 解決），也是最小權限原則。這裡為了開發方便給了 NOPASSWD sudo，正式映像不會這樣。

**Q：映像為什麼這麼大？怎麼縮小？**
A：desktop 基底就有 4.85 GB（含 GUI 工具與大量 ROS 套件）。縮小方法：改用 `ros:humble-ros-base` 只裝需要的套件、`--no-install-recommends`、同層清快取、多階段建置。開發映像以方便為主，部署映像才需要極致精簡。

**Q：怎麼確認快取有生效？**
A：build 輸出中步驟顯示 `CACHED`；改動某一層會讓它和之後的層全部重建，所以把常變的東西放後面。

## 踩坑紀錄

- **`liburdfdom-tools` 是多餘的**：`which check_urdf` 找到的是 `/opt/ros/humble/bin/check_urdf`，`dpkg -S` 顯示它屬於 `ros-humble-urdfdom`（desktop 基底已內含）；`liburdfdom-tools` 只是另外在 `/usr/bin/` 放了一份。PATH 中 `/opt/ros/humble/bin` 在前，所以實際用的是 ROS 那份。→ 在 task 2.2 重建時移除。教訓：加套件前先確認基底映像是否已提供。
- **預期輸出寫錯**：原本以為會印 `Ignition Gazebo`，實際是 `Gazebo Sim, version 6.18.0`。以版本號判斷世代，不要以顯示名稱判斷。
