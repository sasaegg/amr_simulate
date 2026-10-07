# 07 ROS 工作區與 colcon

套件：[`ros_ws/src/amr_worlds/`](../../ros_ws/src/amr_worlds/)

## 為什麼要做

ROS 2 的程式以「套件（package）」為單位組織、建置、安裝與尋找。場景產生器、車輛模型、launch 都要各自成為套件，`ros2 run`／`ros2 launch`／`get_package_share_directory()` 才找得到它們。這一步建立第一個套件的骨架，理解工作區的運作。

## 工作區結構

```
ros_ws/                ← 掛載進容器的 /ros_ws（主機與容器是同一個資料夾）
  src/                 ← 原始碼（進版控）
    amr_worlds/        ← 一個套件
  build/               ← 建置中間產物（不進版控）
  install/             ← 安裝結果 + setup.bash（不進版控）
  log/                 ← build／test 日誌（不進版控）
```

colcon 掃描 `src/` 下所有含 `package.xml` 的資料夾，依相依關係排序，再依 build type 呼叫對應工具（ament_python → setuptools；ament_cmake → CMake）。**colcon 要在工作區根目錄（`/ros_ws`）執行**，因為 `build/ install/ log/` 會建在目前目錄。

## 做了什麼（親手操作的步驟）

### 1. 產生骨架

```bash
# 容器內（UID 1000，產生的檔案屬於主機使用者）
cd /ros_ws/src
ros2 pkg create --build-type ament_python amr_worlds
```

- `--build-type` 不給時預設是 **`ament_cmake`**（C++／CMake 骨架：`CMakeLists.txt`、`include/`、`src/`，沒有 `setup.py`）。可用 `ros2 pkg create --help` 確認。
- 只給 build type 時，其他欄位用預設值：description／license 為 `TODO`，maintainer 用目前帳號（容器內是 `ros`、`ros@todo.todo`）。本專案刻意保留這些 `TODO`。
- 沒給 `--license` 就不會產生 `LICENSE` 檔；但 package.xml 的 `<license>` 標籤（format 3 必填）會填 `TODO: License declaration`。**開源專案沒有授權條款時，法律上預設「保留所有權利」**，之後要公開到 GitHub 前再補。
- 套件名稱只能用小寫、數字、底線。

產生的檔案：

```
amr_worlds/
  package.xml             套件的身分證
  setup.py                Python 建置／安裝設定（setuptools）
  setup.cfg               可執行檔安裝位置
  resource/amr_worlds     空檔案：ament index 的標記
  amr_worlds/__init__.py  Python 模組（外層是 ROS 套件，內層是同名 Python 模組）
  test/test_copyright.py  授權標頭檢查
  test/test_flake8.py     程式風格檢查
  test/test_pep257.py     docstring 檢查
```

### 2. package.xml

```xml
<exec_depend>python3-yaml</exec_depend>      <!-- 新增：執行時需要讀 YAML -->
<test_depend>python3-pytest</test_depend>    <!-- 保留：功能測試用 -->
<export><build_type>ament_python</build_type></export>   <!-- colcon 據此選建置工具 -->
```

相依的種類：

| 標籤 | 什麼時候需要 |
|---|---|
| `build_depend` | 建置時（標頭檔、程式碼產生器） |
| `exec_depend` | 執行時 |
| `depend` | 兩者都要 |
| `test_depend` | 跑測試時 |

名稱用 **rosdep key**（如 `python3-yaml`），`rosdep install --from-paths src` 可據此自動安裝系統套件。版本號採語意化版本 `主.次.修`，`0.x` 表示開發中。

### 3. 移除三個 lint 測試

`test_copyright`（每個檔案要有授權標頭——沒設授權必定失敗）、`test_pep257`（每個函式要有 docstring——太嚴）、`test_flake8`（見踩坑紀錄）全部刪除；對應的 `test_depend` 也一併從 package.xml 拿掉，**兩邊要一致**，否則 `colcon test` 會因找不到模組而失敗。`test/` 留空，之後放功能測試。

### 4. setup.py

```python
from setuptools import find_packages, setup
from glob import glob

package_name = 'amr_worlds'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/worlds', glob('worlds/*.sdf')),
        ('share/' + package_name + '/scenes', glob('scenes/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    ...
    extras_require={'test': ['pytest']},
    entry_points={'console_scripts': []},
)
```

| 欄位 | 意思 |
|---|---|
| `packages=find_packages(exclude=['test'])` | 從 setup.py 所在目錄往下找**含 `__init__.py` 的資料夾**當 Python 模組安裝 → `['amr_worlds']`（內層那個）。會遞迴找子模組；`exclude` 是保險 |
| `data_files` | **非 Python 檔案**要裝到哪：`(目的地, [來源])`。目的地相對於安裝位置 `install/amr_worlds/`，來源相對於 setup.py |
| `install_requires` | pip 世界的執行相依（PyPI 名稱）。**colcon 不會依此安裝**；ROS 以 package.xml 為準，不在這裡重複寫 pyyaml。預設的 `setuptools` 是因為舊式 console script 執行時要用 `pkg_resources` |
| `zip_safe` | 能否打包成 zip egg 執行。舊時代旗標；現代 pip 與 colcon 的 develop 模式都不會打包，實際不起作用 |
| `extras_require` | pip 的「選配」相依：`pip install amr_worlds[test]` 才裝 pytest。colcon 不看，只是讓套件符合一般 Python 慣例（舊寫法 `tests_require` 已廢棄） |
| `entry_points.console_scripts` | **把 Python 函式變成指令**：`'gen_world = amr_worlds.gen_world:main'`（指令名 = 模組:函式）。build 時 setuptools 產生一個小執行檔放到 `lib/amr_worlds/`，`ros2 run amr_worlds gen_world` 就是執行它；`main()` 的回傳值成為結束碼。**改 entry_points 一定要重 build** |

**`data_files` 前兩行**

```
resource/amr_worlds（空檔） → install/amr_worlds/share/ament_index/resource_index/packages/amr_worlds
package.xml                → install/amr_worlds/share/amr_worlds/package.xml
```

- 第一行：**向 ROS 登記這個套件**（見下方 ament index）。
- 第二行：`share/<套件名>/` 是套件的資料夾，`get_package_share_directory('amr_worlds')` 回傳的就是它；`ros2 pkg xml` 讀這裡的 package.xml。之後 `worlds/`、`scenes/` 也裝在這裡。
- 資料裝進 share 而不是從 src 讀：使用者（launch 等）只靠 `get_package_share_directory()` 找檔案，不依賴原始碼放在哪，換機器或用 apt 安裝路徑都正確。
- **`glob()` 在 build 的那一刻執行**：現在 `worlds/` 沒有 `.sdf`，所以 install 裡的 `worlds/` 是空的；之後新增 `.sdf` 要重新 build 才會被安裝。

**setup.cfg**

```ini
[develop]
script_dir=$base/lib/amr_worlds
[install]
install_scripts=$base/lib/amr_worlds
```

setuptools 預設把可執行檔裝到 `bin/`，但 `ros2 run` 去 `lib/<套件>/` 找。少了這兩行：build 成功，`ros2 run` 找不到程式。

entry_points、setup.cfg、ros2 run 的串接：

```
ros2 run amr_worlds gen_world
  → 用 ament index 找到 amr_worlds 的安裝位置
  → 執行 <安裝位置>/lib/amr_worlds/gen_world   ← setup.cfg 決定位置、entry_points 決定產生它
  → import amr_worlds.gen_world、呼叫 main()
```

### 5. 資料夾

```bash
mkdir -p worlds scenes && touch worlds/.gitkeep scenes/.gitkeep
```

git 只追蹤檔案不追蹤資料夾；`.gitkeep` 是社群慣例的空檔名，用來保留空資料夾。

## ament index

ROS 2 用「資料夾 + 檔名」做成的**已安裝資源目錄**（像圖書館的目錄卡櫃）：

```
<prefix>/share/ament_index/resource_index/
  packages/            ← 「套件」抽屜：每個檔名 = 一個已安裝套件（內容空的）
    amr_worlds
    rclpy
  rosidl_interfaces/   ← 「訊息格式」抽屜：檔案內容列出該套件提供的 msg/srv
  ...
```

- 路徑**是固定的**：`share/` 是 Linux 慣例；`ament_index/resource_index` 是 ament 規範，寫死在工具裡（`ament_index_python.constants.RESOURCE_INDEX_SUBFOLDER = 'share/ament_index/resource_index'`）；`packages` 是資源類型名稱。**只有最後的檔名（套件名）是自己決定的**。來源檔放在套件哪裡（`resource/`）只是慣例，可以改。
- `ros2 pkg list` = 對 `AMENT_PREFIX_PATH` 每個路徑列出 `.../resource_index/packages/` 的檔名。
- 用檔案不用資料庫：不需要背景服務；underlay 和 overlay 各有一套，依 `AMENT_PREFIX_PATH` 順序疊加查詢。
- ament_cmake 套件由 `ament_package()` 自動放卡片；ament_python 用的是不認識 ROS 的 setuptools，所以要在 `data_files` 手動寫這一行。

## 建置與 source

```bash
cd /ros_ws && colcon build --symlink-install
#   Starting >>> amr_worlds
#   Finished <<< amr_worlds
```

build 完在**同一個 shell** 執行 `ros2 pkg list | grep amr` → **找不到**。原因：

```
開 shell 時讀 ~/.bashrc
  source /opt/ros/humble/setup.bash                     ✅ underlay
  [ -f /ros_ws/install/setup.bash ] && source ...       ❌ 那時 install/ 還不存在
→ AMENT_PREFIX_PATH = /opt/ros/humble
之後 build 產生了 install/setup.bash，但已開的 shell 不會自動重讀
```

```bash
source /ros_ws/install/setup.bash
echo $AMENT_PREFIX_PATH     # /ros_ws/install/amr_worlds:/opt/ros/humble
ros2 pkg list | grep amr    # amr_worlds
```

overlay 排在 underlay **前面**，所以同名套件以 overlay 優先（可覆蓋官方套件）。只有「這個 shell 開啟後才第一次 build／新增套件」時需要手動 source；新開的 shell 由 `.bashrc` 自動處理。

### 安裝結果

```bash
ls -l install/amr_worlds/share/ament_index/resource_index/packages/   # amr_worlds -> symlink
ls -l install/amr_worlds/share/amr_worlds/                             # package.xml -> symlink；worlds/ scenes/ 空的
cat install/amr_worlds/lib/python3.10/site-packages/amr-worlds.egg-link  # /ros_ws/build/amr_worlds
ros2 pkg prefix amr_worlds                                             # /ros_ws/install/amr_worlds
python3 -c "from ament_index_python.packages import get_package_share_directory; \
            print(get_package_share_directory('amr_worlds'))"          # /ros_ws/install/amr_worlds/share/amr_worlds
```

### `--symlink-install` 加與不加

| | 加 | 不加 |
|---|---|---|
| 資料檔 | symlink 指回 build → src | 複製一份 |
| Python | develop 模式：egg-link 指向原始碼 | `.py` 複製進 `site-packages/amr_worlds/` |
| 改 Python／launch／YAML | 立即生效 | 要重新 build |
| `install/` 能獨立存在 | 不能（刪 src 就壞） | 能（適合部署：映像只留 install） |

兩種模式都要重 build 的情況：新增檔案、改 setup.py／package.xml 的安裝設定、改 entry_points、改 C++。
**不要在同一工作區混用兩種模式**：install 裡殘留另一種模式的檔案會報錯（如 `existing path cannot be removed: Is a directory`），切換前要刪 `build/` 與 `install/`。entrypoint 固定用 `--symlink-install` 就是為了一致。

### 測試

```bash
colcon test --packages-select amr_worlds    # 執行測試，結果寫進 build/ 的 XML
colcon test-result --verbose                # 讀報告、列出失敗細節
#   Summary: 0 tests, 0 errors, 0 failures, 0 skipped（尚未寫功能測試）
```

`colcon test` 的終端輸出只有摘要（測試失敗時也可能顯示 Finished），要用 `test-result` 看結果。測試的是 `install/` 的內容，所以要先 build。

## 面試追問

**Q：colcon 是什麼？和 CMake 的關係？**
A：colcon 是建置工具的協調者：找出工作區所有套件、依相依排序、對每個套件呼叫它自己的建置系統（CMake 或 setuptools），可平行建置。ROS 1 用 catkin；ROS 2 套件用 ament（ament_cmake／ament_python），由 colcon 驅動。

**Q：ament_python 和 ament_cmake 怎麼選？**
A：純 Python 用 ament_python；C++、只裝資料檔、或要定義 msg/srv 的用 ament_cmake（`ros2 pkg create` 預設）。本專案 `amr_worlds`、`amr_bringup` 是 Python，`amr_description` 只裝 URDF 所以用 ament_cmake。兩者混用可用 ament_cmake + ament_cmake_python。

**Q：為什麼 build 完 `ros2 pkg list` 找不到剛建好的套件？**
A：overlay 要 source `install/setup.bash` 才會加進 `AMENT_PREFIX_PATH`；build 前就開著的 shell 沒有 source 到它。我實際遇過，source 之後就有了。

**Q：`resource/<套件名>` 那個空檔案有什麼用？**
A：ament index 的「套件卡片」。`ros2 pkg list`、`get_package_share_directory()` 是看 `share/ament_index/resource_index/packages/` 下有哪些檔名來判斷安裝了哪些套件，這個路徑寫死在 ament 工具裡。少了它，程式裝好了套件也「不存在」。

**Q：`ros2 run` 怎麼找到 Python 程式？**
A：setup.py 的 `console_scripts` 讓 setuptools 在 build 時產生執行檔，setup.cfg 把它放到 `lib/<套件>/`，`ros2 run` 透過 ament index 找到套件位置後執行那裡的檔案。

**Q：`--symlink-install` 做了什麼？什麼時候不用它？**
A：安裝時用 symlink（Python 用 develop 模式的 egg-link）指回原始碼，改 Python／launch／YAML 立即生效。部署時不用它，讓 install 成為可獨立存在的完整複製品。兩種模式不要在同一工作區混用。

**Q：ROS Python 套件的相依寫在 setup.py 還是 package.xml？**
A：以 package.xml 為準（rosdep key，`rosdep install` 會用 apt 安裝）。setup.py 的 `install_requires`／`extras_require` 是 pip 的機制，colcon 不會依此安裝。

**Q：underlay／overlay？**
A：先 source 的是 underlay（`/opt/ros/humble`），後 source 的工作區是 overlay；`AMENT_PREFIX_PATH` 中 overlay 在前，同名套件以 overlay 優先。

## 踩坑紀錄

- **build 完 `ros2 pkg list` 找不到套件**：shell 在 build 前就讀過 `.bashrc`。`source /ros_ws/install/setup.bash` 或開新 shell。
- **flake8 的 import 順序檢查沒有生效**：`setup.py` 把 `from glob import glob` 放在 `setuptools` 後面（Google 風格應該標準庫在前、第三方在後，中間空行），預期 flake8 報 `I100`，結果測試通過。查原因：ROS 的設定檔 `ament_flake8.ini` 寫了 `import-order-style = google`，但負責檢查的外掛 `flake8-import-order` 沒安裝——`ros-humble-ament-flake8` 只相依 flake8 本體，ROS 官方的整組外掛（import-order、quotes、builtins、comprehensions、docstrings…）要另外用 pip 安裝。**flake8 遇到不認識的設定不報錯、直接忽略**。教訓：設定檔寫了不等於生效，要確認工具真的在檢查。最後決定移除 flake8 測試，專注在功能測試。
