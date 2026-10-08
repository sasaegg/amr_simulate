# Spec Delta

## Purpose

讓車子系統在已存好的地圖上定位，並在收到目標位姿後自行規劃路徑、避開障礙物行駛到目標，無法到達時明確回報失敗。

## ADDED Requirements

### Requirement: 載入地圖
導航模式 SHALL 依啟動參數 `map` 從執行資料目錄的 `maps/<map>.yaml` 載入地圖並發布到 `/<id>/map`；未指定時 SHALL 為 `warehouse_small`。地圖檔不存在時 SHALL 在訊息中顯示嘗試載入的路徑，且不開始導航。

#### Scenario: 載入預設地圖
- **WHEN** 以 `mode:=navigation` 啟動車子系統且未指定 `map`
- **THEN** `/amr1/map` 發布 `data/maps/warehouse_small` 的地圖

#### Scenario: 地圖不存在
- **WHEN** 以 `mode:=navigation map:=nope` 啟動
- **THEN** 訊息顯示找不到 `/data/maps/nope.yaml`，導航沒有啟動

### Requirement: 以初始位姿開始定位
導航模式 SHALL 在使用者給定初始位姿（RViz 的 2D Pose Estimate，即 `/<id>/initialpose`）後開始在地圖上定位，並發布 TF `map → <id>/odom`；給定之前 SHALL 不發布。

#### Scenario: 給定初始位姿
- **WHEN** 導航模式啟動後，使用者在 RViz 把初始位姿點在車輛實際所在位置
- **THEN** 10 秒內查得到 TF `map → amr1/base_footprint`，位置與車輛實際位置相差 0.3 m 以內

### Requirement: 行駛中持續定位
定位 SHALL 隨車輛行駛以光達比對地圖持續修正，使 `map → <id>/base_footprint` 與車輛實際位置保持一致；地圖座標系 `map` 不帶車輛前綴。

#### Scenario: 行駛後仍正確
- **WHEN** 給定初始位姿後，車輛行駛 5 m 以上
- **THEN** TF `map → amr1/base_footprint` 與車輛在世界中的實際位置相差 0.3 m 以內

### Requirement: 導航到目標位姿
導航模式 SHALL 接受地圖座標系 `map` 中的目標位姿（RViz 的 Nav2 Goal，或 `/<id>/navigate_to_pose` action），規劃避開地圖障礙物的路徑並自動行駛，抵達後停車並回報成功。導航時線速度 SHALL 不超過 0.5 m/s、角速度不超過 1.0 rad/s。

#### Scenario: 到達可到達的目標
- **WHEN** 定位完成後送出地圖中空曠處的目標位姿
- **THEN** 車輛行駛到目標並停下，action 回報成功，位置誤差 0.3 m 以內

#### Scenario: 速度不超過導航上限
- **WHEN** 導航中車輛直線行駛
- **THEN** `/amr1/odom` 的線速度不超過 0.5 m/s

### Requirement: 避開地圖上沒有的障礙物
導航 SHALL 依光達即時偵測的障礙物調整路徑；新出現的障礙物擋住原路徑時 SHALL 繞行或重新規劃，不與其碰撞。

#### Scenario: 路上出現箱子
- **WHEN** 導航途中在車輛前方的路徑上放一個箱子，且旁邊仍有可通行的空間
- **THEN** 車輛不撞到箱子，繞過或改走其他路徑後抵達目標

### Requirement: 無法到達時回報失敗
目標無法到達（在障礙物內、在地圖外、路徑完全被擋）時，導航 SHALL 在嘗試脫困後停止車輛並回報失敗，不無限期重試。

#### Scenario: 目標在牆內
- **WHEN** 送出位於牆內的目標位姿
- **THEN** action 回報失敗，車輛停止

### Requirement: 導航指令走標準速度介面
導航產生的速度指令 SHALL 送到車輛的標準速度介面 `/<id>/cmd_vel`，與手動操作相同，經由車輛驅動的指令逾時保護。

#### Scenario: 導航停止後車輛停下
- **WHEN** 導航中停止導航的程序
- **THEN** 車輛在 1 秒內停下

### Requirement: 導航不依賴模擬
定位與導航 SHALL 只使用車輛的標準介面（`/<id>/scan`、`/<id>/odom`、TF、`/<id>/cmd_vel`），在模擬與真車上以相同方式執行；模擬時 SHALL 使用模擬時間。

#### Scenario: 模擬模式下導航
- **WHEN** 以 `hardware:=sim mode:=navigation` 啟動車子系統
- **THEN** 定位與導航節點皆使用模擬時間，且皆位於 namespace `amr1` 下
