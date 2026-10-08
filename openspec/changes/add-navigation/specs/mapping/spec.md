# Spec Delta

## Purpose

讓車子系統以 2D 光達與里程計在行駛中建立倉庫的佔據格地圖，並把地圖存成之後定位、導航與網頁顯示都能讀取的檔案。

## ADDED Requirements

### Requirement: 線上建圖
車子系統在建圖模式下 SHALL 依車輛的光達與里程計，隨車輛行駛持續更新 2D 佔據格地圖，並發布到車輛 namespace 下的 `map` topic（第一台為 `/amr1/map`），解析度 0.05 m／格。

#### Scenario: 開始建圖
- **WHEN** 車子系統以建圖模式啟動且光達有資料
- **THEN** 30 秒內 `/amr1/map` 有資料，地圖中車輛周圍的牆已標為佔據

#### Scenario: 行駛後地圖擴大
- **WHEN** 建圖中車輛行駛到先前看不到的區域
- **THEN** 地圖中已知（佔據或空曠）的格數增加

### Requirement: 建圖時提供地圖座標系
建圖模式下 SHALL 發布 TF `map → <id>/odom`，使車輛在地圖上的位置可由 TF `map → <id>/base_footprint` 取得；地圖座標系 `map` 不帶車輛前綴，供多車共用。

#### Scenario: 查得到車輛在地圖上的位置
- **WHEN** 建圖模式執行中
- **THEN** 查詢 TF `map → amr1/base_footprint` 可得到結果，且 `map → amr1/odom` 恰有一個發布者

### Requirement: 存圖
使用者 SHALL 能把建圖中的地圖存成一組檔案：佔據格圖片（`.pgm`）與描述解析度、原點、佔據門檻的說明檔（`.yaml`），存放在執行資料目錄的 `maps/` 下，檔名由使用者指定。存檔不需要停止建圖。

#### Scenario: 存出地圖檔
- **WHEN** 建圖中使用者依 README 的指令以名稱 `warehouse_small` 存圖
- **THEN** 主機的 `docker/amr_sim/data/maps/` 下出現 `warehouse_small.pgm` 與 `warehouse_small.yaml`，以圖片檢視器打開 `.pgm` 可看到倉庫的牆與貨架輪廓

#### Scenario: 存出的地圖可供導航載入
- **WHEN** 以剛存出的地圖名稱啟動導航模式
- **THEN** 地圖成功載入，`/amr1/map` 的內容與存檔時一致

### Requirement: 建圖不依賴模擬
建圖 SHALL 只使用車輛的標準介面（`/<id>/scan`、`/<id>/odom`、TF），在模擬與真車上以相同方式執行；模擬時 SHALL 使用模擬時間。

#### Scenario: 模擬模式下建圖
- **WHEN** 以 `hardware:=sim` 啟動車子系統後，以 `use_sim_time:=true` 另外啟動建圖
- **THEN** 建圖節點使用模擬時間，且 robot 側沒有啟動任何建圖專用的模擬節點

### Requirement: 存圖服務
建圖模式 SHALL 提供存圖服務 `/<id>/map_saver/save_map`：給定地圖 topic 與存放路徑，把目前的地圖存成 `.pgm` + `.yaml`，並回報成功或失敗。

#### Scenario: 以服務存圖
- **WHEN** 建圖中呼叫 `/amr1/map_saver/save_map`，地圖 topic 為 `/amr1/map`、路徑為 `/data/maps/test_map`
- **THEN** 服務回報成功，主機的 `docker/amr_sim/data/maps/` 下出現 `test_map.pgm` 與 `test_map.yaml`

### Requirement: 建圖面板
RViz SHALL 提供建圖面板：可輸入車輛 id 與地圖名稱，按「存圖」時先顯示完整存放路徑並提醒同名檔案會被覆蓋，確認後呼叫存圖服務並顯示結果；面板 SHALL 顯示目前地圖的尺寸、已知區域比例與最後更新時間。面板的車輛 id 與地圖名稱 SHALL 隨 RViz 設定檔保存。

#### Scenario: 按鈕存圖
- **WHEN** 建圖中使用者在面板輸入地圖名稱 `warehouse_small` 並按「存圖」、在確認視窗按確定
- **THEN** 面板顯示存圖成功與路徑 `/data/maps/warehouse_small`，主機上出現對應檔案

#### Scenario: 取消存圖
- **WHEN** 使用者按「存圖」後在確認視窗按取消
- **THEN** 不呼叫存圖服務，既有檔案不變

#### Scenario: 顯示建圖狀態
- **WHEN** 建圖中車輛行駛到新區域
- **THEN** 面板的地圖尺寸與已知比例隨之更新

