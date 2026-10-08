# 26 server 容器與映像

檔案：[`Dockerfile`](../../docker/amr_sim/Dockerfile)、[`compose.yaml`](../../docker/amr_sim/compose.yaml)、[`up.sh`](../../docker/amr_sim/up.sh)、[`exec.sh`](../../docker/amr_sim/exec.sh)

OpenSpec change `add-web-dispatch`（子專案 3，2026-10-08），task 1.1–1.2。

## 為什麼要做

子專案 3 要做網頁派車：後端（FastAPI + rclpy）和前端（React + Vite）。後端是「管全部車的中控」，不屬於任何一台車——真實部署時每台車上跑 robot 容器，另一台中控電腦跑後端。所以新增第三個容器 `server`，分層變成：

| 容器 | 角色 | 真實部署 |
|---|---|---|
| sim | 世界（Gazebo） | 不存在（真實世界取代） |
| robot | 車子系統 | 每台車一份 |
| server | 中控：後端＋網頁 | 中控電腦一份 |

## 做了什麼

### 1. 映像加 Python 套件（pip）

```dockerfile
RUN pip install --no-cache-dir \
        fastapi==0.142.4 \
        uvicorn==0.54.0 \
        websockets==16.1.1 \
        httpx==0.28.1
```

- **為什麼不用 apt**：Ubuntu 22.04 的 `python3-fastapi` 是 0.78（2022 年，Pydantic v1），寫法和現在的文件差很多。
- **映像原本沒有 pip**：`osrf/ros:humble-desktop` 不含 `python3-pip`，在 apt 那層補上。
- **釘死版本（`==`）**：同一份 Dockerfile 隔半年重建，結果要一樣；不釘的話某天上游改版就可能壞掉、而且找不到原因。
- **不用 `uvicorn[standard]`**：它會順便裝 PyYAML 等套件，和 apt 裝的 `python3-yaml` 衝突——apt 裝的套件 pip 無法移除（`Cannot uninstall 'PyYAML', distutils installed project`）。後端只需要 WebSocket，單獨裝 `websockets` 就好。
- **websockets 16.x**：17 起需要 Python 3.11，映像是 3.10（Humble 綁 Ubuntu 22.04）。查法：PyPI 每個版本的 `requires_python`。
- **httpx**：FastAPI 的測試工具 `TestClient` 需要。
- pip 裝在系統 Python（`/usr/local/lib/python3.10/dist-packages`），會比 apt 的 `/usr/lib/python3/dist-packages` 優先。這次順帶裝了較新的 `typing-extensions`、`click`、`idna` 等；驗證 ROS 工具（`ros2`、`colcon`、`rclpy`、`launch_ros`、`tf2_ros`）照常可用。

### 2. 映像加 Node.js 24 LTS（官方 tarball）

```dockerfile
ARG NODE_VERSION=24.21.0
ARG NODE_SHA256=fd8e59d5...
RUN curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    && echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner \
    && rm /tmp/node.tar.xz
```

- **為什麼不用 apt**：Ubuntu 22.04 的 Node 是 12，Vite 需要 18 以上。
- **為什麼不用 NodeSource**：要加第三方 apt 套件庫和金鑰；官方 tarball 只是一個壓縮檔，解開就能用。
- **SHA256 寫死在 Dockerfile**：雜湊取自 nodejs.org 的 `SHASUMS256.txt`。下載的檔案只要被動過一個位元，`sha256sum -c` 就失敗、建置中止——防止下載到被竄改或損壞的檔案。
- `--strip-components=1`：tarball 最外層是 `node-v24.21.0-linux-x64/`，去掉這層，`bin/node` 直接落在 `/usr/local/bin/node`（已在 PATH）。
- `--no-same-owner`：tarball 裡記錄的檔案擁有者是打包者的 UID，解到系統目錄應該屬於 root。
- 為什麼選 24：2026-10 時 Node 24 是 Active LTS（22 進入維護期、20 已結束）。
- Node 也會出現在 sim、robot 容器（同一個映像），多約 100 MB；換來「只有一個映像」的簡單。

### 3. compose 新增 server

```yaml
  server:
    image: amr-sim:humble
    command: ["sleep", "infinity"]
    network_mode: host
    ipc: host
    init: true
    env_file: ./config/ros.env
    volumes:
      - ../../ros_ws:/ros_ws
      - ../../web:/web
```

和 robot 對照，**拿掉的**：GPU 裝置、`DISPLAY` 與 NVIDIA 環境變數、X11 socket、`/data`。後端不畫圖；地圖從車子系統的 `/amr1/map` topic 拿，不讀檔案（真實部署時地圖在車上，不在中控）。

**保留的**：`network_mode: host`（瀏覽器連 `localhost:8000`，也讓 DDS 互相發現）、`ipc: host`（Fast DDS 同一台主機走 shared memory，IPC 不同會「看得到 topic、收不到資料」）、`env_file`（同一個 `ROS_DOMAIN_ID`）。

軟體渲染疊加檔不用改：它只覆寫 GPU 設定，server 本來就沒有。

### 4. up.sh、exec.sh

兩個 `case` 各多一個 `server`。`all` 是「不指定服務＝全部」，自動包含新的 server，不用改。

## 怎麼驗證（2026-10-08 實測）

- `docker compose config -q`、加上軟體渲染疊加檔的 `config -q` 都通過。
- `up.sh gpu foo`、`exec.sh` 不帶參數：顯示含 `server` 的用法、結束碼 2。
- 先以臨時標籤 `amr-sim:webtest` 建置（不影響執行中的容器）：`node --version` → `v24.21.0`、`npm` 11.19；`import fastapi, uvicorn, websockets, httpx` 成功（0.142.4／0.54.0／16.1.1）；PyYAML 仍是 apt 的 5.4.1；`ros2 pkg list`、`colcon list`、`import rclpy.action, tf2_ros, nav2_msgs.action` 正常。
- 使用者重建並啟動三個容器（task 1.2）：見下方「使用者操作」。

## 面試追問

**Q：Dockerfile 裡裝套件為什麼要釘版本？**
A：映像要可重現：同一份 Dockerfile 不同時間建置結果要一樣。不釘版本時上游一改版，建置可能失敗或行為改變，而且很難追。升級時改版本號、重建、跑測試，是一次明確的變更。

**Q：從網路下載二進位檔到映像，怎麼確保安全？**
A：用官方來源，並比對官方公布的 SHA256；把雜湊寫死在 Dockerfile，檔案不符就讓建置失敗。更嚴格的做法還會驗證 GPG 簽章。

**Q：pip 和 apt 裝的 Python 套件混用有什麼風險？**
A：pip 無法移除 apt 裝的套件（會報 distutils installed project），而且 pip 裝到 `/usr/local` 會蓋過 apt 的版本，可能讓依賴 apt 版本的系統工具出問題。做法：只裝需要的套件、避開會拉進衝突套件的 extras、裝完驗證系統工具；更乾淨的是用 venv（但 ROS 的 rclpy 在系統 Python，venv 要開 `--system-site-packages`）。

**Q：為什麼後端放在獨立容器，而不是車上？**
A：後端管理多台車（派車、之後的任務佇列），是車隊層級的服務。放在車上的話每台車各一份、狀態分散；車子離線時也連帶失去管理介面。

## 踩坑紀錄

- **映像沒有 pip**：`osrf/ros:humble-desktop` 不含 `python3-pip`，要在 apt 清單補上。
- **websockets 最新版不支援 Python 3.10**：PyPI 的 17.x 要求 `>=3.11`；選版本時要看 `requires_python`，不能只看最新。
