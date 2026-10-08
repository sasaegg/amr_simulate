# 32 網頁派車的端到端冒煙測試與 README

檔案：[`amr_hw_sim/test/test_web_dispatch_smoke.py`](../../ros_ws/src/amr_hw_sim/test/test_web_dispatch_smoke.py)

OpenSpec change `add-web-dispatch`，task 3.3（冒煙測試）、4.3（建置、README）。

## 為什麼要做

單元測試（假 bridge）和整合測試（假車）證明各部分照設計運作，但沒證明「真的 Nav2 + 真的 Gazebo + 後端」接起來能派車——task 3.2 就是在真的 Nav2 上才發現「剛給初始位姿就派車會被拒絕」。端到端測試完全照網頁的方式操作（只用 HTTP 與 WebSocket），把整條線固定成可重複的測試。

## 做了什麼

### 1. 測試帶起什麼

```python
include('amr_worlds', 'world.launch.xml', world=WORLD, headless='true'),
TimerAction(period=3.0, actions=[
    include('amr_bringup', 'robot.launch.xml', hardware='sim', ..., mode='navigation', map=MAP)]),
include('amr_server', 'server.launch.xml', robots=ROBOT_ID, port=str(PORT), use_sim_time='true'),
```

- 世界 headless（不開 GUI），車子系統用 `mode:=navigation` 一行帶起導航（真車開機的方式）。
- 後端埠預設 8150（`WEB_SMOKE_PORT` 可改），不和使用者正在跑的 8000 撞。
- 放在模擬側套件 `amr_hw_sim`（它本來就收所有需要 Gazebo 的測試），在 robot 容器執行（要讀 `/data/maps/*.yaml` 比對）。

### 2. 測試項目（依名稱順序，後面的依賴前面的狀態）

| # | 操作 | 驗證 |
|---|---|---|
| 01 | `GET /map`、`/map.png` | 解析度、原點與 `warehouse_small.yaml` 一致；PNG 標頭 |
| 02 | `GET /robots` | 還沒定位 `pose_ready` 為 false |
| 03 | `POST /initial_pose (1, 1, 0)` | 10 s 內 WebSocket 有位置，和 Gazebo 真實位置差 < 0.3 m |
| 04 | 等 `nav_ready` → `POST /goal (10, 1, π/2)` | 狀態 `succeeded`、目標正確、途中收到路徑；真實位置與目標差 < 0.3 m；WebSocket 位置與真實位置差 < 0.3 m |
| 05 | `POST /goal` 到箱子中心 (7, 4) | `failed` 且有原因 |
| 06 | 派車 → 2 s 後 `DELETE /goal` | `canceled`，之後 1 秒內真實位置移動 < 3 cm |
| 07 | 錯誤碼 | 沒目標取消 409、地圖外 422、不存在的車 404 |
| 關閉後 | — | 所有程序（含後端）正常結束；Gazebo／bridge 例外只警告（同導航冒煙測試） |

- **用 Python 標準庫的 `urllib` 打 HTTP、`websockets.sync.client` 收推送**：測試的角色就是「一個網頁」，不 import 任何後端程式碼。
- **真實位置**用 `ign model -m amr1 -p` 問 Gazebo（同導航冒煙測試）；地圖座標 = 世界座標，不用換算。

## 怎麼驗證（2026-10-08 實測）

- `launch_test test/test_web_dispatch_smoke.py`：7 項 + 關閉檢查全部通過，約 62 秒。
- 完整 `colcon test`（獨立 domain／partition）：**278 項全部通過**（含既有的建圖、導航冒煙測試）。

## 面試追問

**Q：已經有單元測試和整合測試，為什麼還要端到端測試？**
A：前兩者用假物件驗證「我以為的介面」；端到端驗證真實元件的行為和我以為的一樣。這次就有一個例子：假的 action server 一存在就接受目標，真的 Nav2 在啟動完成前會拒絕——只有端到端（或手動實測）抓得到。端到端慢（1 分鐘），所以只放關鍵路徑，細節留給快的測試。

**Q：端到端測試怎麼避免不穩定（flaky）？**
A：等「條件成立」而不是固定 sleep（例如等 `nav_ready`、等狀態不是 navigating）；每個等待都有上限並在失敗時印出最後狀態；用獨立的 domain、partition、埠，避免和其他程式互相干擾。
