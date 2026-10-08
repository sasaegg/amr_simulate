# 18 AMCL 定位

檔案：[`nav2.yaml`](../../ros_ws/src/amr_navigation/config/nav2.yaml)（定位段落）、[`navigation.launch.xml`](../../ros_ws/src/amr_navigation/launch/navigation.launch.xml)、[`test_navigation_config.py`](../../ros_ws/src/amr_navigation/test/test_navigation_config.py)

子專案 2 task 3.1。

## 為什麼要做

建圖完成後，地圖是固定的，不需要再跑 SLAM；只要回答「我在這張地圖的哪裡」。這就是定位（localization）。Nav2 的標準做法：

- **map_server**：讀 `.yaml` + `.pgm`，發布 `/amr1/map`（Transient Local）
- **AMCL**（Adaptive Monte Carlo Localization）：用粒子濾波器，比對光達和地圖，發布 `map → amr1/odom`

建圖和定位分開：建圖用 slam_toolbox（會改地圖），導航時用 AMCL（地圖不變，計算量小、行為可預期）。

## 做了什麼

### AMCL 原理（粒子濾波器）

1. **粒子**：每個粒子是一個「車子可能在這裡」的假設（x, y, yaw）。給初始位姿時，在該點附近撒 500–2000 個粒子。
2. **預測**：車子移動時，每個粒子依 odom 的位移移動，並加上雜訊（`alpha1`～`alpha5` 描述 odom 有多不可信）。
3. **更新**：拿目前的光達掃描，對每個粒子算「如果車在這裡，看到這筆掃描的機率」（`likelihood_field` 模型：光束端點離地圖上的障礙物越近機率越高）。
4. **重新取樣**：機率高的粒子複製、低的淘汰。粒子逐漸聚集到真實位置。
5. **Adaptive**：粒子收斂時自動減少數量（KLD sampling，`pf_err`、`pf_z`），省 CPU。

`update_min_d: 0.25`、`update_min_a: 0.2`：車子移動 0.25 m 或轉 0.2 rad 才做一次更新——停著不動時不會一直算，也避免粒子在原地過度收斂。

### 參數（以官方為起點）

| 參數 | 值 | 原因 |
|---|---|---|
| `global_frame_id`／`odom_frame_id`／`base_frame_id` | `map`／`amr1/odom`／`amr1/base_footprint` | frame 帶前綴（筆記 15） |
| `scan_topic` | `/amr1/scan` | |
| `set_initial_pose` | false | 初始位姿由使用者在 RViz 點（2D Pose Estimate） |
| `laser_min/max_range` | 0.12／12.0 | 和光達規格一致（官方 -1／100） |
| `robot_model_type` | DifferentialMotionModel | 差速車（另一種是全向輪 Omni） |
| `max_beams` | 60 | 360 點中取 60 點算機率，夠用 |

### launch：push-ros-namespace 與 lifecycle_manager

```xml
<group>
  <push-ros-namespace namespace="$(var robot_id)"/>
  <node pkg="nav2_map_server" exec="map_server" name="map_server"> ... </node>
  <node pkg="nav2_amcl" exec="amcl" name="amcl"> ... </node>
  <node pkg="nav2_lifecycle_manager" exec="lifecycle_manager" name="lifecycle_manager_localization"> ... </node>
</group>
```

- **`<push-ros-namespace>`**：group 內所有節點都加上 namespace，不用每個 `<node>` 都寫 `namespace=`。等 4.1 加入 7 個導航節點時更省事。
- **lifecycle_manager**：Nav2 節點都是 lifecycle node，啟動後停在 unconfigured。lifecycle_manager 依 `node_names` 順序做 configure → activate；任何一個失敗就停下（例如地圖找不到），不會帶著壞掉的元件繼續跑。
- **不 remap `/tf`**：官方 localization launch 把 `/tf` remap 成相對的 `tf`（每台車一棵獨立的 TF 樹）。我們的設計是所有車共用全域 `/tf`、靠 frame 前綴區分，所以不 remap。
- **地圖路徑**：`<param name="yaml_filename" value="/data/maps/$(var map).yaml"/>`，launch 參數 `map` 只給名字。

### 靜態測試（25 項，含 2.1 的建圖測試）

通用的檢查，4.1 加入導航節點後一樣適用：
- launch 裡每個節點在參數檔都有對應的完整名稱鍵
- 每個節點都由 launch 設 `use_sim_time`，參數檔不寫
- 所有 lifecycle node 恰好被一個 lifecycle_manager 管理（漏掉的節點會一直停在 unconfigured）
- frame 只能是 `map` 或 `<id>/…`（以 amr1、amr2 各檢查一次）
- AMCL 光達距離和 xacro 一致

## 怎麼驗證（2026-10-08 實測）

正式地圖等使用者建（task 2.3），先用腳本自動開一圈建的暫時地圖 `dev_tmp` 開發（不進 git）。

用腳本發 `/amr1/initialpose`（和 RViz 2D Pose Estimate 發的是同一種訊息）。車在世界 (1, 1)，地圖從那裡開始建，所以地圖座標是 (0, 0, 0)：

| 時機 | AMCL 估計 | Gazebo 真實（換算成地圖座標） | 誤差 |
|---|---|---|---|
| 給初始位姿前 | `map → base_footprint` 查不到 | | |
| 給初始位姿後 1.1 s | (0.02, 0.04, 0°) | (0.00, 0.00, 0°) | 4.5 cm |
| 直行、左轉 90°、直行約 5.4 m | (2.82, 2.64, 92°) | (2.79, 2.64, 91°) | 3.2 cm、1° |

`ros2 lifecycle get /amr1/map_server`、`/amr1/amcl` 皆為 `active`。`map:=nope` 時：`Failed to load map yaml file: /data/maps/nope.yaml`，map_server configure 失敗，AMCL 沒有被帶起。

## 面試追問

**Q：AMCL 和 SLAM 差在哪？什麼時候用哪個？**
A：SLAM 同時建圖和定位，地圖會變；AMCL 只定位，地圖固定。環境已知且不常變（倉庫）時，先建一次圖，之後用 AMCL，計算量小、結果穩定、也方便在地圖上標儲位。

**Q：粒子濾波器的步驟？**
A：撒粒子 → 依 odom 移動（加雜訊）→ 依感測器觀測算權重 → 依權重重新取樣。AMCL 的 adaptive 是依粒子分布自動調整粒子數（KLD sampling）。

**Q：AMCL 為什麼發 `map → odom` 而不是 `map → base_link`？**
A：和 SLAM 一樣，TF 是樹，`odom → base_link` 已經由里程計發布。AMCL 算出車在地圖的位置後，反推「odom 原點在地圖的哪裡」發布出去。

**Q：初始位姿給錯會怎樣？什麼是 kidnapped robot problem？**
A：粒子都撒在錯的地方，比對不起來，估計會錯或發散。車被搬到別處（kidnapped）時 AMCL 不會自己發現，要重新給初始位姿，或開啟 `recovery_alpha_*` 讓它在權重下降時往全域隨機撒粒子。

**Q：lifecycle node 有什麼好處？**
A：啟動順序可控：先全部 configure（讀參數、配置資源），都成功才 activate；某個元件失敗可以整組停下，不會半套運作。也方便執行中重新設定或關閉某個元件。

## 踩坑紀錄

- **自動建圖第一次失敗，地圖疊成好幾份**：查到是車輛模型的問題——輪子碰撞形狀用圓柱，有效輪距變小，原地旋轉多轉約 10%，odom 漂移（詳見筆記 17）。改成球形碰撞後 `map → odom` 修正量整趟都在 4 cm、0.4° 內。
- **腳本發的 initialpose 出現 extrapolation 警告**：時間戳填 0，AMCL 以最新時間查 TF 時差了幾毫秒。RViz 會填正確時間；仍能正常收斂。
- **開發時用的路徑點腳本以 odom 判斷位置**，車子卡住時輪子空轉、odom 照樣累加，腳本還以為到了。比對位置一律用 Gazebo 真實值（`ign model -m amr1 -p`）。
