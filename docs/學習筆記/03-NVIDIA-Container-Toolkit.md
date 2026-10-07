# 03 NVIDIA Container Toolkit

## 為什麼要做

主機已有驅動（筆記 02），但容器仍然用不了 GPU：

```
$ docker run --rm --gpus all ubuntu nvidia-smi
docker: Error response from daemon: failed to discover GPU vendor from CDI: no known GPU vendor found
```

容器是被 namespace／cgroup 隔離的程序，預設：
- `/dev` 裡沒有 `/dev/nvidia0`、`/dev/nvidiactl` 等裝置節點，cgroup device 規則也不允許存取；
- 檔案系統裡沒有 `libcuda.so`、`libGLX_nvidia.so` 等使用者層函式庫。

要用 GPU，必須在**容器啟動時**放進「裝置節點」與「**和主機 kernel module 版本完全一致**的函式庫」。Toolkit 就是做這件事的，所以映像裡不需要（也不應該）裝驅動。

## 做了什麼

```bash
# 1. NVIDIA apt 來源（金鑰只綁這個來源）
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. 安裝
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. 註冊 nvidia runtime 並重啟 dockerd（daemon.json 只在啟動時讀取）
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

- `gpg --dearmor`：把 ASCII 格式公鑰轉成 apt 使用的二進位格式。
- `signed-by=`：這把金鑰**只能**驗證這個來源。舊的 `apt-key add` 讓金鑰對所有來源有效（任何一把外部金鑰都能冒充 Ubuntu 官方套件），已被廢棄。
- `nvidia-ctk runtime configure` 產生的 `/etc/docker/daemon.json`：

```json
{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    }
}
```

## 兩種注入機制

**① runtime hook（舊）**
```
dockerd → nvidia-container-runtime（包住 runc）→ 加入 OCI prestart hook
        → runc 建容器 → hook 呼叫 libnvidia-container 掛入 /dev/nvidia* 與函式庫 → 程式啟動
```
命令式、NVIDIA 專屬，靠 OCI 的 hook 機制在「容器建立後、程式執行前」插手。注入哪些函式庫由環境變數 `NVIDIA_DRIVER_CAPABILITIES` 決定（預設 `compute,utility`）。

**② CDI，Container Device Interface（新）**
- CNCF 的跨 runtime 標準；Docker 25+、Podman、containerd、Kubernetes 都原生支援。
- 廠商產生**宣告式** spec（YAML），列出要建立的裝置節點、要掛載的檔案、要執行的 hook；runtime 讀 spec 就知道怎麼注入，不需包一層特殊 runtime。
- 本機的 spec：`/var/run/cdi/nvidia.yaml`（`cdiVersion: 0.7.0`、`kind: nvidia.com/gpu`），由 systemd 的 `nvidia-cdi-refresh.path`／`.service` 自動產生——它監看 `/lib/modules/<kernel>/modules.dep` 與 `nvidia-ctk`，kernel 或驅動模組變動時重新產生，所以驅動升級後 spec 自動跟上。

## 怎麼驗證

```bash
nvidia-ctk --version            # NVIDIA Container Toolkit CLI version 1.20.1
cat /etc/docker/daemon.json     # 含 runtimes.nvidia
nvidia-ctk cdi list             # nvidia.com/gpu=0、nvidia.com/gpu=GPU-<UUID>、nvidia.com/gpu=all
docker run --rm --gpus all ubuntu nvidia-smi --query-gpu=name,driver_version --format=csv
#   NVIDIA GeForce RTX 3060 Laptop GPU, 580.178.04
```

純 `ubuntu` 映像裡沒有任何 NVIDIA 東西，加了 `--gpus all` 卻能跑 `nvidia-smi`——`nvidia-smi` 本身也是被注入的。

### 實驗：同一個映像，加不加 `--gpus`

| | `/dev` 中的 nvidia 裝置 | `/usr/lib/x86_64-linux-gnu` 中的 nvidia 檔案 |
|---|---|---|
| `docker run --rm ubuntu` | 無 | 0 個 |
| `docker run --rm --gpus all ubuntu` | `nvidia0`、`nvidiactl`、`nvidia-modeset`、`nvidia-uvm`、`nvidia-uvm-tools` | 含 `libGLX_nvidia`、`libEGL_nvidia`、`libcuda`、`libnvidia-ml`… 全部版本號 580.178.04 |

注入的函式庫版本號與主機驅動完全相同——這正是「版本必須一致」由 toolkit 自動保證的證據。

### 實驗：`NVIDIA_DRIVER_CAPABILITIES` 有沒有作用？

設計時的假設：預設只注入 `compute,utility`，不含 OpenGL，所以要設 `all`。實測：

| 啟動方式 | capabilities | GLX／EGL 函式庫 | nvidia 檔案數 |
|---|---|---|---|
| `--gpus all` | 預設 | 有 | 59 |
| `--gpus all` | `all` | 有 | 59 |
| `--runtime=nvidia` | 預設 | 有 | 59 |
| `--runtime=nvidia` | `compute,utility` | 有 | 59 |

**結論：在本機（Docker 29.8 + Toolkit 1.20.1）這個變數不影響注入。** 原因：
- 第一次的錯誤訊息 `failed to discover GPU vendor from CDI` 顯示 Docker 29 的 `--gpus` **直接走 CDI**，不經 nvidia runtime。
- `/etc/nvidia-container-runtime/config.toml` 中 `mode = "auto"`，新版 toolkit 在 auto 模式下也優先用 CDI。
- CDI spec 列出全部驅動檔案，不看 capabilities 變數。

compose 仍會設 `NVIDIA_DRIVER_CAPABILITIES=all`：在舊版 toolkit 或 legacy 模式的主機上它是必要的，設了在兩種模式都正確、成本為零。design D2 已依實測修正理由。

## 面試追問

**Q：Container Toolkit 到底做了什麼？**
A：在容器啟動時，把主機的 GPU 裝置節點（`/dev/nvidia*`）和與主機 kernel module 版本一致的使用者層驅動函式庫掛進容器，並設定 cgroup 允許存取。映像本身不含驅動，所以可攜、主機升級驅動也不需重建映像。

**Q：runtime hook 和 CDI 差在哪？**
A：hook 方式是包住 runc 的 NVIDIA 專屬 runtime，在 prestart hook 用程式決定注入什麼（命令式）；CDI 是廠商中立的宣告式 spec，各 runtime 原生讀取，Kubernetes 的 device plugin 也逐漸改用 CDI。業界正從前者轉向後者。

**Q：`--gpus all` 和 `--runtime=nvidia` 有什麼不同？**
A：`--gpus` 是 Docker 內建的 device request 參數（compose 的 `deploy.resources.reservations.devices` 等價於它），新版 Docker 會用 CDI 實現；`--runtime=nvidia` 是指定用 nvidia-container-runtime 取代 runc，再用 `NVIDIA_VISIBLE_DEVICES` 選卡。新環境建議用 `--gpus` 或 CDI 的 `--device nvidia.com/gpu=all`。

**Q：`NVIDIA_DRIVER_CAPABILITIES` 是什麼？一定要設嗎？**
A：legacy 模式下用來選擇注入哪類函式庫（`compute`、`utility`、`graphics`、`video`、`display`…，預設 `compute,utility`），跑 OpenGL 程式必須含 `graphics`。我實測過在 Docker 29 + toolkit 1.20 的 CDI 路徑下它不影響注入，但為了在舊環境也正確，compose 仍設為 `all`。

**Q：驅動升級後容器要怎麼辦？**
A：映像不用動。CDI spec 由 `nvidia-cdi-refresh` 監看 kernel 模組變動自動重新產生；重開機後新啟動的容器就會注入新版本函式庫。

**Q：為什麼 apt 來源要用 `signed-by`？**
A：讓金鑰的信任範圍只限於該來源。全域信任（`apt-key`）下，任何一把第三方金鑰被盜都能簽出看似 Ubuntu 官方的套件。

## 踩坑紀錄

- 安裝前的錯誤 `failed to discover GPU vendor from CDI: no known GPU vendor found`：表示 Docker 已嘗試用 CDI 找 GPU，但系統沒有任何 CDI spec。安裝 toolkit 後 `nvidia-cdi-refresh` 自動在 `/var/run/cdi/` 產生 spec 即解決，不需要手動 `nvidia-ctk cdi generate`。
