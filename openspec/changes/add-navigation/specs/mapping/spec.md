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
- **THEN** 主機的 `data/maps/` 下出現 `warehouse_small.pgm` 與 `warehouse_small.yaml`，以圖片檢視器打開 `.pgm` 可看到倉庫的牆與貨架輪廓

#### Scenario: 存出的地圖可供導航載入
- **WHEN** 以剛存出的地圖名稱啟動導航模式
- **THEN** 地圖成功載入，`/amr1/map` 的內容與存檔時一致

### Requirement: 建圖不依賴模擬
建圖 SHALL 只使用車輛的標準介面（`/<id>/scan`、`/<id>/odom`、TF），在模擬與真車上以相同方式執行；模擬時 SHALL 使用模擬時間。

#### Scenario: 模擬模式下建圖
- **WHEN** 以 `hardware:=sim mode:=mapping` 啟動車子系統
- **THEN** 建圖節點使用模擬時間，且 robot 側沒有啟動任何建圖專用的模擬節點
