# 07 ROS 工作區與 colcon

套件：[`ros_ws/src/amr_worlds/`](../../ros_ws/src/amr_worlds/)

## 為什麼要做

ROS 2 的程式以「套件（package）」為單位組織、建置、安裝與尋找。場景產生器、車輛模型、launch 都要各自成為套件，`ros2 run`／`ros2 launch`／`get_package_share_directory()` 才找得到它們。這一步先建立第一個套件的骨架，理解工作區的運作。

## 工作區結構

```
ros_ws/                ← 掛載進容器的 /ros_ws
  src/                 ← 原始碼（進版控）
    amr_worlds/        ← 一個套件
  build/               ← 建置中間產物，每個套件一個資料夾（不進版控）
  install/             ← 安裝結果 + setup.bash（不進版控）
  log/                 ← 每次 build／test 的日誌（不進版控）
```

colcon 掃描 `src/` 下所有含 `package.xml` 的資料夾，依相依關係排序，再依套件的 build type 呼叫對應工具（ament_python → setuptools；ament_cmake → CMake）。

## 做了什麼

在容器內用官方工具產生骨架（以 UID 1000 執行，檔案屬於主機使用者）：

```bash
cd /ros_ws/src
ros2 pkg create --build-type ament_python --license Apache-2.0 \
  --maintainer-name leo --maintainer-email stu002031@gmail.com \
  --description "倉庫場景描述（YAML）與 Gazebo world 產生器" amr_worlds
```

產生後的調整：
- 刪掉 `test_copyright.py`（要求每個檔案都有授權標頭）與 `test_pep257.py`（要求每個函式都有 docstring），只保留 `test_flake8.py`（程式風格檢查）。
- 版本改 `0.1.0`；加 `python3-yaml` 執行相依。
- 建立 `worlds/`、`scenes/`（放 `.gitkeep`，git 不追蹤空資料夾），並在 `setup.py` 安裝它們。

### 檔案逐一說明

```
amr_worlds/
  package.xml            套件的身分證：名稱、版本、相依、build type
  setup.py               Python 的建置／安裝設定（setuptools）
  setup.cfg              指定可執行檔安裝位置
  resource/amr_worlds    空檔案：ament index 的標記
  amr_worlds/__init__.py Python 模組（之後放 gen_world.py）
  test/test_flake8.py    風格檢查測試
  worlds/ scenes/        資料檔
  LICENSE
```

**package.xml**（format 3）
```xml
<exec_depend>python3-yaml</exec_depend>     <!-- 執行時需要 -->
<test_depend>ament_flake8</test_depend>     <!-- 測試時需要 -->
<test_depend>python3-pytest</test_depend>
<export><build_type>ament_python</build_type></export>   <!-- colcon 據此選建置工具 -->
```
相依的種類：`build_depend`（建置時）、`exec_depend`（執行時）、`depend`（兩者都要）、`test_depend`（測試時）。名稱用 **rosdep key**（如 `python3-yaml`），`rosdep install` 能據此自動裝系統套件。本專案相依已在 Dockerfile 明確安裝，但 package.xml 仍要宣告完整——這是套件的契約。

**setup.py** 的 `data_files`：`(安裝目的地, [來源檔案])`
```python
('share/ament_index/resource_index/packages', ['resource/amr_worlds']),  # 註冊到 ament index
('share/amr_worlds', ['package.xml']),
('share/amr_worlds/worlds', glob('worlds/*.sdf')),
('share/amr_worlds/scenes', glob('scenes/*.yaml')),
```
`entry_points.console_scripts` 之後會加 `gen_world = amr_worlds.gen_world:main`，讓 `ros2 run amr_worlds gen_world` 能執行。

**setup.cfg**
```ini
[develop]
script_dir=$base/lib/amr_worlds
[install]
install_scripts=$base/lib/amr_worlds
```
setuptools 預設把可執行檔裝到 `bin/`，但 `ros2 run <套件> <程式>` 是去 `lib/<套件>/` 找——這兩行把位置改對。少了它，build 成功但 `ros2 run` 找不到程式。

**resource/amr_worlds（空檔案）**
ament index 是「用檔案系統當資料庫」：`share/ament_index/resource_index/packages/` 下每個檔名就是一個已安裝的套件。`ros2 pkg list`、`get_package_share_directory()` 都靠它找套件，所以內容是空的也必須存在。

### ament_python 與 ament_cmake

| | ament_python | ament_cmake |
|---|---|---|
| 建置工具 | setuptools（`setup.py`） | CMake（`CMakeLists.txt`） |
| 適合 | 純 Python 節點、工具 | C++ 節點、只裝資料檔的套件、需要產生訊息介面（msg/srv） |
| 本專案 | `amr_worlds`、`amr_bringup` | `amr_description`（只安裝 URDF 資料檔） |

## 建置與 `--symlink-install`

```bash
cd /ros_ws && colcon build --symlink-install
#   Starting >>> amr_worlds
#   Finished <<< amr_worlds [0.70s]
```

`--symlink-install` 的效果（實測）：
- `install/amr_worlds/share/amr_worlds/package.xml -> /ros_ws/build/amr_worlds/package.xml`（symlink，build 目錄再連回 src）
- Python 套件以 **develop 模式**安裝：`site-packages/amr-worlds.egg-link` 內容是 `/ros_ws/build/amr_worlds`，直接指回原始碼

→ 修改 Python、YAML、launch 檔**不需要重新 build**。新增檔案、改 `setup.py`／`package.xml`、改 entry point 時才需要。

## underlay 與 overlay

```
underlay：/opt/ros/humble       apt 安裝的 ROS（先 source）
overlay ：/ros_ws/install        自己的工作區（後 source，蓋在上面）
```
source 之後 `AMENT_PREFIX_PATH=/ros_ws/install/amr_worlds:/opt/ros/humble`：搜尋套件時先找 overlay，所以 overlay 裡的同名套件會**覆蓋** underlay（可以拿官方套件原始碼來改）。

## 怎麼驗證（2026-10-07 實測）

```bash
# 容器內
cd /ros_ws && colcon build --symlink-install     # 1 package finished
# 開新 shell 後
ros2 pkg list | grep amr                          # amr_worlds
ros2 pkg prefix amr_worlds                        # /ros_ws/install/amr_worlds
colcon test --packages-select amr_worlds && colcon test-result --verbose
#   1 test, 0 errors, 0 failures, 0 skipped（flake8 通過）
```

主機上 `ros_ws/build`、`install`、`log` 擁有者皆為 UID 1000；`git status` 只看到 `src/` 下的檔案（建置產物被 `.gitignore` 排除）。

## 面試追問

**Q：colcon 是什麼？和 catkin、CMake 的關係？**
A：colcon 是「建置工具的協調者」：找出工作區所有套件、依相依排序、對每個套件呼叫它自己的建置系統（CMake 或 setuptools），可平行建置。catkin 是 ROS 1 的建置系統；ROS 2 套件用 ament（ament_cmake／ament_python），由 colcon 統一驅動。

**Q：`--symlink-install` 做了什麼？什麼時候還是要重 build？**
A：安裝時用 symlink（Python 則是 develop 模式的 egg-link）指回原始碼，改 Python／launch／YAML 立即生效。新增檔案、改 setup.py／package.xml／entry point、改 C++ 都要重 build。

**Q：為什麼 build 完 `ros2 pkg list` 找不到剛建好的套件？**
A：overlay 要 source `install/setup.bash` 才會加進 `AMENT_PREFIX_PATH`。已開著的 shell 在 build 之前 source 過（當時 install 還不存在），要重新 source 或開新 shell。我實際遇過這個狀況。

**Q：`resource/<套件名>` 那個空檔案有什麼用？**
A：ament index 的標記。`ros2 pkg list` 等工具是看 `share/ament_index/resource_index/packages/` 下有哪些檔名來判斷安裝了哪些套件；少了它套件就「不存在」。

**Q：setup.cfg 那兩行在做什麼？**
A：把 console script 裝到 `lib/<套件名>/`，因為 `ros2 run` 在那裡找可執行檔；setuptools 預設是 `bin/`。

**Q：underlay／overlay？**
A：先 source 的是 underlay（例如 /opt/ros/humble），後 source 的工作區是 overlay；同名套件以 overlay 優先，可以覆蓋官方套件。

**Q：package.xml 的 exec_depend 和 build_depend 差在哪？**
A：build_depend 是建置時需要（例如標頭檔、程式碼產生器），exec_depend 是執行時需要，depend 是兩者皆是，test_depend 只有測試需要。名稱用 rosdep key，`rosdep install --from-paths src` 會自動安裝。

## 踩坑紀錄

- **build 完 `ros2 pkg prefix amr_worlds` 回 `Package not found`**：執行 build 的那個 shell 在 build 前就讀了 `.bashrc`，那時 `install/setup.bash` 不存在所以沒被 source。開新 shell（或 `source install/setup.bash`）即可。下一次容器啟動時 entrypoint 也會自動 source。
