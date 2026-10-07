# 01 docker 群組

## 為什麼要做

`docker` 指令只是 client，真正建立與執行容器的是以 root 執行的 **dockerd** daemon。兩者透過 unix socket `/var/run/docker.sock` 溝通（HTTP REST API）：

```
docker CLI ──▶ /var/run/docker.sock ──▶ dockerd (root) ──▶ containerd ──▶ runc ──▶ 容器
```

socket 的權限：

```
$ ls -l /var/run/docker.sock
srw-rw---- 1 root docker 0 ... /var/run/docker.sock
```

| 欄位 | 意義 |
|---|---|
| `s` | socket 檔 |
| `rw-` | 擁有者 root 可讀寫 |
| `rw-` | `docker` 群組成員可讀寫 |
| `---` | 其他人不可存取 |

不在 `docker` 群組 → 打不開 socket → `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`。

## 做了什麼

```bash
sudo usermod -aG docker $USER
```

- `-G docker`：設定附加群組。
- **`-a`（append）不可省略**：沒有 `-a` 時 `-G` 會**取代**整個附加群組清單，帳號會失去 `sudo` 等群組。
- 實際效果是修改 `/etc/group`：`docker:x:999:` → `docker:x:999:myuser`。

接著**重新登入（本次是重開機）**。群組清單是在登入時讀取 `/etc/group` 並附加到登入程序上，之後所有子程序繼承這份清單；已在執行的程序不會更新。`newgrp docker` 只會在目前終端開一個帶新群組的子 shell，其他視窗（包括從桌面啟動的 app）都不受影響。

## 怎麼驗證

```bash
getent group docker          # 改完立即可見：docker:x:999:myuser
id -nG                       # 重新登入後：... docker
docker run --rm hello-world  # 不加 sudo：Hello from Docker!
```

實際結果（2026-10-07）：`id -nG` 含 `docker`，`hello-world` 不加 sudo 成功。

## 面試追問

**Q：為什麼說 docker 群組等同 root？**
A：dockerd 以 root 執行，會照請求掛載任何主機路徑。例如 `docker run -v /:/host -it ubuntu chroot /host` 就能以 root 身分操作整個主機檔案系統，而且不需要密碼、不會留下 sudo 紀錄。所以把人加進 docker 群組等於給他 root。

**Q：那在多人或正式環境怎麼辦？**
A：
- **rootless Docker**：daemon 以一般使用者執行，搭配 user namespace，容器內的 root 對應到主機上的非特權 UID。
- **Podman**：無 daemon、預設 rootless，指令與 docker 相容。
- 只允許 `sudo docker`：至少有稽核紀錄，可用 sudoers 限制。
- 單人開發機（本專案）本來就有 sudo，加入群組的風險可接受。

**Q：為什麼加完群組 `id` 還看不到？**
A：群組在登入時才附加到程序上，子程序繼承父程序的群組；`/etc/group` 改了不會影響已在執行的程序。要重新登入（或 `newgrp` 開新 shell）。

**Q：docker CLI 和 daemon 一定要在同一台機器嗎？**
A：不用。CLI 只是對 API 發請求，可用 `DOCKER_HOST=ssh://user@host` 或 docker context 連到遠端 daemon。這也說明了為什麼「能存取 socket」就是權限邊界。

**Q：dockerd、containerd、runc 各做什麼？**
A：dockerd 提供 Docker API、映像建置、網路與 volume 管理；containerd 管理容器生命週期與映像存放；runc 是依 OCI 規格實際呼叫 kernel（namespace、cgroup）把程序跑成容器的低階 runtime。之後 NVIDIA Container Toolkit 就是在 runc 建立容器前插入一個 hook。

**附帶觀察**：本帳號也在 `lxd` 群組，同理等同 root（lxd daemon 也是 root 執行）。
