# Spec Delta

## Purpose

中控後端是操作介面（網頁，以及之後的任務佇列）與車輛之間唯一的橋梁：以 HTTP／WebSocket 提供每台車的地圖、即時位置與導航狀態，並把派車、取消與初始位姿轉成車子系統的標準介面。

## ADDED Requirements

### Requirement: 車輛清單
後端 SHALL 依啟動參數 `robots`（逗號分隔的車輛 id，預設 `amr1`）管理車輛，並以 `GET /api/robots` 回傳每台車的 id 與三項就緒狀態：已收到地圖、已定位、導航可接受目標。所有車輛相關路徑 SHALL 帶車輛 id（`/api/robots/{id}/...`）；不在清單中的 id SHALL 回應 404。

#### Scenario: 列出車輛
- **WHEN** 後端以 `robots:=amr1` 啟動，車子系統與導航都在執行且已給定初始位姿
- **THEN** `GET /api/robots` 回傳一筆 `amr1`，三項就緒狀態皆為 true

#### Scenario: 不存在的車輛
- **WHEN** 呼叫 `GET /api/robots/amr9/map`
- **THEN** 回應 404

### Requirement: 地圖
後端 SHALL 以車輛導航正在使用的地圖（`/<id>/map`）提供地圖資訊（寬、高、解析度、原點、版本）與 PNG 圖片；圖片 SHALL 以白色表示空曠、黑色表示障礙、灰色表示未知，圖片上方對應地圖 y 最大的一側。每收到一次新地圖，版本 SHALL 遞增。尚未收到地圖時 SHALL 回應 503。

#### Scenario: 取得地圖
- **WHEN** 導航以 `map:=warehouse_small` 執行中，呼叫地圖資訊與圖片
- **THEN** 資訊的解析度、原點與寬高和 `warehouse_small.yaml`／`.pgm` 一致，圖片與 `.pgm` 的空曠、障礙、未知格位置相同

#### Scenario: 地圖重新載入
- **WHEN** 車上的地圖被重新載入（例如標完原點後）
- **THEN** 地圖版本遞增，之後取得的圖片與資訊為新地圖

#### Scenario: 尚未收到地圖
- **WHEN** 車子系統沒有執行導航，呼叫地圖資訊
- **THEN** 回應 503，訊息指出尚未收到地圖

### Requirement: 即時狀態推送
後端 SHALL 提供 WebSocket，連線後每 0.1 秒推送所有車輛的：位置（地圖座標 x、y、yaw）、目前目標、導航狀態（`idle`、`navigating`、`succeeded`、`failed`、`canceled`）、失敗原因、剩餘距離、規劃路徑、地圖版本。無法取得位置（尚未定位，或位置超過 2 秒沒有更新）時位置 SHALL 為空值。

#### Scenario: 位置隨車移動
- **WHEN** 已定位的車輛行駛中，用戶端連上 WebSocket
- **THEN** 每秒約收到 10 則訊息，位置與 TF `map → amr1/base_footprint` 相差 0.05 m 以內

#### Scenario: 尚未定位
- **WHEN** 導航執行中但尚未給定初始位姿
- **THEN** 訊息中該車的位置為空值

#### Scenario: 車子系統停止
- **WHEN** 已定位後車子系統停止
- **THEN** 2 秒後訊息中該車的位置變為空值

### Requirement: 派車
後端 SHALL 以 `POST /api/robots/{id}/goal`（地圖座標 x、y、yaw）把目標送給該車的導航；接受後回應 202，狀態變為 `navigating`。導航進行中再送新目標 SHALL 取代原目標。抵達時狀態 SHALL 變為 `succeeded`；導航放棄或拒絕目標時 SHALL 變為 `failed` 並附原因。

#### Scenario: 派車到可到達的位置
- **WHEN** 已定位後送出地圖中空曠處的目標
- **THEN** 回應 202，狀態依序為 `navigating`、`succeeded`，車輛在 Gazebo 中的位置與目標相差 0.3 m 以內

#### Scenario: 目標到不了
- **WHEN** 送出障礙物內的目標
- **THEN** 狀態最後為 `failed`，失敗原因非空，車輛停下

#### Scenario: 新目標取代舊目標
- **WHEN** 導航進行中送出另一個目標
- **THEN** 車輛改往新目標，狀態最後為 `succeeded`，目前目標為新目標

### Requirement: 取消
後端 SHALL 以 `DELETE /api/robots/{id}/goal` 取消該車進行中的目標，回應 202，車輛停下且狀態變為 `canceled`。沒有進行中的目標時 SHALL 回應 409。

#### Scenario: 中途取消
- **WHEN** 導航進行中呼叫取消
- **THEN** 回應 202，狀態變為 `canceled`，車輛 1 秒內停下

#### Scenario: 沒有目標可取消
- **WHEN** 狀態不是 `navigating` 時呼叫取消
- **THEN** 回應 409

### Requirement: 設定初始位姿
後端 SHALL 以 `POST /api/robots/{id}/initial_pose`（地圖座標 x、y、yaw）發布該車的初始位姿（與 RViz 2D Pose Estimate 相同的介面），回應 202。

#### Scenario: 從網頁開始定位
- **WHEN** 導航執行中尚未定位，以車輛在 Gazebo 中的實際位置呼叫設定初始位姿
- **THEN** 回應 202，10 秒內 WebSocket 的位置與車輛實際位置相差 0.3 m 以內

### Requirement: 拒絕不合法或無法執行的請求
後端 SHALL 驗證派車與初始位姿的輸入：缺欄位、非數值、NaN、無限大或座標在目前地圖範圍外時 SHALL 回應 422 且不送出任何指令。該車的導航沒有在執行（0.5 秒內找不到導航的 action）時，派車 SHALL 回應 503。錯誤回應 SHALL 附可讀的原因。

#### Scenario: 目標在地圖外
- **WHEN** 送出 x 為 999 的目標
- **THEN** 回應 422，原因指出目標在地圖範圍外，車輛沒有動作

#### Scenario: 數值不合法
- **WHEN** 送出 yaw 為 NaN 或缺少 y 的目標
- **THEN** 回應 422

#### Scenario: 導航沒有執行
- **WHEN** 車子系統執行中但沒有啟動導航，送出目標
- **THEN** 回應 503，原因指出導航沒有在執行

### Requirement: 提供網頁
後端 SHALL 在根路徑提供建置好的操作者網頁，使操作者只需開啟後端的網址即可使用；網頁尚未建置時 SHALL 在根路徑回應說明如何建置的訊息，API 照常運作。

#### Scenario: 開啟網頁
- **WHEN** 網頁已建置，瀏覽器開啟 `http://localhost:8000/`
- **THEN** 顯示操作者網頁

#### Scenario: 網頁尚未建置
- **WHEN** 網頁沒有建置，瀏覽器開啟 `http://localhost:8000/`
- **THEN** 顯示如何建置網頁的訊息，`GET /api/robots` 仍正常回應

### Requirement: 後端不依賴模擬
後端 SHALL 只使用車子系統的標準介面（地圖、路徑 topic、TF、導航 action、初始位姿 topic），SHALL 不依賴任何模擬套件，使真車部署時不需修改。

#### Scenario: 套件相依
- **WHEN** 檢查後端套件的相依與 launch 檔
- **THEN** 不含 `ros_gz*`、`amr_hw_sim`、`amr_worlds`
