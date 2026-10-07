# 05 entrypoint

檔案：[`docker/amr_sim/entrypoint.sh`](../../docker/amr_sim/entrypoint.sh)、[`docker/amr_sim/Dockerfile`](../../docker/amr_sim/Dockerfile)

## 為什麼要做

容器每次啟動都要先做準備：載入 ROS 環境、（必要時）建置掛載進來的工作區、載入工作區環境，然後才執行真正的程式。這段「每次都要做的事」就是 entrypoint。基底映像的 `/ros_entrypoint.sh` 只會 source ROS，不處理工作區，所以換成自己的。

## 做了什麼

### entrypoint.sh

```bash
#!/bin/bash
set -e                                              # 任何一步失敗就停止
source "/opt/ros/${ROS_DISTRO}/setup.bash" --       # 1. underlay：apt 裝的 ROS
if [ -d /ros_ws/src ] && { [ ! -f /ros_ws/install/setup.bash ] || [ "${BUILD:-0}" = "1" ]; }; then
    (cd /ros_ws && colcon build --symlink-install)  # 2. 必要時才建置
fi
if [ -f /ros_ws/install/setup.bash ]; then
    source /ros_ws/install/setup.bash --            # 3. overlay：自己的工作區
fi
exec "$@"                                           # 4. 換成目標程式
```

- **不用 `set -u`**：ROS 的 setup.bash 會引用未定義變數，加了會直接失敗。
- **`source ... --`**：bash 的 `source` 不帶參數時，被 source 的腳本會繼承目前的 `$@`（例如 `ign gazebo --version`），setup.bash 會誤把它們當自己的參數解析。`--` 明確表示沒有參數。
- **條件建置**：有原始碼（`/ros_ws/src` 存在）且「從沒建置過」或 `BUILD=1` 才 build；平常啟動不重複建置。沒掛載工作區時直接跳過。
- **underlay／overlay**：先 source `/opt/ros/humble`（underlay），再 source 工作區（overlay）；overlay 同名套件會覆蓋 underlay。
- **`(cd /ros_ws && ...)`**：括號開子 shell，`cd` 不影響外面的工作目錄。

### Dockerfile 的變更

```dockerfile
# apt 清單移除 liburdfdom-tools（check_urdf 已由基底的 ros-humble-urdfdom 提供）

USER ${USERNAME}
WORKDIR /ros_ws

RUN printf '%s\n' \
        "source /opt/ros/${ROS_DISTRO}/setup.bash" \
        "[ -f /ros_ws/install/setup.bash ] && source /ros_ws/install/setup.bash" \
        >> ~/.bashrc

COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
```

**`.bashrc` 那段**
- `docker exec` **不經過 entrypoint**，exec 進去的互動式 shell 只會讀 `~/.bashrc`，所以也在這裡 source。
- `printf '%s\n' A B`：格式對每個參數重複套用 → 一個參數一行。不用 `echo`：Ubuntu 的 `/bin/sh` 是 dash，`echo` 行為與 bash 不同；`printf` 各 shell 一致。
- 雙引號裡的 `${ROS_DISTRO}` 在**建置時**展開（基底有 `ENV ROS_DISTRO=humble`），寫入的是 `source /opt/ros/humble/setup.bash`。
- `[ -f ... ] && source ...`：工作區 setup 在建置時不存在，每次開 shell 才檢查——之後 build 工作區不需重建映像。
- `>>` 附加，不是 `>` 覆蓋（否則 Ubuntu 預設的提示字元、補全設定全沒了）。
- 必須在 `USER ros` 之後，`~` 才是 `/home/ros`。
- **不會重複附加**：RUN 每次都從上一層（useradd 剛建好的乾淨 `.bashrc`）開始執行；沒改時直接用快取，根本不再執行。只有放在執行期會重複跑的地方（例如 entrypoint）才會越加越多。
- **限制**：Ubuntu 預設 `.bashrc` 開頭對非互動式 shell 直接 `return`，所以只有互動式 shell 會載入（`docker exec -it ... bash` 可以；`docker exec ... bash -c '...'` 不行，要加 `-i`）。

**`COPY --chmod=755`**
- 755 = `rwxr-xr-x`（擁有者 rwx=4+2+1、群組 r-x=4+1、其他 r-x）。entrypoint 由 kernel 直接執行，沒有 `x` 位元容器一啟動就 `permission denied`。
- 不加的話 COPY 沿用來源檔權限；Windows／NTFS、zip 下載、某些編輯器存檔都可能讓執行位元遺失，而且 build 不會報錯。
- 不用 `COPY` + `RUN chmod +x`：改權限在層的世界等於改檔案，會把整個檔案再存一份、多一層。
- COPY 的檔案預設擁有者是 root（不受 `USER` 影響），755 讓容器內的 `ros` 只能讀與執行，不能改。
- 需要 BuildKit（Docker 23+ 預設）。

**`COPY` 放最後**：最常修改的檔案放最後，改它只重建這一層。

**`ENTRYPOINT` + `CMD`**
- 實際執行 = ENTRYPOINT + CMD（兩個陣列串接）；`exec "$@"` 的 `$@` 就是 CMD。

| 啟動方式 | 實際執行 |
|---|---|
| `docker run -it amr-sim:humble` | `entrypoint.sh bash` |
| `docker run amr-sim:humble ign gazebo --version` | `entrypoint.sh ign gazebo --version`（取代 CMD） |
| `docker run --entrypoint ls amr-sim:humble /` | `ls /`（entrypoint.sh 不執行） |
| compose `command: ros2 launch ...` | `entrypoint.sh ros2 launch ...` |

- **一定用 exec form（JSON 陣列）**：shell form 會包成 `/bin/sh -c`，sh 成為 PID 1（訊號送不到你的程式），而且 CMD 與 `docker run` 的參數會被忽略。
- **為什麼要重寫 `CMD ["bash"]`**：Dockerfile 一設定 ENTRYPOINT，從基底繼承的 CMD 就會被清空；不重寫的話 `exec "$@"` 沒東西可執行，容器立刻結束。
- `CMD bash` 要搭配 `-it` 才會停在 shell；沒有輸入時 bash 立刻結束。

## PID 1 與訊號

`docker stop`／Ctrl+C 的 SIGTERM **只送給 PID 1**。

- **沒有 exec**：bash 是 PID 1、目標程式是子程序；bash 不轉發 SIGTERM → 程式收不到 → 10 秒後被 SIGKILL 強制終止（ROS 節點來不及正常關閉）。
- **有 exec**：bash 被取代，目標程式本身是 PID 1，直接收到訊號。

**但 PID 1 還有特殊規則**：kernel 對 PID 1 不套用訊號的預設動作——沒有自己註冊處理函式的話，SIGTERM 會被**忽略**。所以光有 exec 還不夠，compose 要加 `init: true`，讓 **tini** 當 PID 1：負責轉發訊號、回收殭屍程序。

## 怎麼驗證（2026-10-07 實測）

```bash
docker build -t amr-sim:humble docker/amr_sim
docker image inspect amr-sim:humble --format 'ENTRYPOINT={{json .Config.Entrypoint}} CMD={{json .Config.Cmd}}'
#   ENTRYPOINT=["/usr/local/bin/entrypoint.sh"] CMD=["bash"]
docker run --rm amr-sim:humble bash -c 'echo $ROS_DISTRO; which ros2'
#   humble  /opt/ros/humble/bin/ros2
```

**PID 實驗**

```bash
docker run --rm amr-sim:humble ps -o pid,ppid,comm               # 有 exec
#   1  0 ps
docker run --rm amr-sim:humble bash -c 'ps -o pid,ppid,comm; true'   # 模擬沒有 exec
#   1  0 bash
#  14  1 ps
```
（`; true` 讓 bash 不對最後一個指令做 exec 最佳化。）

**訊號實驗**

```bash
docker run --rm -d --name t1 amr-sim:humble sleep 100 && time docker stop t1          # 10.23 s
docker run --rm -d --init --name t2 amr-sim:humble sleep 100 && time docker stop t2   #  0.17 s
```
`sleep` 當 PID 1 時忽略 SIGTERM，等滿 10 秒被 SIGKILL；有 tini 時不到 0.2 秒。

**`.bashrc`**

| 指令 | 結果 |
|---|---|
| `grep -c 'source /opt/ros' /home/ros/.bashrc` | `1` |
| `docker exec t3 bash -ic 'which ros2'`（互動式） | `/opt/ros/humble/bin/ros2` |
| `docker exec t3 bash -c 'which ros2'`（非互動式） | 找不到 |

**條件建置**（掛載一個只有空 `src/` 的工作區）

| 執行 | 結果 |
|---|---|
| 第 1 次 | 印出 `[entrypoint] colcon build --symlink-install`，產生 `build/ install/ log/`，擁有者 UID 1000 |
| 第 2 次 | 跳過建置 |
| `-e BUILD=1` | 強制重建 |

## 面試追問

**Q：ENTRYPOINT 和 CMD 差在哪？**
A：ENTRYPOINT 是每次都執行的前置程式，CMD 是預設參數（通常是要跑的程式），實際執行兩者串接。`docker run` 映像後面接的指令取代 CMD；要換 ENTRYPOINT 得用 `--entrypoint`。compose 的 `command` 對應 CMD、`entrypoint` 對應 ENTRYPOINT。

**Q：exec form 和 shell form？**
A：exec form（JSON 陣列）直接執行；shell form 包成 `/bin/sh -c`，sh 變 PID 1、訊號送不到程式，且 ENTRYPOINT 用 shell form 時 CMD 被忽略。兩者都該用 exec form。

**Q：entrypoint 腳本最後為什麼要 `exec "$@"`？**
A：讓目標程式取代 shell 成為 PID 1，直接收到 SIGTERM 正常關閉。我實測過：不處理的話 `docker stop` 要等 10 秒被強制 kill。

**Q：有了 exec 為什麼還要 `init: true`？**
A：kernel 對 PID 1 不套用訊號預設動作，沒註冊處理函式的程式當 PID 1 會忽略 SIGTERM；PID 1 也負責回收孤兒程序。tini 專門做這兩件事。實測 `sleep` 當 PID 1 停止要 10.2 秒，加 `--init` 只要 0.17 秒。

**Q：為什麼 `docker exec` 進去沒有 ROS 環境？**
A：exec 是在已執行的容器裡開新程序，不經過 entrypoint，也不繼承 entrypoint 裡 source 出來的變數（那些只存在於 entrypoint 的程序樹）。解法是寫進 `~/.bashrc`，互動式 shell 會讀；非互動式要用 `bash -ic`。

**Q：在 Dockerfile 裡 `>> ~/.bashrc` 會不會每次 build 都加一次？**
A：不會。每個 RUN 從上一層的狀態執行，上一層的 `.bashrc` 永遠是乾淨的；沒改就用快取不執行。會累積的是放在執行期重複跑的地方，那時要寫成冪等（先 grep 再附加）。

**Q：為什麼用 `COPY --chmod` 而不是 `RUN chmod`？**
A：不依賴來源檔權限；也避免多一層把整個檔案再存一份。

## 踩坑紀錄

- 移除 `liburdfdom-tools`（筆記 04 發現多餘）讓 apt 那層與其後所有層重建——親眼看到「改前面的層，後面全部重建」。映像大小不變（5.61 GB），因為那個套件很小。
