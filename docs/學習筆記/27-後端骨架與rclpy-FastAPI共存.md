# 27 後端骨架與 rclpy／FastAPI 共存

檔案：[`amr_server/`](../../ros_ws/src/amr_server/)（`map_image.py`、`geometry.py`、`state.py`、`bridge.py`、`main.py`）、[`launch/server.launch.xml`](../../ros_ws/src/amr_server/launch/server.launch.xml)

OpenSpec change `add-web-dispatch`，task 2.1（套件與純函式）、3.2（進入點與 launch）。

## 為什麼要做

後端同時要做兩件事：當 **ROS 節點**（訂閱地圖、查 TF、送 action），也當 **HTTP 伺服器**（給瀏覽器 REST 與 WebSocket）。兩邊的程式風格不同：ROS 是回呼（executor 呼叫你），FastAPI 是 asyncio（事件迴圈）。先把結構切乾淨，才不會變成一團難測的程式。

## 做了什麼

### 1. 套件：ament_python

和 `amr_navigation` 一樣的 ament_python 結構（`package.xml`、`setup.py`、`setup.cfg`、`resource/`），所以 `colcon build`／`colcon test` 照常，console script `server` 之後由 launch 啟動。

package.xml 只列 ROS 套件與 apt 的 Python 套件（`python3-numpy`、`python3-pil`）。**FastAPI、uvicorn 不列**：rosdep 沒有對應的鍵，寫了反而讓 `rosdep install` 失敗；它們由映像的 pip 安裝（筆記 26）。

### 2. 模組邊界

```
map_image.py   佔據格 → PNG（純函式）
geometry.py    四元數 ↔ yaw、路徑降取樣、是否在地圖範圍內（純函式）
state.py       資料型別：Pose2D、MapInfo、RobotState、狀態字串
bridge.py      RobotBridge 介面 + 兩個例外（NavigationUnavailable、NoActiveGoal）
ros_bridge.py  用 rclpy 實作 RobotBridge（task 3.1）
api.py         FastAPI，只認識 RobotBridge 介面（task 2.2）
main.py        把 ROS 和 HTTP 接起來（task 3.2）
```

關鍵是 **`bridge.py` 的介面**（Python 的 `typing.Protocol`）：

```python
class RobotBridge(Protocol):
    def state(self) -> RobotState: ...
    def map_info(self) -> Optional[MapInfo]: ...
    def map_png(self) -> Optional[bytes]: ...
    def send_goal(self, x, y, yaw) -> None: ...      # 導航沒執行 → NavigationUnavailable
    def cancel(self) -> None: ...                    # 沒有目標 → NoActiveGoal
    def set_initial_pose(self, x, y, yaw) -> None: ...
```

`api.py` 只呼叫這些方法。正式執行時傳入 rclpy 版本；測試時傳入一個假的類別（只要有同樣的方法，不用繼承——這就是 Protocol 的「結構型別」），API 的測試完全不需要啟動 ROS。這種寫法叫**依賴反轉**：高層（API）不依賴低層細節（rclpy），兩者都依賴介面。

### 3. 佔據格 → PNG

```python
pixels = np.full(grid.shape, UNKNOWN, dtype=np.uint8)        # 先全部灰（205）
pixels[(grid >= 0) & (grid <= 25)] = FREE                    # 白（254）
pixels[grid >= 65] = OCCUPIED                                # 黑（0）
Image.fromarray(np.flipud(pixels), mode='L').save(buffer, format='PNG')
```

- 門檻和 map_saver 的 trinary 模式一樣（空曠 0.25、佔據 0.65），網頁看到的就是存圖的 `.pgm`。
- **`np.flipud`（上下翻轉）**：OccupancyGrid 第 0 列是地圖 y 最小（下方），圖片第 0 列是最上面。這是筆記 17 提過的「圖片 row 由上往下、地圖 y 由下往上」。
- 用 numpy 的布林遮罩一次處理整張圖（40 萬格），比 Python 迴圈快上百倍。
- 為什麼轉 PNG 不直接送數字陣列：PNG 有壓縮（大片同色壓得很小），瀏覽器原生就能顯示。

### 4. 路徑降取樣

Nav2 的 `/amr1/plan` 每 5 cm 一點，20 m 的路徑就 400 點，每 0.1 秒推一次太浪費。每隔約 0.1 m 留一點、起點終點一定留，畫出來看不出差別。

### 5. 一個程序、兩個執行緒（`main.py`）

```python
rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
node = FleetNode()                                   # 讀參數 robots，每台車一個 bridge
executor = SingleThreadedExecutor(); executor.add_node(node)
spin_thread = threading.Thread(target=executor.spin, daemon=True); spin_thread.start()   # ROS：背景執行緒
try:
    uvicorn.run(create_app(node.bridges, web_dir), host=host, port=port,
                timeout_graceful_shutdown=1)         # HTTP：主執行緒（阻塞到收到 Ctrl+C）
except KeyboardInterrupt:
    pass
finally:
    executor.shutdown()
    spin_thread.join(timeout=2.0)                    # 一定要等 spin 執行緒結束
    node.destroy_node()
    rclpy.shutdown()
```

- **為什麼 uvicorn 在主執行緒**：Python 的訊號（Ctrl+C）只會送到主執行緒，uvicorn 要在主執行緒才能自己處理 SIGINT、優雅關閉連線。
- **`SignalHandlerOptions.NO`**：rclpy 預設也會裝 SIGINT 處理，收到就把 ROS context 關掉。兩邊搶訊號的話，可能 ROS 先關、HTTP 還在服務卻沒有資料。改成只有 uvicorn 處理，它結束後我們再依序關掉 ROS。
- **`timeout_graceful_shutdown=1`**：WebSocket 迴圈不會自己結束，關閉時最多等 1 秒就強制斷線。
- 兩邊怎麼溝通：見筆記 28（鎖、`executor.create_task`）。

### 6. launch

```xml
<node pkg="amr_server" exec="server" name="amr_server" output="screen"
      ros_args="-p use_sim_time:=$(var use_sim_time)">
  <param name="robots" value="$(var robots)" type="str"/>
  <param name="host" value="$(var host)" type="str"/>
  <param name="port" value="$(var port)"/>
  <param name="web_dir" value="$(var web_dir)" type="str"/>
</node>
```

- `type="str"`：讓 `amr1` 這種值確定是字串（launch 會自己猜型別，例如 `0001` 可能被當成整數）。
- `host` 預設 `127.0.0.1`：只有本機能連。目前沒有登入驗證，開放給其他電腦（`host:=0.0.0.0`）就是任何人都能派車。
- `use_sim_time` 照子專案 2 的做法用 `ros_args`。

## 怎麼驗證（2026-10-08 實測）

- 先寫測試、確認因模組不存在而失敗，再實作：`pytest` 21 項通過（顏色、7 個門檻值、上下翻轉、大小不符報錯、yaw 來回轉換、降取樣、地圖範圍邊界、套件邊界）。
- `colcon build --packages-select amr_server` 成功、`ros2 pkg prefix amr_server` 找得到。
- launch 參數測試 3 項（參數與預設值、每個參數都傳給節點、use_sim_time 用 ros_args）。
- 臨時容器（獨立 domain、埠 8100）跑世界＋車子系統（`mode:=navigation`）＋後端：
  - `GET /api/robots`、`/map`（與 `warehouse_small.yaml` 一致：0.05、origin (−0.13, −0.11)）、未建置網頁時 `/` 顯示說明。
  - WebSocket 每秒約 11 則。`POST initial_pose (1, 1, 0)` 後位置 (1.01, 1.03)。
  - Nav2 還在啟動時派車 → 503「導航還在啟動」；啟動後派到 (10, 1) → `succeeded`，Gazebo 真實位置 (9.84, 1.03)（差 0.17 m），WebSocket 位置和真實位置差 0.03 m。
  - 派到箱子 (7, 4) → `failed`「Nav2 放棄」；導航中取消 → `canceled`；再取消 → 409；x=999 → 422。
  - WebSocket 連線中以 ros2 launch 停止：0.5 秒結束、`process has finished cleanly`，用戶端收到連線關閉。

## 面試追問

**Q：怎麼讓一個依賴 ROS 的 web 後端好測試？**
A：把 ROS 的部分藏在一個介面後面（這裡的 RobotBridge），web 層只依賴介面。測 web 層時換成假的實作；ROS 的部分另外寫整合測試。純計算（圖片轉換、幾何）抽成沒有副作用的函式，單元測試最容易。

**Q：Protocol 和抽象基底類別（ABC）有什麼不同？**
A：ABC 要求實作類別明確繼承；Protocol 是結構型別，只要方法簽名對得上就算符合，不用繼承。假物件寫起來更輕，型別檢查器（mypy）也能檢查。

## 踩坑紀錄

- **停止要 5 秒、而且崩潰（`terminate called without an active exception`，exit −6）**：`finally` 裡 `executor.shutdown()` 後沒等 spin 執行緒結束就讓程序退出；daemon 執行緒還在 rclpy 的 C++ 程式碼裡，直譯器結束時 C++ 的 `std::terminate` 被呼叫。ros2 launch 等不到程序結束，5 秒後才送 SIGTERM。加上 `spin_thread.join(timeout=2.0)` 後：0.3 秒、結束碼 0。教訓：daemon 執行緒「程序結束時自動被殺」對純 Python 沒事，對跑著 C 擴充的執行緒很危險。

- **pip 裝的 anyio 弄壞了整個映像的 pytest**：anyio 會自動註冊 pytest 外掛（`pytest11` entry point），外掛 import `_pytest.scope`，那是 pytest 7 才有的；apt 的 pytest 是 6.2，結果**任何** pytest 一啟動就崩潰——連既有套件的 `colcon test` 都會壞。解法：Dockerfile 加 `ENV PYTEST_ADDOPTS="-p no:anyio"` 停用這個外掛（我們用不到）。教訓：pip 裝套件可能帶進「外掛」這種隱形的副作用，裝完要跑一次既有的測試。
