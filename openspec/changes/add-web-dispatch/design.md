# Design

## Context

- 子專案 2 完成後的車子系統介面（見 `openspec/specs/navigation`、`mapping`）：map_server 發布 `/<id>/map`（Transient Local）；TF 為全域 `/tf`，frame `map → <id>/odom → <id>/base_footprint`；Nav2 在 namespace `<id>` 下提供 `/<id>/navigate_to_pose` action、發布 `/<id>/plan`；AMCL 訂閱 `/<id>/initialpose`。地圖座標即 5.3 標好的倉庫座標（`warehouse_small` 與 Gazebo 世界座標一致）。
- 容器：sim、robot 兩個，同一個映像 `amr-sim:humble`（`osrf/ros:humble-desktop`、Python 3.10，已含 numpy 1.21、Pillow 9）；`network_mode: host`、`ipc: host`；`up.sh <gpu|cpu> <sim|robot|all>`、`exec.sh <sim|robot>`。
- 冒煙測試的慣例：launch_testing、放在模擬側套件 `amr_hw_sim`、在 robot 容器執行（需要 `/data` 的地圖）、以 `ROS_DOMAIN_ID`／`IGN_PARTITION` 隔離。
- 使用者決定（brainstorming，2026-10-08）：只做 2D；不建資料庫；新增 server 容器；後端為 ROS 節點、前端 REST＋WebSocket（方案 1）；RViz 式拖曳派車；網頁可設定初始位姿。

## Goals / Non-Goals

**Goals:**
- 後端的 ROS 部分與 HTTP 部分以清楚的介面分開，API 不碰 rclpy，可用假的 bridge 單元測試。
- 前端的座標轉換與手勢判斷是純函式，可單元測試。
- 多車：程式結構以「每台車一個 bridge」組成，第一版只跑 `amr1`。

**Non-Goals:**
- 3D 視角、SQLite、儲位、任務佇列（子專案 4）。
- 使用者驗證與權限（第一版只綁 `127.0.0.1`，見 Risks）。
- 生產等級部署（反向代理、HTTPS、process manager）。

## Decisions

### D1：server 容器與映像

- compose 新增 service `server`：同一個映像、`command: sleep infinity`、`init: true`、`network_mode: host`、`ipc: host`（Fast DDS 同主機走 shared memory，和另外兩個容器一致，否則收不到資料）、`env_file: ./config/ros.env`；掛載 `../../ros_ws:/ros_ws`、`../../web:/web`。**不要** GPU、`DISPLAY`、X11 socket、`/data`。
- `up.sh` 第二個參數接受 `server`；`all` 維持「不指定服務＝全部」。`exec.sh` 接受 `server`，用法說明列出 `ros2 launch amr_server server.launch.xml`。軟體渲染疊加檔不動。
- Dockerfile：
  - `pip install --no-cache-dir` 釘死版本的 `fastapi`、`uvicorn[standard]`（含 WebSocket 支援）、`httpx`（FastAPI TestClient 需要）。apt 的 `python3-fastapi` 是 0.78，太舊（Pydantic v1、lifespan 寫法不同）。版本於 task 1.1 選定當下穩定版並寫進 Dockerfile。
  - Node.js 24 LTS：從 `nodejs.org/dist` 下載 `linux-x64` tarball，以同目錄 `SHASUMS256.txt` 驗證 SHA256 後解壓到 `/usr/local`。替代：NodeSource apt 套件庫（要加第三方金鑰與 repo）；Ubuntu apt 的 Node 12（Vite 需要 18 以上）；另開官方 `node` 映像的容器（多一個容器，且後端與前端分處兩個容器，開發時要切換）。
  - 放在 apt 那層之後、建立使用者之前，避免改 Node 版本時重跑 apt。
- 替代：後端放 robot 容器——多車時每台車各有一個後端，與「中控管全部車」矛盾（brainstorming 選定 server 容器）。

### D2：後端套件 `amr_server` 與模組邊界

ament_python，`colcon build`／`test` 與其他套件一致。package.xml 執行相依：`rclpy`、`tf2_ros`、`nav2_msgs`、`nav_msgs`、`geometry_msgs`、`launch_xml`；FastAPI 等由映像 pip 提供（rosdep 沒有對應鍵，package.xml 不列，於 README 與筆記說明）。

```
amr_server/
  map_image.py     OccupancyGrid（寬、高、data）→ PNG bytes；純函式
  geometry.py      四元數 ↔ yaw、路徑降取樣、點是否在地圖範圍內；純函式
  state.py         RobotState dataclass（pose、goal、status、message、distance_remaining、plan、map_version）
  bridge.py        RobotBridge 介面（Protocol）：state()、map_info()、map_png()、send_goal()、cancel()、set_initial_pose()、nav_ready()
  ros_bridge.py    RosRobotBridge：以 rclpy 實作上面的介面；FleetNode 持有每台車一個
  api.py           create_app(bridges: dict[str, RobotBridge], web_dir) → FastAPI；只依賴 bridge.py
  main.py          進入點 `server`：解析參數、建立 FleetNode、啟動 executor 執行緒與 uvicorn
launch/server.launch.xml
test/
```

`api.py` 只拿到 `RobotBridge` 介面，測試時傳入 `FakeBridge`，完全不需要 ROS。

### D3：rclpy 與 FastAPI 在同一個程序

- `main.py`：`rclpy.init()` → 建立 `FleetNode`（一個節點，內含每台車的訂閱、action client、publisher，以及共用的 tf2 Buffer／TransformListener）→ `MultiThreadedExecutor` 在背景執行緒 `spin()` → 主執行緒 `uvicorn.run(app, host, port)`。uvicorn 收到 SIGINT（`ros2 launch` 的 Ctrl+C）結束後，`executor.shutdown()`、`node.destroy_node()`、`rclpy.shutdown()`。
- 共享狀態：ROS 回呼（背景執行緒）寫入 RobotState，API／WebSocket（asyncio 執行緒）讀取；每台車一把 `threading.Lock`，讀取時回傳複本。
- 會等待的 API（例如 action server 是否就緒）宣告成一般 `def` 路由，FastAPI 會放到執行緒池，不卡住事件迴圈；WebSocket 用 `async def`，每 0.1 秒 `await asyncio.sleep(0.1)` 後送出所有車的狀態快照。
- 參數：launch 以 `<param>` 給節點 `robots`、`host`、`port`、`web_dir`（預設 `/web/dist`）；`use_sim_time` 以 `ros_args="-p use_sim_time:=$(var use_sim_time)"`（同子專案 2 的做法）。
- 替代：兩個程序（ROS 節點＋web 伺服器）以 IPC 溝通——多一層協定；`rclpy` 跑在 asyncio 內（`spin_once` 輪詢）——延遲與 CPU 取捨不好，action 回呼時機難掌握。

### D4：RosRobotBridge 的行為

- **地圖**：訂閱 `/<id>/map`（`QoS(1).reliable().transient_local()`），每收到一則 `map_version += 1`，同時以 `map_image` 轉好 PNG 快取（地圖不常變，避免每次請求都轉）。
- **位置**：每次取狀態時 `buffer.lookup_transform("map", "<id>/base_footprint", Time())`（最新一筆）；查不到，或 `now − 該筆時間 > 2 s`，位置為 `None`。`use_sim_time` 為 true 時 `now` 是模擬時間，與 TF 時間一致。
- **路徑**：訂閱 `/<id>/plan`，降取樣成點與點間隔約 0.1 m（保留最後一點）；狀態不是 `navigating` 時清空。
- **派車**：`send_goal(x, y, yaw)`：
  1. `action_client.wait_for_server(timeout_sec=0.5)` 失敗 → 回報「導航沒在執行」（API 回 503）。
  2. 遞增 `goal_seq`，狀態設為 `navigating`、記錄目標、清空 message，呼叫 `send_goal_async`（帶 feedback 回呼取 `distance_remaining`）。
  3. goal response：被拒絕 → `failed`「Nav2 拒絕目標」；接受 → 記錄 goal handle，取得 result future。
  4. result：`SUCCEEDED` → `succeeded`；`CANCELED` → `canceled`；`ABORTED` → `failed`「Nav2 放棄（到不了或卡住）」（Humble 的 NavigateToPose 結果沒有錯誤碼）。
  - **每個回呼都比對 `goal_seq`**：被新目標取代的舊目標，其結果（Nav2 會以 ABORTED／CANCELED 結束舊目標）不得改寫目前的狀態。
- **取消**：狀態不是 `navigating` → 回報「沒有進行中的目標」（409）。goal handle 已取得 → `cancel_goal_async`；還在等接受 → 記下「接受後立刻取消」。狀態在 result 回來時變 `canceled`。
- **初始位姿**：發布 `PoseWithCovarianceStamped` 到 `/<id>/initialpose`，frame `map`、stamp 為現在、共變異數與 RViz 2D Pose Estimate 相同（x、y 0.25，yaw 0.0685）。
- **就緒狀態**：`map_ready` = 收到過地圖；`pose_ready` = 位置不是 `None`；`nav_ready` = `action_client.server_is_ready()`（不等待）。

### D5：API 細節

- 路由與回應見 `specs/fleet-server`；WebSocket 訊息格式：`{"robots": {"<id>": {pose, goal, status, message, distance_remaining, plan, map_version, map_ready, nav_ready}}}`，`pose`／`goal` 為 `{x, y, yaw}` 或 `null`，`plan` 為 `[[x, y], ...]`。
- 輸入用 Pydantic model（`x: float, y: float, yaw: float`）；`allow_inf_nan=False` 拒絕 NaN／無限大 → 422。地圖範圍檢查在路由中做（需要該車的地圖資訊；尚未收到地圖時派車回 503）。
- 錯誤回應統一 `{"detail": "<原因>"}`（FastAPI 預設格式），前端直接顯示 `detail`。
- 靜態檔：`web_dir` 存在時以 `StaticFiles(directory=web_dir, html=True)` 掛在 `/`（掛在所有 `/api` 路由之後）；不存在時 `/` 回一段純文字說明（`cd /web && npm install && npm run build`）。

### D6：前端

- Vite 的 `react-ts` 範本；相依只有 `react`、`react-dom`；開發相依 `vite`、`typescript`、`vitest`、`@testing-library/react`、`jsdom`。不用 UI 框架與繪圖套件（SVG 直接寫）。
- **座標**：SVG 內層 `<g transform="scale(1,-1)">` 讓 1 單位＝1 公尺、y 向上；地圖圖片放在 `(origin_x, origin_y)`、大小 `width×res`、`height×res`（圖片在 g 內要再翻回來，否則上下顛倒）。外層 `viewBox` 控制縮放平移。螢幕 → 地圖座標用 `svg.getScreenCTM().inverse()`，包在 `geometry.ts` 可測的函式中（測試時以矩陣參數傳入）。
- **手勢**（`MapView.tsx`）：`pointerdown`（左鍵）記錄地圖座標 → `pointermove` 超過 0.1 m 才算拖曳、算 `atan2` 為 yaw、顯示預覽箭頭 → `pointerup` 送出。沒拖曳時 yaw＝車目前朝向（沒有位置時為 0）。`setPointerCapture` 讓滑出 SVG 也收得到放開。模式 `dispatch`／`initial_pose` 由 App 狀態決定。
- **縮放平移**：滾輪以游標為中心縮放 viewBox；右鍵／中鍵拖曳平移（`contextmenu` 事件取消預設選單）；「整張地圖」把 viewBox 設回地圖範圍加 0.5 m 邊。
- **資料**：`useRobotStream`（WebSocket，`onclose` 後 2 秒重連，回傳 `{connected, robots}`）；`api.ts` 包 fetch，非 2xx 時丟出含 `detail` 的錯誤。地圖版本變了才重新抓 `map.png`（URL 加 `?v=<version>` 避免快取）。
- **開發**：`vite.config.ts` 的 `server.proxy` 把 `/api`（含 `ws: true`）轉到 `http://localhost:8000`；`npm run dev -- --host 127.0.0.1`。

### D7：測試策略

| 層級 | 位置 | 內容 | 需要 |
|---|---|---|---|
| 純函式 | `amr_server/test/test_map_image.py`、`test_geometry.py` | 三種顏色、上下翻轉、門檻；yaw 換算、降取樣、範圍判斷 | 無 |
| API | `amr_server/test/test_api.py` | FakeBridge＋TestClient：每個路由的狀態碼、422／409／503／404、WebSocket 訊息格式、靜態檔與未建置訊息 | 無 ROS |
| bridge 整合 | `amr_server/test/test_ros_bridge.py` | 同程序：假的 NavigateToPose action server（可設定成功／拒絕／放棄／慢速可取消）、`StaticTransformBroadcaster`、假地圖與 plan 發布者；驗證狀態轉換、舊目標結果被忽略、位置過期、初始位姿訊息內容 | rclpy，數秒 |
| 套件邊界 | `amr_server/test/test_package_boundary.py` | package.xml 與 launch 不含模擬套件 | 無 |
| 端到端 | `amr_hw_sim/test/test_web_dispatch_smoke.py` | world headless＋`robot.launch.xml hardware:=sim x:=1 y:=1 mode:=navigation map:=warehouse_small`＋`server.launch.xml use_sim_time:=true port:=<空閒埠>`；HTTP 設定初始位姿 (1, 1, 0) → WebSocket 位置誤差 < 0.3 m；地圖資訊與 yaml 一致；派到 (10, 1) → `succeeded` 且 Gazebo 真實位置誤差 < 0.3 m；派到箱子內 → `failed`；導航中取消 → `canceled` | robot 容器，約 2 分鐘 |
| 前端 | `web/src/**/*.test.ts(x)` | `geometry.ts`；MapView 拖曳送出正確 x、y、yaw，只點不拖用車的朝向，地圖外不送；初始位姿模式；Banner；`tsc --noEmit` | server 容器 `npm test` |

`colcon test` 包含前四層與端到端；前端測試以 `npm test` 另外執行（不納入 colcon，README 註明）。

### D8：學習筆記

編號接續（26 起），段落同前。預計：26 server 容器與映像（Node、pip、為什麼不用 apt 版）、27 rclpy 與 FastAPI 共存（執行緒、事件迴圈、鎖）、28 RobotBridge（TF 查位置、action client 狀態機、舊目標結果）、29 REST 與 WebSocket（狀態碼、驗證、推送 vs 輪詢）、30 前端骨架與 SVG 座標系、31 拖曳手勢與派車／初始位姿、32 端到端冒煙測試與 README、33 使用者驗收。

## Risks / Trade-offs

- [沒有驗證，任何連得到埠的人都能派車] → `host` 預設 `127.0.0.1`，只有本機能連；要讓其他電腦連線需明確 `host:=0.0.0.0`，README 標示風險。驗證留給之後的子專案。
- [rclpy 回呼與 API 在不同執行緒，狀態競爭] → 每台車一把鎖、只交換複本；bridge 整合測試涵蓋「新目標取代舊目標」的回呼順序。
- [Nav2 被新目標取代時，舊目標的結果晚到] → `goal_seq` 比對（D4），測試以假 action server 刻意延遲舊結果。
- [`wait_for_server` 會阻塞] → 只在 `def` 路由（執行緒池）中呼叫，最多 0.5 s。
- [映像變大、需要重建] → Node 約 100 MB；重建由使用者執行（`up.sh gpu all --build`），已有的 sim、robot 容器也會換成新映像（內容向後相容）。
- [主機已有程式占用 8000 或 5173] → `port` 參數；Vite 埠可用 `--port` 改。
- [WebSocket 每 0.1 秒推送整條路徑] → 降取樣到 0.1 m（20 m 路徑約 200 點、約 4 KB／則），本機連線可接受；之後多車或遠端時再改成只在變更時送。

## Migration Plan

1. 使用者重建映像並啟動三個容器（`up.sh gpu all --build`）。既有的世界、車子系統操作不變。
2. 回復：移除 compose 的 `server` service 與 Dockerfile 的新增層即可；robot、sim 的套件沒有被修改。
