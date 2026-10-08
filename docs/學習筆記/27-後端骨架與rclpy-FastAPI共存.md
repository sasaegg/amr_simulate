# 27 後端骨架與 rclpy／FastAPI 共存

檔案：[`amr_server/`](../../ros_ws/src/amr_server/)（`map_image.py`、`geometry.py`、`state.py`、`bridge.py`）

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

## 怎麼驗證（2026-10-08 實測）

- 先寫測試、確認因模組不存在而失敗，再實作：`pytest` 21 項通過（顏色、7 個門檻值、上下翻轉、大小不符報錯、yaw 來回轉換、降取樣、地圖範圍邊界、套件邊界）。
- `colcon build --packages-select amr_server` 成功、`ros2 pkg prefix amr_server` 找得到。

## 面試追問

**Q：怎麼讓一個依賴 ROS 的 web 後端好測試？**
A：把 ROS 的部分藏在一個介面後面（這裡的 RobotBridge），web 層只依賴介面。測 web 層時換成假的實作；ROS 的部分另外寫整合測試。純計算（圖片轉換、幾何）抽成沒有副作用的函式，單元測試最容易。

**Q：Protocol 和抽象基底類別（ABC）有什麼不同？**
A：ABC 要求實作類別明確繼承；Protocol 是結構型別，只要方法簽名對得上就算符合，不用繼承。假物件寫起來更輕，型別檢查器（mypy）也能檢查。

## 踩坑紀錄

- **pip 裝的 anyio 弄壞了整個映像的 pytest**：anyio 會自動註冊 pytest 外掛（`pytest11` entry point），外掛 import `_pytest.scope`，那是 pytest 7 才有的；apt 的 pytest 是 6.2，結果**任何** pytest 一啟動就崩潰——連既有套件的 `colcon test` 都會壞。解法：Dockerfile 加 `ENV PYTEST_ADDOPTS="-p no:anyio"` 停用這個外掛（我們用不到）。教訓：pip 裝套件可能帶進「外掛」這種隱形的副作用，裝完要跑一次既有的測試。
