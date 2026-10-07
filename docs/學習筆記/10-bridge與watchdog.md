# 10 bridge 與 watchdog

套件：[`ros_ws/src/amr_hw_sim/`](../../ros_ws/src/amr_hw_sim/)（task 5.1–5.3 時寫在 `amr_bringup`，5.5 架構調整後搬到這裡）
檔案：[`watchdog.py`](../../ros_ws/src/amr_hw_sim/amr_hw_sim/watchdog.py)、[`cmd_vel_watchdog.py`](../../ros_ws/src/amr_hw_sim/amr_hw_sim/cmd_vel_watchdog.py)、[`bridge.py`](../../ros_ws/src/amr_hw_sim/amr_hw_sim/bridge.py)

## 為什麼要做

- **watchdog**：Gazebo Fortress 的 DiffDrive 沒有指令逾時；teleop 或導航程式當掉時，車子會照最後一筆指令一直走。真車的馬達驅動板通常自己有逾時，模擬要補上這個「假驅動板」功能（deadman 設計）。
- **bridge**：ROS 2 與 Gazebo transport 是兩套獨立的通訊系統，名稱相同也不會互通，需要 ros_gz_bridge 轉送並轉換訊息型別。

## watchdog

### 判斷邏輯與節點分開

```
Watchdog 類別（純邏輯）     ← 只回答「現在該不該停車」，時間由外部傳入
   ↑ 呼叫
cmd_vel_watchdog 節點        ← 只負責收發訊息、計時器
```

時間由外部傳入：測試寫 `dog.check(0.5)` 就等於過了 0.5 秒，不用真的等、不用啟動 ROS，9 個測試瞬間跑完、結果穩定（與產生器把 validate／generate 寫成純函式同一個道理）。

```python
class Watchdog:
    def __init__(self, timeout):        # timeout <= 0 → ValueError
        self._last_command = None
        self._stopped = True            # 還沒收過指令 = 已停車，不送停車指令
    def on_command(self, now):          # 收到指令：記時間、開始計時
        self._last_command = now
        self._stopped = False
    def check(self, now):               # 計時器定期呼叫，True = 現在送一次零速度
        if self._stopped: return False
        if now < self._last_command:    # 時間倒退（Gazebo reset）：重新計時
            self._last_command = now; return False
        if now - self._last_command >= self._timeout:
            self._stopped = True        # 只送一次
            return True
        return False
```

一個 `_stopped` 旗標同時處理「啟動時不送」與「逾時後只送一次」。

**為什麼只送一次**：spec 要求停止後不持續送。若每次檢查都送零速度，其他來源（之後的 Nav2）的指令會一直被蓋掉，車子動不了。

### 9 個測試

未收指令不停車、逾時內不停、剛好 0.5 s 送一次且之後不再送、連續指令不停、停車後新指令重新計時、計時器延遲仍只送一次、時間倒退不誤判、timeout ≤ 0 報錯。

pytest 的 **ERROR 與 FAILED**：fixture 準備階段就出錯（例如空殼的 `__init__` 拋 `NotImplementedError`）是 ERROR，測試函式根本沒跑；測試本身的 assert 不成立是 FAILED。看到 ERROR 先檢查 fixture 與環境。

### rclpy 節點

```python
class CmdVelWatchdog(Node):                     # 繼承 Node：「是一個」ROS 節點
    def __init__(self):
        super().__init__('cmd_vel_watchdog')    # 先初始化父類別：向 ROS 註冊節點、套用 namespace
        timeout = self.declare_parameter('timeout', 0.5).value
        self._publisher = self.create_publisher(Twist, 'cmd_vel_gz', 10)
        self.create_subscription(Twist, 'cmd_vel', self._on_command, 10)
        self.create_timer(1.0 / check_rate, self._on_timer)
```

- **rclpy** = ROS Client Library for Python。架構：`rclpy / rclcpp → rcl（C 核心）→ rmw（middleware 抽象）→ Fast DDS / Cyclone DDS`。Python 與 C++ 節點共用同一個核心所以能互通；換 DDS 只要設 `RMW_IMPLEMENTATION`。
- **`super().__init__(名稱)` 必須先呼叫**：子類別定義了 `__init__` 時父類別的不會自動執行；Node 的初始化才真的建立節點，之後才能 `create_*`。
- **相對 topic 名稱**（不以 `/` 開頭）會加上節點的 namespace：以 `-r __ns:=/amr1` 啟動就是 `/amr1/cmd_vel`——同一份程式服務不同的車。
- `declare_parameter` 宣告參數與預設值，可用 `-p timeout:=1.0` 覆寫。
- `get_clock().now()`：`use_sim_time` 為 true 時是 `/clock` 的模擬時間。
- **`rclpy.spin()`**：事件迴圈。`create_subscription`／`create_timer` 只是登記 callback，spin 才去檢查事件並呼叫。預設單執行緒，callback 依序執行，所以共用狀態不需要鎖（事件驅動模型）。
- 結束時 `except (KeyboardInterrupt, ExternalShutdownException)`、`destroy_node()`、`rclpy.try_shutdown()`：Ctrl+C／SIGTERM 正常收尾不印 traceback。
- 繼承 vs 組合：正式節點繼承 `Node`（狀態與 callback 在同一個類別）；短腳本可直接 `node = Node('x')`。

### 結束時讓車停下（task 5.8 實測發現）

車子系統停止時，如果車子正在移動，Gazebo 裡的車會一直開（DiffDrive 執行最後一筆指令，watchdog 已經停了）。在結束前送零速度，但 **launch 結束時同時對所有節點送 SIGINT，ROS→Gazebo 的 bridge 常比 watchdog 先結束**，經 bridge 送不到（實測車子仍以 0.58 m/s 前進）。所以改為直接用 `ign topic -t /amr1/cmd_vel_gz -m ignition.msgs.Twist -p ''` 送進 Gazebo——watchdog 本身就是模擬側的假驅動板，直接跟 Gazebo 溝通是合理的。

## bridge

### parameter_bridge 的 YAML 設定

```yaml
- ros_topic_name: /amr1/odom
  gz_topic_name: /amr1/odom
  ros_type_name: nav_msgs/msg/Odometry
  gz_type_name: ignition.msgs.Odometry      # Fortress 是 ignition.msgs.*，Garden 之後是 gz.msgs.*
  direction: GZ_TO_ROS                       # GZ_TO_ROS／ROS_TO_GZ／BIDIRECTIONAL
```

`parameter_bridge --ros-args -p config_file:=<路徑>`——只吃檔案路徑，所以由 `write_bridge_config` 寫到暫存資料夾。命令列寫法 `/topic@ros_type[gz_type`（`[` gz→ros、`]` ros→gz、`@` 雙向）只適合簡單情況，YAML 才能讓兩邊名稱不同（例如 `/amr1/tf` → `/tf`）。

確認支援的方式：`strings /opt/ros/humble/lib/libros_gz_bridge.so` 找 `config_file`、`gz_topic_name` 等鍵與型別名稱。

### 依元件拆分（架構調整後）

| 元件 | ROS topic | 方向 | Gazebo topic | 型別 |
|---|---|---|---|---|
| 虛擬底盤 | `/amr1/cmd_vel_gz` | ▶ | `/amr1/cmd_vel_gz` | Twist |
| | `/amr1/odom` | ◀ | `/amr1/odom` | Odometry |
| | **`/tf`** | ◀ | **`/amr1/tf`** | TFMessage ↔ Pose_V |
| | `/amr1/joint_states` | ◀ | `/amr1/joint_states` | JointState ↔ Model |
| 虛擬光達 | `/amr1/scan` | ◀ | `/amr1/scan` | LaserScan |
| 虛擬 IMU | `/amr1/imu` | ◀ | `/amr1/imu` | Imu ↔ IMU |
| 世界（amr_worlds） | `/clock` | ◀ | `/clock` | Clock |

- 只有經過 watchdog 的速度指令是 ROS → Gazebo。
- `/tf` 是唯一兩邊名稱不同的：Gazebo 端每台車各自一個，ROS 端合併到全域 `/tf`，靠 frame 前綴區分。
- 每個元件一個 bridge 節點，對應真車上的各個驅動，之後監控可個別處理。
- `/clock` 屬於世界：不論幾台車只有一個發布者，放在 world launch，不放在車輛的虛擬驅動裡。
- gpu_lidar 另外自動發布 `/amr1/scan/points`（點雲），沒有轉送。

### 測試

各元件的 topic／型別／方向符合設計、每筆只有五個鍵、只有 cmd_vel 進 Gazebo、虛擬驅動不轉送 `/clock`、robot_id 套用到所有名稱、拒絕不合法 robot_id、寫出的 YAML 讀回相同、**bridge 的 Gazebo 端 topic 與 xacro 設定完全一致**（需要 xacro，無 ROS 時以 `skipif` 略過——報告顯示 skipped 與原因，不是失敗）。

## 怎麼驗證（實測）

- watchdog：以 10 Hz 送 1 秒前進後停送 → 轉發 10 筆、約 0.5 s 後 1 筆停車；整合後停送到停車 0.86 s（watchdog 0.5 + 減速 1.0／2.5）。
- bridge：scan 9.97 Hz、odom 29.2 Hz、imu 99.3 Hz；scan frame `amr1/laser_link`、`angle_increment` 0.01745 rad（1°）。
- 直接送 `cmd_vel_gz`（跳過 watchdog）2 秒後停送，車子繼續前進——親眼證明 DiffDrive 沒有逾時。
- `joint_states` 為 1000 Hz：Fortress 的 JointStatePublisher 每個物理步（1 ms）發布一次，沒有頻率參數。

## 面試追問

**Q：為什麼要 watchdog？為什麼放在模擬側？**
A：deadman 安全機制：上游程式當掉時車子要自己停。真車的馬達驅動板通常內建逾時；Gazebo 的 DiffDrive 沒有，watchdog 補的是「假驅動板」的功能，所以屬於模擬側；`cmd_vel_gz` 這個名稱只存在於模擬側，車子系統只看到標準的 `cmd_vel`。

**Q：怎麼測試跟時間有關的邏輯？**
A：把判斷寫成純類別、時間由外部傳入，測試直接給時間值，不用 sleep、不用 ROS，快又穩定。節點只是把 `get_clock().now()` 傳進去。

**Q：rclpy 的 spin 在做什麼？callback 會同時執行嗎？**
A：spin 是事件迴圈，檢查訊息與計時器並呼叫登記的 callback。預設單執行緒 executor，callback 依序執行；要平行可用 MultiThreadedExecutor 搭配 callback group。

**Q：ROS 2 和 Gazebo 的 topic 為什麼要 bridge？**
A：Gazebo 用自己的 transport（ignition transport），不是 DDS，兩邊訊息型別也不同。ros_gz_bridge 在兩邊各開一個端點，轉送並逐欄位轉換型別。

**Q：多台車時 /clock 怎麼處理？**
A：時間屬於世界，只由世界轉送一次；每台車的虛擬驅動都轉送會讓 ROS 收到多份時間。

## 踩坑紀錄

- 空殼的 `__init__` 拋 `NotImplementedError` → 用到 fixture 的 7 個測試是 ERROR 而非 FAILED。
- 停止車子系統後車子繼續跑：bridge 比 watchdog 先結束，零速度送不到 Gazebo → 改用 `ign topic` 直接送。
