# Design

## Context

- 地圖由 slam_toolbox 建、`map_saver_server` 存成 `.pgm` + `.yaml`（trinary：254 空曠、0 佔據、205 未知），放在 robot 容器的 `/data/maps`（主機 `docker/amr_sim/data/maps`）。`.yaml` 的 `origin` 是圖片**左下角**像素在 map 座標系的位置；Nav2 map_server 會讀 origin 的角度，但 costmap、AMCL 等多數元件忽略它，所以地圖不能靠 origin 角度轉向。
- 現行慣例「從出生點 (1, 1) 建圖、世界 = 地圖 + (1, 1)」寫在 add-navigation 的 design D4、README、筆記 16／17，以及導航冒煙測試的換算；main spec 沒有寫到這個慣例。
- 面板、存圖服務的既有做法見 add-navigation D11（服務在車上、面板只呼叫服務、名稱白名單、確認視窗）。

## Goals / Non-Goals

**Goals:** 掃圖不假設出生點；掃好後在 RViz 點選、拖曳即可把地圖原點標在倉庫的參考點；改寫後的地圖檔自己就是倉庫座標，Nav2 與之後的網頁直接使用。

**Non-Goals:** 掃圖中標原點；自動偵測牆的方向對齊；「還原」按鈕（先保留 `.bak` 檔，之後再加）；多張地圖之間的對齊。

## Decisions

### D1：改寫地圖檔本身（使用者選定）

- 選取的位姿 P=(px, py, θ) 以目前的地圖座標表示。新座標 `q' = R(−θ)(q − P)`。
- `.yaml`：`origin` 改為新圖片左下角在新座標的位置，角度一律寫 0；其他欄位保持不變。
- `.pgm`：θ = 0 時不改圖片；θ 為 90° 倍數時以 `numpy.rot90` 旋轉陣列（無損）；任意角度時以最近鄰重新取樣，新增區域補 205（未知），只會出現 0／205／254 三種值。
- 替代：另存轉換並發布 `warehouse` TF（多一層座標系，目標、儲位都要換算）；只改 origin（不能轉向）。

### D2：對齊 90° 倍數（預設開啟）

拖曳角度不可能剛好是 0°；照實際角度旋轉會讓幾乎是正的地圖被重新取樣。面板預設把角度取最近的 0／90／180／270°（無損），並即時顯示「拖曳 X° → 套用 Y°」；整張圖歪了才關掉選項。角度計算放在面板的靜態函式，gtest 測試。

### D3：元件與介面

| 元件 | 套件 | 內容 |
|---|---|---|
| `SetMapOrigin.srv` | 新 `amr_interfaces`（ament_cmake + rosidl_default_generators） | 請求 `string map_name`、`float64 x`、`float64 y`、`float64 yaw`；回應 `bool success`、`string message` |
| `map_origin.py` | `amr_navigation` | 純 Python + numpy：讀寫 PGM（P5）與 yaml、計算新 origin、旋轉／重新取樣、備份、原子寫入（mkstemp + os.replace，同 gen_world）。不依賴 ROS |
| `map_origin_server` | `amr_navigation`（console script） | 節點在 namespace `<id>` 下，服務 `map_origin/set`（`/<id>/map_origin/set`），參數 `maps_dir`（預設 `/data/maps`）；名稱白名單與存圖面板相同 |
| `MapOriginPanel` | `amr_rviz_plugins` | 訂閱 `/<id>/map_origin/candidate`（PoseStamped）顯示 x、y、拖曳角度與套用角度；「對齊 90° 倍數」勾選；「套用」→ 確認 → 非同步呼叫服務 → 成功後呼叫 map_server 的 `load_map`（nav2_msgs/LoadMap）重新載入 |
| `map_origin.rviz` | `amr_rviz_plugins` | Map（`/<id>/map_origin/map`）、Grid、Axes（原點）、Pose（候選箭頭）；工具：Move Camera、**設定原點**＝ SetGoal 改 topic 為 `/<id>/map_origin/candidate` |
| `map_origin_ui.launch.xml` | `amr_rviz_plugins` | 參數 `robot_id`、`map`；啟動 map_server（節點 `map_origin_viewer`、namespace `<id>`、topic `map_origin/map`、載入 `/data/maps/<map>.yaml`）＋ lifecycle_manager、`map_origin_server`、RViz |

- 「設定原點」工具重用 RViz 內建 SetGoal（只改 topic），不另寫工具外掛。
- 顯示用的 map_server 用獨立的節點名稱與 topic（`map_origin_viewer`、`map_origin/map`），和導航的 map_server（`/amr1/map`）不衝突；不需要世界與車子系統。
- 服務在車上、面板只呼叫服務（同 add-navigation D11）。

### D4：錯誤處理與備份

- 名稱不合法、地圖檔不存在或讀不了、PGM 格式不支援（只接受 P5、maxval 255）、寫檔失敗 → `success=false` 與訊息，原檔不變。
- 改寫前把 `<name>.pgm`、`<name>.yaml` 複製成 `<name>.bak.pgm`、`<name>.bak.yaml`（只保留最近一次）；`.gitignore` 加 `*.bak.pgm`、`*.bak.yaml`。
- 先把新內容寫到同目錄的暫存檔，兩個都寫成功才依序 `os.replace`。

### D5：repo 地圖 `warehouse_small` 的轉換

以同一服務（或模組）輸入精確值 (−1.0, −1.0, 0)：模擬倉庫的左下角在目前地圖座標 (−1, −1)（地圖從出生點 (1, 1) 開始建、車頭朝 +x）。轉換後地圖座標 = Gazebo 世界座標。用精確數字而非手點，是因為冒煙測試要拿它和 Gazebo 真實位置比對；這只用在幾何已知的模擬範例地圖上，掃圖流程本身不假設出生點。轉換後導航冒煙測試的初始位姿為出生點 (1, 1, 0)、可到達目標 (10, 1)、障礙物內目標 (7, 4)（皆為世界座標）。

### D6：測試

- pytest（無 ROS）：純平移時圖片逐位元組相同、origin 正確；90／180／270° 的三種值格數不變且等於 `rot90`；任意角度只有三種值、新增區域為未知；已知牆格的新座標正確；失敗時原檔不變；備份內容正確；名稱白名單。
- 服務節點：launch_testing 或 rclpy 測試，對暫存目錄的地圖呼叫服務並檢查結果與失敗回報。
- 面板 gtest：pluginlib 載入、元件存在、對齊角度計算。
- 靜態：`amr_interfaces`／`amr_navigation` 不依賴模擬套件；`map_origin.rviz` 工具 topic 帶 namespace；launch 內容。
- 整合：導航冒煙測試以轉換後的地圖、世界座標通過；`colcon test` 全部通過。
- 手動驗收：在複製出的地圖上以 UI 點選、套用，RViz 的座標軸移到新原點。

## Risks / Trade-offs

- [任意角度重新取樣，斜邊多 1 格鋸齒] → 預設對齊 90° 倍數；解析度 5 cm 影響小。
- [套用錯了] → `.bak` 備份；已進 git 的地圖可用 git 還原。
- [`load_map` 重新載入後 RViz 的 Map 顯示沒更新] → Map display 用 Transient Local；實作時驗證，必要時面板提示重新開啟。
- [新增自訂介面套件，之後的介面都放這裡] → 子專案 3、4 本來就需要，先建立。
