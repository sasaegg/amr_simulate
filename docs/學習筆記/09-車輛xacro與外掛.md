# 09 車輛 xacro 與外掛

套件：[`ros_ws/src/amr_description/`](../../ros_ws/src/amr_description/)
檔案：[`urdf/amr.urdf.xacro`](../../ros_ws/src/amr_description/urdf/amr.urdf.xacro)、[`test/test_urdf.py`](../../ros_ws/src/amr_description/test/test_urdf.py)

## 為什麼要做

模擬需要一台車：外形（看得到）、碰撞外型（撞得到、光達掃得到）、質量（物理正確）、可轉動的輪子，加上讓它「動起來」與「感知環境」的 Gazebo 外掛。之後 robot_state_publisher、Gazebo、RViz 都讀同一份模型。

## 套件：ament_cmake

```bash
cd /ros_ws/src
ros2 pkg create --build-type ament_cmake amr_description
rm -rf amr_description/include amr_description/src      # 沒有 C++
mkdir amr_description/urdf && touch amr_description/urdf/.gitkeep
```

```cmake
cmake_minimum_required(VERSION 3.8)
project(amr_description)

find_package(ament_cmake REQUIRED)

install(DIRECTORY urdf
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_urdf test/test_urdf.py)
endif()

ament_package()
```

| 項目 | 說明 |
|---|---|
| `project()` | 宣告名稱，之後用 `${PROJECT_NAME}` |
| 編譯選項 `-Wall -Wextra -Wpedantic` | C++ 用，刪掉 |
| `ament_lint_auto` 區塊 | 依 package.xml 的 `ament_lint*` test_depend 自動加 lint；`set(..._FOUND TRUE)` 是「假裝已找到」來跳過某項 lint。刪掉（與 amr_worlds 移除 flake8 一致） |
| `install(DIRECTORY urdf DESTINATION share/${PROJECT_NAME})` | 安裝整個資料夾；資料夾不存在時安裝階段報錯，所以先放 `.gitkeep`；`--symlink-install` 下一樣是 symlink |
| `ament_add_pytest_test` | **ament_cmake 的測試要明確註冊**（ament_python 會自動找 `test/`） |
| `ament_package()` | **必須最後一行**：自動產生 ament index 卡片、安裝 package.xml、產生給其他套件 `find_package` 的設定——ament_python 要在 setup.py 手寫的事全部自動完成 |

`BUILD_TESTING` 是 CMake 標準開關（colcon 預設開；`--cmake-args -DBUILD_TESTING=OFF` 可關）。

package.xml：`<exec_depend>xacro</exec_depend>`（使用這個模型的人執行時要能展開它）、`<test_depend>ament_cmake_pytest</test_depend>`、`python3-pytest`、`urdfdom`（提供 `check_urdf`）。

**測試數量 = pytest + 1**：`ament_add_pytest_test` 在 CTest 註冊一個測試，它的內容是執行 pytest；兩者各產生一份報告，`colcon test-result` 會加總（25 + 1）。`colcon test-result` 只讀 `build/` 裡現有的報告檔，不檢查是不是最新的。

## 車子的設計

```
側視圖（車頭朝右）                         離地高度   相對 base_link
         laser_link ●                       0.255      +0.175
     ┌──────────────┴──────┐  車頂          0.23       +0.15
     │      base_link       │  車身中心       0.13       +0.05
     │          ●           │  base_link     0.08        0     ← 輪軸高度
     └──────────────────────┘  車底          0.03       −0.05
      ○        ( ◎ )        ○
═══════════════╪═════════════  地面 / base_footprint    0
```

| 零件 | 形狀 | 尺寸 | 質量 |
|---|---|---|---|
| 車身 | box | 0.5 × 0.4 × 0.2 m | 15 kg |
| 驅動輪 ×2 | cylinder | r 0.08、寬 0.04，y = ±0.22 | 1 kg |
| 支撐球 ×2 | sphere | r 0.03，x = ±0.2 | 0.1 kg |
| 光達 | cylinder | r 0.04、高 0.05，x = 0.15 | 0.2 kg |
| IMU | 無外形 | 與 base_link 同位置 | — |

- 驅動輪在車身正中（x = 0）：原地旋轉以車身中心為軸。
- base_link 原點放在輪軸高度：輪子 joint 不需要高度偏移。
- 光達在車頂上方：掃描平面約 0.26 m，掃得到牆、貨架與 1 m 的 box，不被車身擋住。
- 四個接觸點等高：球心 0.03 = 半徑 → 球底剛好在地面。
- 支撐「球」代替真的萬向輪：零摩擦的球在地上滑動，效果相同、物理更穩定。只有 2 個輪子的車前後沒有支撐會倒（需平衡控制），實際搬運車都是「2 驅動輪 + 被動支撐輪」。
- 剛性設計：地板是平的。懸吊（驅動輪加 prismatic joint + 彈簧，讓驅動輪在凹陷處仍壓在地上保持抓地）與不平地形列為之後的獨立 change。

## TF 樹與前綴（做法 1）

```
amr1/base_footprint              ← 根 link，地面投影（REP-105）
└── amr1/base_link               ← fixed，+0.08
    ├── amr1/left_wheel_link     ← continuous（無限旋轉）
    ├── amr1/right_wheel_link    ← continuous
    ├── amr1/front_caster_link   ← fixed
    ├── amr1/rear_caster_link    ← fixed
    ├── amr1/laser_link          ← fixed
    └── amr1/imu_link            ← fixed
```

- **URDF 的 link／joint 名稱不帶前綴**，ROS 側由 robot_state_publisher 的 `frame_prefix: amr1/` 加上。兩邊都加會變成 `amr1/amr1/base_link`（原設計文件裡的矛盾，實作前發現並修正）。
- **Gazebo 側不經過 robot_state_publisher**，所以外掛與感測器的 frame 要用 `robot_id` 明確寫出 `amr1/...`。
- 名稱不含 `/` 也避免 Gazebo 用 link 名組 topic 路徑時出錯。這是 ROS 2 多機器人的標準做法。
- fixed joint 的 TF 永遠不變 → `/tf_static`；continuous joint 隨輪子轉動 → `/tf`。

## xacro

URDF 是純 XML，沒有變數、計算、函式。xacro 加上這些能力，用 `xacro` 指令展開後才是 URDF：

| 功能 | 寫法 |
|---|---|
| 命名空間 | `<robot ... xmlns:xacro="http://www.ros.org/wiki/xacro">`（網址只是識別名，不會連線；沒有它 `xacro:` 標籤不會被處理） |
| 參數（外部傳入） | `<xacro:arg name="robot_id" default="amr1"/>`，取值 `$(arg robot_id)`，執行時 `xacro file robot_id:=amr2` |
| 常數 | `<xacro:property name="wheel_radius" value="0.08"/>`，取值 `${wheel_radius}` |
| 計算 | `${chassis_width / 2 + wheel_width / 2}`——就是 Python 運算式，`pi` 可用 |
| 巨集 | `<xacro:macro name="..." params="a b c:=0">`（`:=` 是預設值），呼叫 `<xacro:名稱 a="..."/>`，展開成巨集內容 |

- 慣例：把 arg 複製成同名 property（`$(arg)` 不能計算，`${}` 可以）。
- **位置由尺寸計算**：改輪子大小，base_link、車身、支撐球、光達高度全部自動跟著變，車身離地間隙與四點貼地都維持。
- 展開後 `<xacro:property>` 完全消失；**XML 註解會保留**。
- 單位（REP-103）：公尺、公斤、弧度。

## link 的三個部分

```xml
<link name="base_link">
  <visual>    <origin/> <geometry/> <material/>   外觀
  <collision> <origin/> <geometry/>               碰撞（物理、光達）
  <inertial>  <origin/> <mass/> <inertia/>        質量與轉動慣量
</link>
```

- **三者各有自己的 `<origin>`，要分別設定**。只移動 visual 會出現「看起來對但撞的位置不對」。
- 形狀：`box`（size 長 寬 高）、`cylinder`（radius、length，軸沿 z）、`sphere`、`mesh`。box 以中心定位。
- `material` 的 `rgba` 每個值 0～1。
- visual 可以用精細 mesh、collision 用簡單形狀以加快物理計算；本車兩者相同。
- `<link name="base_footprint"/>` 是自閉合的空 link：純座標系。**根 link 不能有 inertial**（KDL 不支援）。

### 轉動慣量

質量決定「推動有多難」，轉動慣量決定「轉動有多難」；質量離軸越遠越難轉。慣量是 3×3 對稱矩陣（6 個值），對稱形狀且軸對齊時非對角項為 0。

| 形狀 | 公式 | 本車數值 |
|---|---|---|
| 長方體 | `ixx = m/12·(y²+z²)` 依此類推 | 車身 ixx 0.25、iyy 0.3625、**izz 0.5125**（原地旋轉最難） |
| 圓柱（軸沿 z） | `ixx = iyy = m/12·(3r²+h²)`、`izz = m·r²/2` | 光達 |
| 輪子（軸沿 y） | 繞軸那一項放 **iyy** | iyy 0.0032 |
| 球 | `2/5·m·r²` | 0.000036 |

輪子 link 本身沒有旋轉（只有 visual／collision 用 `rpy` 轉 90°），在 link 座標系裡軸是 y，所以另寫 `wheel_inertial`。慣量太小模擬會抖動甚至「飛走」。

## joint

```xml
<joint name="left_wheel_joint" type="continuous">
  <parent link="base_link"/>
  <child link="left_wheel_link"/>
  <origin xyz="0 0.22 0" rpy="0 0 0"/>   ← 子座標系放在父座標系的哪裡、轉多少
  <axis xyz="0 1 0"/>                    ← 繞 y 軸轉
</joint>
```

- `origin` = 子 link 座標系相對父 link 的位置（xyz 公尺）與旋轉（rpy：roll 繞 x、pitch 繞 y、yaw 繞 z，弧度）——TF 就是從這裡來的。
- 類型：`continuous`（無限旋轉，輪子）、`fixed`（固定）、`revolute`（有角度限制）、`prismatic`（直線滑動，懸吊會用到）。
- 圓柱預設直立（軸沿 z），`rpy="${pi/2} 0 0"` 繞 x 轉 90° 變成橫躺的輪子。
- 巨集參數 `side="1"`／`"-1"` 用一個正負號產生對稱的左右輪、前後球。

## Gazebo 擴充 `<gazebo>`

URDF 不懂模擬；`<gazebo>` 是 Gazebo 專用標籤，轉成 SDF 時搬到對應位置，RViz 等工具忽略它。

- `<gazebo>`（無 reference）：整個模型 → 外掛。
- `<gazebo reference="link">`：某個 link → 感測器、摩擦（`<mu1>0</mu1><mu2>0</mu2>` 讓支撐球零摩擦）。

### 外掛

```xml
<plugin filename="ignition-gazebo-diff-drive-system" name="ignition::gazebo::systems::DiffDrive">
```

- `filename`：共享函式庫檔名（省略 `lib` 與 `.so`）；`name`：裡面的 C++ 類別。
- **Fortress 內建 60 多個系統外掛**，由 apt 套件 `libignition-gazebo6-plugins` 提供（`ros-humble-ros-gz` → `ignition-fortress` → 它），放在 `/usr/lib/x86_64-linux-gnu/ign-gazebo-6/plugins/`。另有帶版本號的 `ignition-gazebo6-*` 檔名。有用的還有 `mecanum-drive`、`ackermann-steering`、`joint-position-controller`、`odometry-publisher`（無誤差的真實位置，可當 SLAM 的標準答案）、`wheel-slip`、`detachable-joint`（取放貨可用）。自寫外掛：繼承 System 類別編成 .so，以 `IGN_GAZEBO_SYSTEM_PLUGIN_PATH` 指定。Gazebo 是外掛式架構（ECS）。
- **確認參數名稱**：`strings libignition-gazebo-diff-drive-system.so` 查外掛實際接受的參數。Fortress 同時有新名稱（`max_linear_velocity`、`max_angular_velocity`…）與已棄用的舊名稱（`max_velocity`）；寫錯的參數會被默默忽略。`topic`、`frame_id` 沒出現在輸出，是因為編譯器把它們與 `odom_topic`、`child_frame_id` 做了字串尾端合併。

### DiffDrive（差速驅動）

```
速度指令 (v, ω) → 輪速：v_L = v − ω·L/2、v_R = v + ω·L/2，轉速 = 輪速 / r
例：v 0.5、ω 1.0、L 0.44 → 左 0.28、右 0.72 m/s（左轉）；只有 ω → 兩輪反轉原地旋轉
反過來：讀兩輪 joint 實際轉角（= 編碼器）→ 推算移動量 → 累加成里程計
```

- `wheel_separation = ${2 * wheel_y}`、`wheel_radius = ${wheel_radius}`：**必須和模型一致**，否則里程計比例錯誤。
- 里程計會累積誤差（打滑時編碼器以為有走），所以之後需要 SLAM 修正。
- topic 是 **Gazebo transport 的 topic**，與 ROS 是兩套獨立系統，由 ros_gz_bridge（task 5.3）轉送：

```
ROS：/amr1/cmd_vel → watchdog → /amr1/cmd_vel_gz ─bridge→ Gazebo DiffDrive
ROS：/amr1/odom、/tf  ←bridge─ Gazebo /amr1/odom、/amr1/tf
```

- 速度指令走 `cmd_vel_gz`：中間經過 watchdog（Fortress 的 DiffDrive 沒有指令逾時，teleop 當掉車子會一直衝）。
- `frame_id amr1/odom` → `child_frame_id amr1/base_footprint`：odom 是開機起點，固定不動。
- 限制：速度 ±1.0 m/s、±1.5 rad/s（超過截斷；min 為負代表倒車／右轉）；加速度 ±2.5 m/s²、±5.0 rad/s²。不加加速度限制速度會瞬間跳變（車身晃動、打滑）；加太小會違反 spec「停送 1 s 內停車」：停車時間 = watchdog 0.5 s + 1.0 / 2.5 = 0.9 s。
- odom 30 Hz（spec ≥ 20 Hz）。

### JointStatePublisher

不指定 `joint_name` 就發布所有可動 joint（兩輪的角度與角速度）到 `/amr1/joint_states`；robot_state_publisher 靠它算出輪子的 TF。

### gpu_lidar

- 用 GPU 從光達位置**渲染深度影像**換算距離 → 需要 world 的 Sensors 系統與 ogre2（所以需要 GPU；ogre1 下全部回報 0.12 m）。
- `update_rate 10`、`always_on`（沒人訂閱也產生）、`visualize`（GUI 顯示光束）。
- 只有 `<horizontal>` → 2D 光達；360 樣本、`resolution 1`（每個 sample 一條光束）。
- 角度 `-π` 到 `π − 2π/360`：若用 `-π`～`+π`，頭尾兩個樣本是同一方向，間隔也變成 360°/359。0 是車頭、逆時針為正。
- 距離 0.12～12 m（太近量不到、太遠回 inf）、解析度 0.01 m；目前沒有雜訊。

### IMU

角速度、線加速度（靜止時量到重力 9.8 m/s²）、姿態；100 Hz（資料小、變化快，高頻才能準確積分）。需要 world 的 Imu 系統——場景產生器早已載入。

## URDF → SDF：fixed joint 合併（lumping）

Gazebo 實際讀 SDF。`ign sdf -p amr.urdf` 轉換後：

```
URDF 8 個 link → SDF 3 個 link：base_footprint、left_wheel_link、right_wheel_link
fixed joint 連接的 base_link、支撐球、laser_link、imu_link 全部併入根 link base_footprint
```

- 原因：不會相對移動的零件當成同一剛體，物理計算更快更穩。
- 合併後：質心重算（`0.0019 0 0.130`，光達在前所以略偏前）、感測器位姿換算（光達 `0.15 0 0.255`）、支撐球碰撞體改名為 `base_footprint_fixed_joint_lump__front_caster_link_collision_1` 且 `mu=0` 保留。
- **`laser_link` 在 Gazebo 裡已不存在 → 感測器必須用 `<ignition_frame_id>` 指定 frame**，否則 ROS 的 TF 樹對不上。

## 測試（25 + 1 個）

| 測試 | 檢查 |
|---|---|
| `check_urdf_passes` | 官方工具驗證 |
| `links_match_design`、`joints_match_design` | 名稱、類型、父子關係完全符合 TF 樹 |
| `names_have_no_prefix` | 名稱沒有 `/`（防止 `amr1/amr1/`） |
| `wheels_rotate_about_y`、`wheels_are_symmetric` | 輪軸方向、左右對稱 |
| `physical_links_have_positive_inertia` | 實體 link 有正的質量與慣量；base_footprint、imu_link 沒有 inertial |
| `four_contact_points_touch_ground` | 沿 TF 樹計算輪底與球底高度都等於 0 |
| `diff_drive_geometry_matches_model` | 外掛輪距／半徑從模型讀出來比對，不是比對寫死的數字 |
| `diff_drive_topics_and_frames`、`diff_drive_limits`（×8）、`joint_state_topic` | 外掛參數 |
| `stop_time_fits_spec` | `0.5 + v_max / a_max < 1.0`——把手算的 spec 限制變成測試 |
| `lidar_parameters`、`imu_parameters` | 類型、topic、frame、頻率、樣本數、角度間隔 1°、量測範圍 |
| `robot_id_changes_all_gazebo_names` | `robot_id:=amr2` 時沒有殘留 amr1 |
| `converts_to_sdf_with_sensors` | `ign sdf -p` 轉換後只剩 3 個 link、感測器 frame 正確、支撐球 mu=0 |

- `@pytest.fixture(scope='module')`：整個檔案共用一份展開結果（呼叫外部程式慢、URDF 只讀不改）。
- `subprocess.run([...], check=True)`：呼叫 `xacro`、`check_urdf`、`ign sdf`，失敗就拋例外。
- 這些測試需要 ROS 工具，不能像 amr_worlds 那樣用 `env -i` 跑。

## 怎麼驗證（2026-10-08 實測）

```bash
xacro /ros_ws/src/amr_description/urdf/amr.urdf.xacro > /tmp/amr.urdf
check_urdf /tmp/amr.urdf                     # root Link: base_footprint，7 個子 link
ign sdf -p /tmp/amr.urdf                      # 3 個 link、感測器帶 ignition_frame_id
cd /ros_ws && colcon build --symlink-install
colcon test && colcon test-result --verbose   # 84 tests（amr_worlds 58 + amr_description 25 + 1）
```

## 面試追問

**Q：URDF 和 SDF 差在哪？**
A：URDF 是 ROS 的機器人描述格式，只描述單一機器人的樹狀結構（link、joint），不能描述世界、不能有封閉迴路，沒有模擬專用的欄位。SDF 是 Gazebo 的格式，能描述整個世界、燈光、物理、感測器、外掛。實務上機器人用 URDF（ROS 工具都讀它），模擬需要的東西用 `<gazebo>` 擴充，Gazebo 載入時轉成 SDF。

**Q：xacro 解決什麼問題？**
A：URDF 沒有變數與函式，對稱零件要複製貼上、尺寸一改到處要重算。xacro 提供參數、常數、運算式、巨集，展開後才是 URDF。

**Q：base_footprint 和 base_link 差在哪？**
A：REP-105：base_footprint 是車子在地面的投影，2D 導航在這個平面計算；base_link 固定在車身上，是零件的參考點。另一個實務理由是 KDL 不接受有慣量的根 link，所以根 link 留空。

**Q：多台機器人怎麼避免 TF 衝突？**
A：每台車的 frame 加 namespace 前綴（amr1/、amr2/）。URDF 不帶前綴，robot_state_publisher 用 `frame_prefix` 加；Gazebo 側外掛的 frame 參數用 robot_id 明確填。兩邊都加會變成雙重前綴。

**Q：差速驅動的運動學？**
A：v_L = v − ωL/2、v_R = v + ωL/2，輪轉速 = 輪速 / r；反過來由編碼器推算里程計。輪距與輪半徑必須與實際一致，否則里程計比例錯誤。里程計會累積誤差，需要 SLAM 或其他感測器修正。

**Q：為什麼模擬的光達需要 GPU？**
A：gpu_lidar 是從光達位置渲染深度影像換算距離，依賴渲染引擎（ogre2）。沒有 GPU 會退回軟體渲染、變慢，用 ogre1 則量測失效。

**Q：URDF 轉 SDF 時發生了什麼？會有什麼問題？**
A：fixed joint 連接的 link 會被合併進父 link（lumping），模型只剩可動的部分；質心與感測器位姿會自動換算。問題是原本的 link 名稱不存在了，感測器訊息的 frame 要用 `ignition_frame_id` 明確指定。

**Q：轉動慣量隨便填會怎樣？**
A：太小模擬不穩定（抖動、飛走），0 可能讓物理引擎出錯。要用形狀公式計算；URDF 不會自動算。

**Q：為什麼要加加速度限制？怎麼決定數值？**
A：沒有限制速度會瞬間跳變，不真實也會造成車身晃動、打滑。數值受 spec 限制：停送指令後 1 s 內停車 = watchdog 0.5 s + 減速時間，所以減速度至少 2 m/s²，選 2.5 留餘裕，並寫成測試。

## 踩坑紀錄

- **設計文件互相矛盾**：tasks 寫 URDF 名稱帶前綴、design 寫 robot_state_publisher 用 frame_prefix——兩者同時做會變成 `amr1/amr1/base_link`。實作前發現，改成做法 1。
- **車身質心放錯位置**：`<inertial>` 沒寫 `<origin>` 時質心在 link 原點（輪軸高度），但車身中心高 5 cm → 模擬的車比實際穩。加 `com_z` 參數修正。visual、collision、inertial 三個 origin 要分別設定。
- **手算數字寫錯**：設計表格寫光達 z = +0.205，xacro 用公式算出的是 +0.175。公式計算比手寫數字可靠。
- **xacro 展開保留 XML 註解**：測試用字串搜尋 `amr1` 時被註解裡的文字誤判；先用 ElementTree 解析（會丟掉註解）再檢查。
- **`.vscode/settings.json` 被 commit**：VS Code 的 CMake Tools 自動產生，內容是本機絕對路徑。加進 `.gitignore`、`git rm --cached`（保留本機檔案）、`git commit --amend`（只能用在還沒 push 的 commit）。教訓：commit 前先看 `git status`。
- **`colcon test-result` 顯示舊報告**：amr_worlds 的 `pytest.xml` 還是 task 3.1 時的 0 tests；它只讀現有檔案。重新跑 `colcon test` 才更新。
