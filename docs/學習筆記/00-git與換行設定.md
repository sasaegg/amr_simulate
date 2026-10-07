# 00 git 與換行設定

## 為什麼要做

1. **版控是後面每一步的安全網**：每完成一步就 commit，任何時候都能回到上一個可用狀態；`git log` 同時是開發歷程，面試時可以照著講專案演進。
2. **換行字元會讓 Linux 上的腳本壞掉**：Windows 用 CRLF（`\r\n`），Linux 用 LF（`\n`）。shell script 若是 CRLF，第一行 `#!/bin/bash\r` 會被當成要執行 `bash\r` 這個不存在的程式，錯誤是 `/bin/bash^M: bad interpreter` 或 `exec ... no such file or directory`——在 Docker 的 entrypoint 上特別常見，而且錯誤訊息看不出原因。
3. **建置產物不進版控**：`colcon build` 產生的 `build/`、`install/`、`log/` 體積大、可由原始碼重新產生，而且內含本機絕對路徑，放進 repo 只會造成衝突。

## 做了什麼

```bash
git init -b main
```
- 建立 `.git/` 資料夾（整個版本庫的資料都在這裡）。
- `-b main`：指定預設分支名稱。git 2.34 不指定時預設是 `master`；現在 GitHub 等平台預設為 `main`，一開始就統一可避免之後推到遠端時要改名。

`.gitattributes`：
```
* text=auto eol=lf
```
- `*`：套用到所有檔案。
- `text=auto`：讓 git 自動判斷是文字檔還是二進位檔；二進位檔（圖片等）不會被轉換換行。
- `eol=lf`：文字檔在**工作目錄**中一律使用 LF；repo 內部本來就統一存 LF。
- 另外明確標記二進位檔（2026-10-07 補上）：

  ```
  *.png binary
  *.jpg binary
  *.pgm binary   # slam_toolbox 存出的地圖影像
  *.stl binary   # 3D 模型
  *.dae binary   # 3D 模型（COLLADA，本質是 XML）
  ```

  `binary` 等於 `-diff -merge -text`：不轉換換行、不做文字 diff 與合併。`text=auto` 只看檔案開頭有沒有 NUL 位元組來猜是不是二進位，**ASCII 版的 STL、XML 格式的 DAE、純文字變體的 PGM 會被誤判成文字檔而被改換行，模型或地圖就壞了**，所以要明確標記，不靠猜。
- 這是 **repo 層級**的設定，會跟著 repo 走，任何人 clone 都生效；相對地 `core.autocrlf` 是**個人電腦層級**設定，靠每個人自己設，不可靠。

`.gitignore`：
```
build/  install/  log/        # colcon 建置產物
__pycache__/  .pytest_cache/  # Python 快取
.env.local                    # 個人本機覆寫設定
```
- `.env` 本身要進版控：它只放非機密的預設值（`ROS_DOMAIN_ID`、`WORLD` 等），別人 clone 下來就能直接跑。若某人要覆寫，放在不進版控的 `.env.local`。

## 怎麼驗證

```bash
git status                                   # 首次 commit 後：nothing to commit, working tree clean
git log --oneline                            # 看得到首次 commit
git check-attr eol -- openspec/config.yaml   # openspec/config.yaml: eol: lf
git check-ignore -v ros_ws/build             # 顯示是 .gitignore 哪一行忽略了它
```

## 踩坑紀錄

- **`git status` 中文檔名顯示成 `"docs/\345\255\270..."`**：git 預設 `core.quotepath=true`，會把非 ASCII 位元組以八進位跳脫。只是顯示問題，檔案本身沒壞。解法：`git config --global core.quotepath false`。
- **首次 commit 前沒設定身分**：`git commit` 會報 `Please tell me who you are`。用 `git config --global user.name` / `user.email` 設定；這兩個值會寫進每個 commit 的作者欄位，推到 GitHub 時 email 用來對應帳號。

## 面試追問

**Q：`.gitattributes` 和 `core.autocrlf` 差在哪？為什麼選前者？**
A：`core.autocrlf` 是每台電腦自己的 git 設定，團隊裡只要有一個人沒設，就會把 CRLF 帶進 repo；`.gitattributes` 是放在 repo 裡、跟著版本走的規則，對所有人強制生效。所以團隊專案用 `.gitattributes` 才可靠。

**Q：如果已經有 CRLF 的檔案進了 repo 怎麼辦？**
A：加上 `.gitattributes` 後執行 `git add --renormalize .`，讓 git 依新規則重新正規化所有檔案，再 commit。

**Q：為什麼 `.env` 要進版控？不是說 `.env` 不能 commit 嗎？**
A：不能 commit 的是**含機密**的 `.env`（密碼、API key）。這個專案的 `.env` 只有預設參數，進版控才能讓別人 clone 後直接執行。原則是：預設值進版控、機密與個人覆寫不進版控。

**Q：為什麼不把 `install/` 一起 commit，省得別人重建？**
A：建置產物依賴建置當下的環境（路徑、套件版本），換一台機器不一定能用；而且可以由原始碼確定性地重新產生。版控應該只存「無法重新產生的東西」。

**Q：為什麼空的 `ros_ws/` 沒有被 commit？**
A：git 只追蹤檔案內容，不追蹤資料夾；資料夾只是檔案路徑的一部分。要保留空資料夾，慣例是放一個 `.gitkeep` 空檔（例如 `openspec/specs/.gitkeep`）。`ros_ws/` 之後放進套件就自然出現了。

**Q：commit 的粒度怎麼抓？**
A：一個 commit 做一件完整、可驗證的事，且 commit 後專案仍處於可用狀態。這個專案的規則是「一個 task 一個 commit，程式與對應筆記放在一起」。
