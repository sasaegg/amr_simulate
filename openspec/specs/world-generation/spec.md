# world-generation Specification

## Purpose

讓使用者以人類可讀的 YAML 檔描述倉庫場景（尺寸、牆、貨架、障礙物），並轉換成 Gazebo Fortress 可直接載入的 world，使地圖可被編輯、比對與版本控制。

## Requirements

### Requirement: 由 YAML 場景描述產生 world
系統 SHALL 提供一個指令，接受一個場景 YAML 檔路徑，輸出一個 Gazebo Fortress 可載入的 SDF world 檔。輸出檔名 SHALL 與場景 `name` 欄位一致（`<name>.sdf`），輸出位置為 world 目錄。

#### Scenario: 產生範例場景
- **WHEN** 使用者對 `warehouse_small.yaml` 執行產生指令
- **THEN** 產生 `warehouse_small.sdf`，且 Gazebo Fortress 載入時不報錯

#### Scenario: 重複產生結果一致
- **WHEN** 對同一份未修改的 YAML 連續執行兩次產生指令
- **THEN** 兩次輸出內容逐位元組相同

### Requirement: 產生器不依賴 ROS 執行環境
產生器與其測試 SHALL 能在只安裝 Python 3 與 PyYAML、未 source 任何 ROS 環境的情況下執行。

#### Scenario: 在純 Python 環境執行測試
- **WHEN** 在未 source ROS 的 shell 中執行產生器的測試
- **THEN** 測試可以執行並通過

### Requirement: 自動產生外牆與地板
系統 SHALL 依場景 `size: [寬, 長]`（公尺）產生一個覆蓋該範圍的地板，以及沿四周邊界的封閉外牆；場景座標原點為地板左下角，x 軸沿寬、y 軸沿長。

#### Scenario: 外牆封閉
- **WHEN** 場景 `size` 為 `[20, 15]`
- **THEN** world 中包含一片 20×15 m 地板與四面外牆，車輛無法從場景內任何位置駛出邊界

### Requirement: 支援牆、貨架與障礙物元素
系統 SHALL 支援以下元素類型並將其轉為 world 中的靜態物體：`walls`（由 `from`、`to` 兩點、`thickness`、`height` 定義的線段牆）、`shelves`（`pos`、`yaw`、`size: [長, 寬, 高]`）、`obstacles`（`type: box | cylinder`、`pos` 與對應尺寸）。所有元素 SHALL 同時具備可見外觀與碰撞體，以便光達可偵測。

#### Scenario: 貨架被光達看見
- **WHEN** 場景中定義一個位於 `[3, 8]` 的貨架，車輛面向該貨架
- **THEN** 車輛的光達量測中出現對應該貨架位置的障礙點

#### Scenario: 省略的可選欄位使用預設值
- **WHEN** 一面牆未指定 `thickness` 與 `height`
- **THEN** 系統使用預設厚度 0.2 m、高度 2.0 m

### Requirement: 輸入驗證與錯誤回報
系統 SHALL 在產生前驗證 YAML；遇到缺少必要欄位、型別錯誤、數值不合理（尺寸 ≤ 0）、元素超出場景邊界、或含有已移除的 `spawn` 欄位時，SHALL 不輸出 world 檔，並以非零結束碼回報指出問題元素與欄位的錯誤訊息。

#### Scenario: 缺少必要欄位
- **WHEN** YAML 缺少 `size` 欄位
- **THEN** 指令以非零碼結束，訊息指出缺少 `size`，且不產生任何 `.sdf` 檔

#### Scenario: 元素超出邊界
- **WHEN** 一個貨架的位置在場景 `size` 範圍之外
- **THEN** 指令以非零碼結束，訊息指出是哪一個貨架（索引）超出邊界

#### Scenario: 場景不再定義出生點
- **WHEN** 場景 YAML 含有 `spawn` 欄位
- **THEN** 指令以非零碼結束，訊息指出出生點改在啟動車子系統時指定

#### Scenario: 驗證失敗不覆蓋既有輸出
- **WHEN** 已存在 `warehouse_small.sdf`，使用者把 YAML 改壞後執行產生指令
- **THEN** 指令以非零碼結束，既有的 `warehouse_small.sdf` 內容不變

### Requirement: 手動微調版本不被覆蓋
產生指令 SHALL 只寫入 `<name>.sdf`；使用者在 Gazebo GUI 中另存的 world（例如 `<name>_edited.sdf`）SHALL 可被啟動時指定載入，且不會被產生指令覆寫。

#### Scenario: 載入手動微調的 world
- **WHEN** 使用者啟動模擬時指定 world 為 `warehouse_small_edited`
- **THEN** Gazebo 載入該檔，且重新執行產生指令後該檔內容不變
