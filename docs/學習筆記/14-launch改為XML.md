# 14 launch 改為 XML

檔案：[`world.launch.xml`](../../ros_ws/src/amr_worlds/launch/world.launch.xml)、[`robot.launch.xml`](../../ros_ws/src/amr_bringup/launch/robot.launch.xml)、[`sim_hardware.launch.xml`](../../ros_ws/src/amr_hw_sim/launch/sim_hardware.launch.xml)

## 為什麼要做

原本三個 launch 是 Python 寫的。Python launch 有 `OpaqueFunction`、`LaunchConfiguration(...).perform(context)` 這類延遲求值的概念，ROS 1 出身的人不容易看懂。ROS 2 也支援 XML launch，寫法和 ROS 1 幾乎一樣，讀起來就是「宣告參數 → 啟動哪些程式」。

代價：XML 不能寫一般程式邏輯，**不能讀自訂的 YAML 設定檔**。所以原本的 `world.yaml`／`robot.yaml` 和「套件預設 ← 設定檔 ← 命令列」三層合併一併移除，設定全部改成 launch 參數（ROS 1 也是這樣做）。

## ROS 1 → ROS 2 XML 對照

| ROS 1 | ROS 2 XML | 說明 |
|---|---|---|
| `<arg name="x" default="0"/>` | 相同 | 沒有 `default` = 必填 |
| `$(arg x)` | `$(var x)` | 改名 |
| `$(find pkg)` | `$(find-pkg-share pkg)` | 找的是 **install** 下的 share 目錄，不是 src |
| `<node pkg type name>` | `<node pkg exec name>` | `type` 改名為 `exec` |
| `ns="..."` | `namespace="..."` | |
| `<param name value/>` | 相同 | 寫在 `<node>` 裡面 |
| `<remap from to/>` | 相同 | |
| `<include file>` + `<arg>` | 相同 | |
| `<group if="...">` | 相同 | |
| `$(eval arg('x') == 'sim')` | `$(equals $(var x) sim)` | 也有 `not-equals`、`and`、`or`、`not` |
| `<arg name="a" value="..."/>`（算出來的值） | `<let name="a" value="..."/>` | |
| 無 | `<executable cmd="..."/>` | 執行非 ROS 程式（例如 `ign gazebo`） |
| `required="true"` | `on_exit="shutdown"` | 這個程式結束時，整個 launch 跟著結束 |
| 無 | `<shutdown reason="..."/>` | 主動結束 launch |
| 自動啟動 roscore | 不需要 | ROS 2 沒有 master，節點透過 DDS 互相發現 |

列出某個 launch 的所有參數：`ros2 launch amr_bringup robot.launch.xml --show-args`。

## 做了什麼

### world.launch.xml

```xml
<arg name="world" default="warehouse_small"/>
<arg name="headless" default="false"/>
<let name="world_file" value="$(find-pkg-share amr_worlds)/worlds/$(var world).sdf"/>

<executable cmd="ign gazebo -r $(var world_file)" on_exit="shutdown" unless="$(var headless)"/>
<executable cmd="ign gazebo -r -s --headless-rendering $(var world_file)" on_exit="shutdown" if="$(var headless)"/>

<node pkg="ros_gz_bridge" exec="parameter_bridge" name="clock_bridge"
      args="/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock"/>
```

- headless 有兩種指令，XML 不能用 if 去改指令內容，所以寫兩行，用 `if`／`unless` 二選一。`headless` 不是 true／false 時，launch 會自己報錯（`invalid condition expression`）。
- `on_exit="shutdown"`：Gazebo 結束時，整個 launch 跟著結束（直接關掉視窗、world 檔不存在都算）。少了這個，Gazebo 掛掉後 clock bridge 還會一直跑。

### robot.launch.xml

```xml
<arg name="hardware" description="必填：sim 或 real"/>      <!-- 沒有 default = 必填 -->
<let name="is_sim"  value="$(equals $(var hardware) sim)"/>
<let name="is_real" value="$(equals $(var hardware) real)"/>

<group if="$(var is_real)">  <log .../> <shutdown .../> </group>
<group unless="$(or $(var is_sim) $(var is_real))">  <log .../> <shutdown .../> </group>

<group if="$(var is_sim)">
  <node pkg="robot_state_publisher" ...>
    <param name="robot_description" type="str"
           value="$(command 'xacro $(find-pkg-share amr_description)/urdf/amr.urdf.xacro robot_id:=$(var robot_id)')"/>
    <param name="use_sim_time" value="$(var is_sim)"/>
  </node>
  <include file="$(find-pkg-share amr_hw_sim)/launch/sim_hardware.launch.xml">
    <arg name="x" value="$(var x)"/> ...
  </include>
</group>
```

- **`$(command '...')`**：執行指令，把輸出當成值，等於 ROS 1 的 `$(command xacro ...)`。
- **`type="str"`**：URDF 內容是一大段 XML 文字，告訴 launch 直接當字串，不要猜型別。
- **`use_sim_time` 直接用 `$(var is_sim)`**：模擬模式才用模擬時間，不另外開一個參數，避免兩個設定互相矛盾。
- **`$(find-pkg-share amr_hw_sim)` 放在 `if` 條件內**：條件不成立就不會去找這個套件，所以真車上沒安裝 `amr_hw_sim` 也沒問題。`amr_bringup` 的 package.xml 也不宣告它。

### sim_hardware.launch.xml 的 bridge

原本用 `bridge.py` 產生 YAML，改成直接寫在 `args`：

```xml
<node pkg="ros_gz_bridge" exec="parameter_bridge" name="base_bridge" namespace="$(var robot_id)"
      args="/$(var robot_id)/cmd_vel_gz@geometry_msgs/msg/Twist]ignition.msgs.Twist
            /$(var robot_id)/odom@nav_msgs/msg/Odometry[ignition.msgs.Odometry
            /$(var robot_id)/tf@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V ...">
  <remap from="/$(var robot_id)/tf" to="/tf"/>
</node>
```

- 格式是 `<topic>@<ROS 型別><方向><Gazebo 型別>`：`[` 表示 Gazebo → ROS，`]` 表示 ROS → Gazebo，`@` 表示雙向。
- args 寫法的 ROS 端和 Gazebo 端 topic 名稱相同。`/amr1/tf` 要合併到全域 `/tf`，所以再加一條 `<remap>`。
- 測試 [`test_bridge.py`](../../ros_ws/src/amr_hw_sim/test/test_bridge.py) 直接解析這個 XML，檢查 topic、型別、方向，以及 Gazebo 端 topic 和 xacro 設定是否一致。

### 其他改動

- 刪除 `world.yaml`、`robot.yaml`、`world_config.py`、`robot_config.py`、`bridge.py` 和它們的測試。
- compose 拿掉 `./config:/config` 掛載，`config/` 只剩 `ros.env`（由主機端的 `env_file` 讀取）。
- `setup.py` 改為安裝 `launch/*.launch.xml`；package.xml 加上 `launch_xml`。
- 冒煙測試仍然是 Python（launch_testing 只支援 Python），用 `AnyLaunchDescriptionSource` include XML，它會依副檔名判斷格式。

## 怎麼驗證（2026-10-08 實測）

```bash
ros2 launch amr_bringup robot.launch.xml                   # missing required argument 'hardware'，結束碼 1
ros2 launch amr_bringup robot.launch.xml hardware:=real    # 尚未提供真車驅動，沒有啟動任何節點
ros2 launch amr_bringup robot.launch.xml hardware:=foo     # hardware 必須是 sim 或 real，收到 'foo'
ros2 launch amr_worlds world.launch.xml world:=nope headless:=true   # Gazebo 找不到檔案 → launch 自己結束
colcon test && colcon test-result --all                     # 117 tests, 0 failures；冒煙測試 9 項通過
```

## 面試追問

**Q：ROS 2 的 launch 可以用哪些格式？怎麼選？**
A：Python、XML、YAML 三種。XML／YAML 是宣告式的，好讀，和 ROS 1 接近；Python 能寫任意邏輯，例如讀設定檔、算路徑、動態決定要啟動什麼。一般的做法是能用 XML 就用 XML，需要邏輯時才用 Python，兩種可以互相 include。

**Q：從 ROS 1 的 launch 改到 ROS 2 XML，要注意什麼？**
A：`type` 改成 `exec`、`$(arg)` 改成 `$(var)`、`$(find)` 改成 `$(find-pkg-share)`（找的是 install 目錄，新增檔案要 build），`ns` 改成 `namespace`；`required` 改成 `on_exit="shutdown"`；不需要 roscore。

**Q：XML launch 怎麼做條件判斷？**
A：用 `if`／`unless` 屬性，搭配 `$(equals)`、`$(not-equals)`、`$(and)`、`$(or)`、`$(not)` 這些替換。可以加在 `<group>`、`<node>`、`<include>`、`<executable>` 上。

**Q：怎麼讓參數變成必填？**
A：`<arg>` 不給 `default`。沒有傳入時，launch 會以「missing required argument」結束。

## 踩坑紀錄

- **XML 註解裡不能出現 `--`**：XML 規格禁止，寫 `<!-- 加上 --headless-rendering -->` 會解析失敗。註解裡要改寫成別的字。
- **Humble 的 `XMLLaunchDescriptionSource` 在 `launch_xml` 套件裡**，不在 `launch.launch_description_sources`。改用 `AnyLaunchDescriptionSource`，它會依副檔名自動判斷格式。
- **`<shutdown>` 之前的節點還是會先啟動**：一開始 `hardware:=real` 時，robot_state_publisher 會先啟動再被關掉，還印出一行容易誤會的 `process has died`。改成把節點放進 `<group if="$(var is_sim)">`。
- **`<shutdown>` 的結束碼是 0**：只有「缺少必填參數」是非零。所以測試改成檢查訊息，不檢查結束碼。
- **Gazebo 掛了，launch 卻沒結束**：world 檔不存在時 Gazebo 結束了，clock bridge 卻還在跑。加上 `on_exit="shutdown"` 解決。
- **使用者的 Gazebo 還開著時跑冒煙測試**：兩個世界會互相干擾（`/clock` 會有兩個發布者）。可以設定不同的 `ROS_DOMAIN_ID`（隔離 ROS 2）和 `IGN_PARTITION`（隔離 Gazebo transport），兩邊就完全分開。
