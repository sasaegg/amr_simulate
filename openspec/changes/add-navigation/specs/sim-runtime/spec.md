# Spec Delta

## ADDED Requirements

### Requirement: 車子系統的功能模式
車子系統 SHALL 依啟動參數 `mode` 決定同時帶起的功能：`none`（預設，只有驅動與共用節點）、`mapping`（建圖）、`navigation`（定位與導航）。不合法的值 SHALL 顯示訊息（含收到的值與可用值）並結束，不啟動任何節點。建圖與導航 SHALL 也能在車子系統執行中單獨啟動與停止，不需重啟驅動。

#### Scenario: 預設不帶建圖或導航
- **WHEN** 以 `hardware:=sim` 啟動車子系統，沒有指定 `mode`
- **THEN** 沒有建圖或導航節點，也沒有 `map` 座標系

#### Scenario: 以模式一次啟動
- **WHEN** 以 `hardware:=sim mode:=navigation` 啟動車子系統
- **THEN** 驅動、共用節點與導航節點都啟動

#### Scenario: 不合法的模式
- **WHEN** 以 `hardware:=sim mode:=foo` 啟動車子系統
- **THEN** 訊息指出 `mode` 必須是 `none`、`mapping` 或 `navigation` 並顯示收到的值，沒有啟動任何節點即結束

#### Scenario: 單獨切換建圖與導航
- **WHEN** 車子系統以 `mode:=none` 執行中，使用者另外啟動建圖，之後停止建圖再另外啟動導航
- **THEN** 驅動在過程中持續執行，車輛留在原地，不被移回出生點

## MODIFIED Requirements

### Requirement: 執行設定
兩個容器共用的 ROS 環境變數（含 `ROS_DOMAIN_ID`）SHALL 放在專案 `docker/amr_sim/config/` 的一個環境變數檔；世界與車子系統的設定（world、headless、hardware、robot_id、出生位姿、mode、map）SHALL 以 launch 參數傳入，各參數的預設值寫在 launch 檔中。執行中產生的資料（地圖）SHALL 存放在專案的 `docker/amr_sim/data/` 目錄，以可寫方式掛載到 robot 容器的 `/data`，存入的檔案在主機上屬於使用者。

#### Scenario: 兩個容器取得相同 domain
- **WHEN** 使用者把環境變數檔中的 `ROS_DOMAIN_ID` 改為 42 並重建容器，再分別進入 `sim` 與 `robot` 執行 `ros2 topic list`
- **THEN** 兩個 shell 的 `ROS_DOMAIN_ID` 皆為 42，且在 `robot` 中可看到 `sim` 發布的 `/clock`

#### Scenario: 地圖存到主機
- **WHEN** robot 容器內的程序在 `/data/maps/` 寫入地圖檔
- **THEN** 檔案出現在主機的 `docker/amr_sim/data/maps/`，擁有者為主機使用者
