# 02 NVIDIA 驅動

## 為什麼要做

容器與主機共用同一顆 kernel，GPU 的 kernel module 只能裝在主機上；之後 NVIDIA Container Toolkit 也是把**主機已安裝**的驅動函式庫注入容器。所以主機驅動是容器用 GPU 的前提。

安裝前的現況：

| 項目 | 結果 | 意義 |
|---|---|---|
| `lspci` | Intel Alder Lake-P 內顯 + NVIDIA GA106M（RTX 3060 Mobile） | 雙顯卡筆電 |
| `lsmod` | `nouveau`、`i915` 已載入 | 3060 由開源逆向驅動 nouveau 接管 |
| `uname -r` | `6.8.0-138-generic`（HWE kernel） | 模組要對應這個 kernel |
| `mokutil --sb-state` | SecureBoot disabled | 不需要 MOK 簽章流程 |

## 做了什麼

### 1. 安裝驅動

最終狀態：`nvidia-driver-580-open`（580.178.04），kernel module 來自預編譯套件 `linux-modules-nvidia-580-open-generic-hwe-22.04`。原計畫是 `ubuntu-drivers` 推薦的 595-open，排查黑畫面（見踩坑紀錄）的過程中改用 580-open 並維持。

```bash
sudo ubuntu-drivers install nvidia:580-open   # 格式：驅動:版本
sudo apt install -y mesa-utils                # 提供 glxinfo
sudo reboot
```

安裝時套件會做三件事：
1. 安裝 kernel module（`nvidia`、`nvidia_modeset`、`nvidia_drm`、`nvidia_uvm`）與使用者層函式庫（`libnvidia-gl`、`libnvidia-compute`…）。
2. 把 nouveau 加入黑名單並重建 initramfs——同一張卡只能被一個 kernel module 接管，而 nouveau 也在開機早期映像裡，要重建才不會被它搶先載入。
3. 設定 `nvidia_drm modeset=1`（`/etc/modprobe.d/nvidia-graphics-drivers-kms.conf`），讓 NVIDIA 驅動支援 kernel modesetting，PRIME 與 Wayland 都需要它。

必須重開機：nouveau 正在驅動顯示，執行中無法卸載。

### 2. 改用 Xorg

```
# /etc/gdm3/custom.conf
WaylandEnable=false
```

登入畫面（GDM）只提供 Xorg session。原因見踩坑紀錄。

## 三個必懂的概念

### nouveau / 閉源 / open 的差別

| | kernel module | 使用者層函式庫 | 作者 |
|---|---|---|---|
| nouveau | 開源（逆向工程） | Mesa | 社群 |
| `nvidia-driver-580` | 閉源 | 閉源 | NVIDIA |
| **`nvidia-driver-580-open`** | **開源**（NVIDIA 官方，2022 起） | 閉源 | NVIDIA |

nouveau 無法調高新卡時脈、3D 效能很差、不支援 CUDA。`-open` 只有 kernel module 開源；能這樣做是因為 Turing（RTX 20）之後大部分邏輯移到 GPU 上的 **GSP 韌體**，kernel module 變薄。NVIDIA 官方建議 Turing 之後的卡使用 open 版；3060 是 Ampere。

### 預編譯模組 vs DKMS

kernel module 必須針對特定 kernel 版本編譯：
- **DKMS**：每次 kernel 更新就在本機重新編譯；需要 headers 與 gcc，編譯失敗會讓開機後沒有 GPU 驅動；Secure Boot 下還要自行簽章（MOK）。
- **預編譯**（本專案採用）：Canonical 編好並簽章，隨 kernel 發布；meta 套件 `linux-modules-nvidia-580-open-generic-hwe-22.04` 讓 kernel 升級時自動拉進對應版本。`ubuntu-drivers` 會自動選這種。

### 雙顯卡與 PRIME

`nvidia-prime` 提供 `prime-select`：

| 模式 | 行為 |
|---|---|
| `intel` | NVIDIA 關閉 |
| **`on-demand`**（本機） | Intel 負責桌面合成；程式**明確要求**時才由 NVIDIA 繪圖，畫完交回顯示 |
| `nvidia` | 全部由 NVIDIA 執行 |

「明確要求」靠兩個環境變數：
- `__NV_PRIME_RENDER_OFFLOAD=1`：要求 NVIDIA 驅動以 offload 模式提供繪圖。
- `__GLX_VENDOR_LIBRARY_NAME=nvidia`：告訴 **GLVND**（OpenGL 的分派層，讓多家驅動共存）把 GLX 呼叫交給 NVIDIA 的實作，而不是 Mesa。

這就是 compose 裡要設這兩個變數的原因。

**反向的情況：reverse PRIME。** 這台筆電的 HDMI 輸出是**實體接在 NVIDIA 上**。`xrandr --listproviders` 中 NVIDIA 顯示為 `NVIDIA-G0`、能力 `Sink Output`：Intel（modesetting）負責合成畫面，再交給 NVIDIA 從 HDMI-1-0 輸出。

## 怎麼驗證

```bash
nvidia-smi                                   # RTX 3060 Laptop GPU、Driver 580.178.04
lsmod | grep -E '^(nvidia|nouveau)'          # 有 nvidia*、沒有 nouveau
dpkg -l | grep -E '^ii.*(nvidia|dkms)'       # linux-modules-nvidia-580-open-*，沒有 nvidia-dkms-*
prime-select query                           # on-demand
echo $XDG_SESSION_TYPE                       # x11
xrandr --listproviders                       # modesetting + NVIDIA-G0
glxinfo -B | grep renderer
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia glxinfo -B | grep renderer
```

實際結果（2026-10-07）：

| 指令 | 輸出 |
|---|---|
| `glxinfo -B`（不加變數） | `Mesa Intel(R) Graphics (ADL GT2)` |
| `glxinfo -B`（加 PRIME 變數） | `NVIDIA GeForce RTX 3060 Laptop GPU/PCIe/SSE2` |

同一個程式，只差兩個環境變數，繪圖的 GPU 就換了——容器內之後要驗證的就是同一件事。

## 踩坑紀錄

**症狀**：安裝 NVIDIA 驅動（試過 595 與 580）後重開機，kernel module 正常載入、gnome-shell 也在 Wayland 下啟動了，但接在 HDMI 的外接螢幕一片黑。

**原因**：HDMI 埠實體接在 NVIDIA 獨顯上（`/sys/class/drm` 中為 `card2-HDMI-A-1`），而 Ubuntu 22.04 的 Wayland compositor（mutter 42）對「輸出接在第二張 GPU（非主繪圖 GPU）」的支援不成熟。Xorg 則有成熟的 reverse PRIME 機制處理這種接法。

**排查過程**：先 `sudo apt purge 'nvidia-*'` 退回 nouveau 確保有畫面，再改裝 580-open 並在 `/etc/gdm3/custom.conf` 設 `WaylandEnable=false`。

**解法**：關閉 Wayland、改用 Xorg 後畫面正常。對本專案沒有副作用：容器本來就只用標準 X11。

**救援方式備忘**：開機後黑畫面時，`Ctrl+Alt+F3` 切到文字終端登入，`sudo apt purge 'nvidia-*' && sudo reboot` 退回 nouveau。

## 面試追問

**Q：容器裡能不能自己裝 NVIDIA 驅動？**
A：kernel module 不行——容器沒有自己的 kernel。只能裝使用者層函式庫，但它與主機 kernel module 之間是私有介面，版本必須完全一致，否則出現 `Driver/library version mismatch` 或無聲退回 llvmpipe。所以改用 Container Toolkit 在啟動時注入主機的函式庫（筆記 03）。

**Q：為什麼選 open kernel module？**
A：NVIDIA 官方對 Turing 之後的架構建議 open 版；它是 NVIDIA 自己維護的開源 kernel module，不是 nouveau，效能與功能相同，只是授權與 kernel 社群相容性較好。

**Q：預編譯模組和 DKMS 怎麼選？**
A：有預編譯就用預編譯：不需在本機編譯、已簽章（Secure Boot 可直接用）、隨 kernel 一起升級。DKMS 適合沒有官方預編譯的 kernel（自編 kernel、特殊版本）。

**Q：筆電雙顯卡下，程式怎麼決定用哪張卡？**
A：`on-demand` 模式下預設用內顯；設 `__NV_PRIME_RENDER_OFFLOAD=1` 與 `__GLX_VENDOR_LIBRARY_NAME=nvidia` 的程式才由 NVIDIA 繪圖（Vulkan 用 `__VK_LAYER_NV_optimus=NVIDIA_only`）。GLVND 是讓多家 OpenGL 實作共存並依變數分派的那一層。

**Q：為什麼關掉 Wayland？會不會影響專案？**
A：外接螢幕接在 NVIDIA 上，22.04 的 mutter 在這種接法下黑畫面；Xorg 有 reverse PRIME 能處理。專案的容器只用 X11 協定送畫面，在 Xorg 下反而更直接（不經 XWayland），沒有負面影響。

**Q：`nvidia-smi` 顯示的 CUDA Version 13.0 是什麼？**
A：是這版驅動**支援的最高** CUDA runtime 版本，不代表系統裝了 CUDA toolkit。容器裡的 CUDA 映像只要版本不高於它即可運作。
