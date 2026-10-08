# 30 前端骨架與 SVG 座標系

檔案：[`web/`](../../web/)（`package.json`、`vite.config.ts`、`src/geometry.ts`、`src/api.ts`、`src/useRobotStream.ts`、`src/components/MapView.tsx` 等）

OpenSpec change `add-web-dispatch`，task 4.1。

## 為什麼要做

操作者的網頁：看地圖、看車即時移動。前端只和後端溝通（REST＋WebSocket），完全不懂 ROS。

## 做了什麼

### 1. 工具鏈

| 工具 | 角色 |
|---|---|
| **Vite 8** | 開發伺服器（存檔即更新）與打包（`npm run build` → `dist/`） |
| **React 19** | 畫面元件 |
| **TypeScript 7** | 型別檢查（`tsc --noEmit`；TS 7 是 Go 重寫的版本，快很多） |
| **Vitest 5** + Testing Library + jsdom | 測試（在 Node 裡模擬瀏覽器） |

- `package.json` 用 `--save-exact` 釘死版本，`package-lock.json` 進 git——和 Dockerfile 釘版本同一個理由：可重現。
- 沒有 UI 框架、沒有繪圖套件：地圖用 SVG 自己畫，規模小，自己寫反而好懂。
- `node_modules/`、`dist/` 不進 git（`.gitignore`）。

**開發時的轉送（proxy）**：`npm run dev` 開在 5173，網頁裡的 `/api/...` 由 Vite 轉給後端 8000（含 WebSocket，`ws: true`）。瀏覽器以為只有一個網址，不會有跨來源（CORS）問題；建置後由後端直接提供網頁，同樣只有一個網址。

### 2. SVG 座標系：單位就是公尺

整個 SVG 的 `viewBox` 用公尺當單位，車、目標、路徑都直接用地圖座標畫——只有一件事要處理：**SVG 的 y 向下、地圖的 y 向上**。

```ts
export function toSvg(p: Point): Point { return { x: p.x, y: -p.y } }    // 畫任何東西前把 y 變號
```

- **地圖圖片**：PNG 上方＝地圖 y 最大，所以圖片左上角放在 `(minX, −maxY)`，寬高＝地圖範圍，圖片本身不用翻。
- **角度**：地圖的 yaw 逆時針為正；y 翻過來後 SVG 的 `rotate()` 要變號：`rotate(-yaw°)`。
- **車**：直徑約 0.56 m 的圓（實車約 0.5 m）＋車頭三角形，大小就是真實尺寸，縮放時一起變大變小。

### 3. 螢幕座標 → 地圖座標

滑鼠事件給的是螢幕像素（`clientX/Y`）。SVG 預設 `preserveAspectRatio="xMidYMid meet"`：等比例縮放、置中，多出來的地方留白。

```ts
scale = min(rect.width / vb.width, rect.height / vb.height)       // 每公尺幾像素
left  = rect.left + (rect.width  - vb.width  * scale) / 2         // 置中後圖的左上角
top   = rect.top  + (rect.height - vb.height * scale) / 2
svgX  = vb.x + (clientX - left) / scale
svgY  = vb.y + (clientY - top)  / scale
map   = { x: svgX, y: -svgY }
```

寫成純函式 `clientToMap(clientX, clientY, rect, viewBox)`，測試不需要瀏覽器（jsdom 沒有實作 SVG 的 `getScreenCTM`）。

### 4. 縮放與平移就是改 viewBox

- **滾輪縮放**：以游標下的點為中心——那一點在縮放前後的相對位置不變：`x' = anchor − (anchor − x) × factor`。滾輪事件要 `preventDefault()`（不然整頁捲動），React 的 `onWheel` 是 passive 不能阻止，所以自己 `addEventListener('wheel', ..., { passive: false })`。
- **右鍵／中鍵拖曳平移**：移動的像素 ÷ scale ＝ 公尺，viewBox 往反方向移。右鍵要擋 `contextmenu`。
- **整張地圖**：viewBox 設回地圖範圍加 0.5 m 邊。換了一張不同大小的地圖才自動重設，同一張圖重新載入時保留使用者的縮放。

### 5. 資料：REST 與 WebSocket

- `api.ts`：包 `fetch`，非 2xx 丟出帶 `detail` 的 `ApiError`（後端的中文原因，直接顯示）。地圖圖片網址加 `?v=<版本>`，地圖換了瀏覽器才不會用舊的快取。
- `useRobotStream()`：React hook。連 `/api/ws`，每則訊息更新狀態；`onclose` 後 2 秒重連；`onerror` 一律 `close()`，重連只在一個地方處理。元件卸載時 `stopped = true` 並關閉連線，避免卸載後還在重連。

### 6. 提示橫幅

只顯示最需要處理的一則，依序：與後端斷線 → 尚未收到地圖 → 尚未定位（指引按「設定初始位姿」）→ 導航沒在執行或還在啟動。

## 怎麼驗證（2026-10-08 實測）

- `npm test`：33 項通過（座標轉換、縮放平移、手勢判斷、橫幅、側欄、MapView 手勢、App 整合）；`tsc --noEmit` 無錯誤。
- 臨時容器跑世界＋車子系統（導航）＋後端（8000）＋ `npm run dev`，in-app 瀏覽器開 `http://127.0.0.1:5173/`：
  - 地圖方向與 RViz 相同（貨架左上、箱子左下），原點座標軸在左下角；游標移到倉庫左下角顯示 (0.01, 0.06)、(1, 1) 附近顯示 (1.12, 1.12)。
  - 車輛隨 WebSocket 即時移動、路徑與目標箭頭顯示（見筆記 31）。
  - 滾輪以游標為中心縮放。
  - 停掉後端 → 橫幅「與後端斷線，每 2 秒自動重連…」；重啟後端 → 橫幅消失、資料恢復、縮放保留，不需重新整理。

## 面試追問

**Q：在網頁上畫地圖，SVG 和 Canvas 怎麼選？**
A：元素少（一張底圖、幾台車、幾條路徑）、需要互動與事件，用 SVG：每個東西是 DOM 元素，React 直接管、事件直接掛、縮放靠 viewBox 不用重畫。元素多到上萬（例如點雲）或要每幀重畫才用 Canvas／WebGL。

**Q：開發時前後端在不同埠，怎麼避免 CORS？**
A：讓開發伺服器轉送 API（Vite 的 `server.proxy`），瀏覽器只看到一個來源；正式環境由同一個伺服器（或反向代理）提供網頁與 API。

**Q：WebSocket 斷線重連要注意什麼？**
A：只在 `onclose` 裡排重連（`onerror` 之後一定會 close）、設重連間隔避免狂連、元件卸載時停止重連、畫面要顯示斷線狀態。
