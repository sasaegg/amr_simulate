# 29 REST 與 WebSocket（FastAPI）

檔案：[`amr_server/api.py`](../../ros_ws/src/amr_server/amr_server/api.py)、[`test/test_api.py`](../../ros_ws/src/amr_server/test/test_api.py)

OpenSpec change `add-web-dispatch`，task 2.2。

## 為什麼要做

網頁只和後端溝通（不直連 ROS）。後端要提供兩種東西：
- **一問一答**（拿地圖、派車、取消）→ REST：每次一個 HTTP 請求。
- **持續更新**（車的位置每秒 10 次）→ WebSocket：開一條連線，後端主動推。

## 做了什麼

### 1. 路由一覽

| 方法 | 路徑 | 成功 | 失敗 |
|---|---|---|---|
| GET | `/api/robots` | 200 清單 | — |
| GET | `/api/robots/{id}/map` | 200 地圖資訊 | 404 沒這台車、503 還沒有地圖 |
| GET | `/api/robots/{id}/map.png` | 200 PNG | 404、503 |
| POST | `/api/robots/{id}/goal` | 202 | 404、422 輸入不對或在地圖外、503 沒地圖或導航沒執行 |
| DELETE | `/api/robots/{id}/goal` | 202 | 404、409 沒有進行中的目標 |
| POST | `/api/robots/{id}/initial_pose` | 202 | 404、422、503 |
| WS | `/api/ws` | 每 0.1 s 一則所有車的狀態 | — |

### 2. 狀態碼怎麼選

- **202 Accepted**（不是 200）：派車「已收到、處理中」，結果要等車開到才知道，透過 WebSocket 的 `status` 回報。
- **404**：網址指的東西（這台車）不存在。
- **409 Conflict**：請求本身沒錯，但和目前狀態衝突——沒有目標卻要取消。
- **422 Unprocessable**：格式對（是 JSON），內容不合理（NaN、缺欄位、在地圖外）。
- **503 Service Unavailable**：後端沒問題，是它依賴的東西（地圖、Nav2）還沒準備好；之後再試可能就好了。

所有錯誤都是 `{"detail": "一句人看得懂的原因"}`，前端直接顯示。

### 3. FastAPI 的寫法

```python
class PoseIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    x: float
    y: float
    yaw: float

@app.post('/api/robots/{robot_id}/goal', status_code=202)
def send_goal(robot_id: str, pose: PoseIn):
    bridge = bridge_of(robot_id)                       # 不存在 → HTTPException(404)
    require_in_map(robot_id, bridge, pose, '目標')      # 地圖外 → 422
    try:
        bridge.send_goal(pose.x, pose.y, pose.yaw)
    except NavigationUnavailable as e:
        raise HTTPException(503, str(e))
    return {'detail': '已送出目標'}
```

- **型別提示就是規格**：`robot_id: str` 從網址取，`pose: PoseIn` 從 JSON body 解析並驗證（Pydantic）。驗證失敗 FastAPI 自動回 422，函式根本不會被呼叫。
- **`allow_inf_nan=False`**：Python 的 `float` 接受 NaN、無限大，但它們不能當座標。
- **`def` 還是 `async def`**：一般 `def` 的路由，FastAPI 會丟到執行緒池執行；`send_goal` 裡最多等 0.5 s 確認 Nav2 在不在，用 `def` 才不會卡住整個事件迴圈（卡住的話所有 WebSocket 推送都會停）。WebSocket 本身用 `async def`，因為它整段時間都在 `await`。
- **自動文件**：開 `http://localhost:8000/docs` 就有 Swagger UI，可以直接在網頁上試每個 API。

### 4. WebSocket 推送

```python
@app.websocket('/api/ws')
async def push_state(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({'robots': {rid: state_json(b.state()) for rid, b in bridges.items()}})
            await asyncio.sleep(push_period)
    except WebSocketDisconnect:
        pass
```

**推送 vs 輪詢**：輪詢是前端每 0.1 s 發一次 HTTP 請求，每次都要建連線、帶標頭，大部分回應「沒變」；WebSocket 開一條連線就一直用，後端想送就送。即時位置這種「高頻、伺服器主動」的資料適合 WebSocket；派車這種「使用者動作、要知道成不成功」的適合 REST。

### 5. 網頁靜態檔

`npm run build` 產生的 `dist/` 用 `StaticFiles(..., html=True)` 掛在 `/`。**一定要在所有 `/api` 路由之後掛**：掛在 `/` 的東西會攔下所有網址，先掛的話 `/api/robots` 也會被當成找檔案。沒建置時 `/` 回一段純文字教你怎麼建。

## 怎麼驗證（2026-10-08 實測）

`test_api.py` 30 項，用假的 bridge（`FakeBridge`）＋ FastAPI 的 `TestClient`（在記憶體裡模擬 HTTP，不用真的開埠）：

- 每個路由的成功與每種錯誤碼（含 5 個路由的 404、NaN／無限大／缺欄位／字串／不是 JSON 的 422、地圖三個邊界的 422）。
- 不合法的輸入不會呼叫 bridge（`bridge.goals == []`）。
- WebSocket 訊息格式完全比對；狀態改變後下一則訊息就反映。
- 有建置／沒建置網頁兩種情況，以及 `/api` 不被靜態檔蓋掉。

全部 51 項（含 task 2.1）通過。

## 面試追問

**Q：REST 和 WebSocket 各適合什麼？**
A：REST 適合一次性的請求與回應，可快取、無狀態、好除錯；WebSocket 適合伺服器要主動、頻繁推送的資料（即時位置、聊天、行情）。常見組合：指令走 REST、狀態走 WebSocket。

**Q：派車的 API 為什麼回 202 而不是 200？**
A：202 表示請求被接受但還在處理，結果要另外查（這裡由 WebSocket 推送）。導航要幾十秒，HTTP 請求不該一直等到車開到。

**Q：FastAPI 什麼時候用 def、什麼時候用 async def？**
A：函式內有阻塞呼叫（同步 I/O、`time.sleep`、等待其他執行緒）就用 `def`，FastAPI 會放到執行緒池；整段都是 `await` 的才用 `async def`。在 `async def` 裡做阻塞呼叫會卡住整個事件迴圈。

## 踩坑紀錄

- **NaN 的 422 變成 500**：FastAPI 預設的 422 回應會把原始輸入放回 `detail`，輸入是 NaN 時 JSON 編碼失敗（`Out of range float values are not JSON compliant`），反而回 500。改成自訂 `RequestValidationError` 處理：回一行可讀的字串（例如「輸入不正確：yaw：Input should be a finite number」），不回原始輸入。測試有涵蓋。
- **`StarletteDeprecationWarning: install httpx2 instead`**：新版 Starlette 建議測試用 `httpx2`。目前 `httpx` 仍可用，只是警告，先不換（之後升級 FastAPI 時一起處理）。
