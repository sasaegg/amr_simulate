# Proposal

## Why

slam_toolbox 以「開始建圖時車輛的位置」當地圖原點，所以地圖座標取決於車子從哪裡出發。原本以「一律從出生點 (1, 1) 開始建圖、世界座標 = 地圖座標 + (1, 1)」的慣例處理，等於掃圖時預設知道出生點，也讓儲位、派車等之後的功能綁在建圖起點上。使用者要求：掃圖時不假設出生點，掃好後再手動把地圖原點標在倉庫的固定參考點，地圖座標就成為「倉庫座標」。

## What Changes

- 新增「標地圖原點」：在存好的地圖上以 RViz 點選原點位置、拖曳 x 軸方向，按「套用」改寫地圖檔，使選取的點成為 (0, 0)、拖曳方向成為 +x。
  - 新套件 `amr_interfaces`：自訂服務 `SetMapOrigin.srv`。
  - `amr_navigation`：純 Python 的地圖改寫模組（平移、90° 倍數無損旋轉、任意角度最近鄰重新取樣），以及提供 `/map_origin/set` 的服務節點（和車輛無關，不帶車輛 namespace）；改寫前備份、原子寫入。
  - `amr_rviz_plugins`：「AMR 地圖原點」面板（選取結果、對齊 90° 倍數、套用與確認、結果）、`map_origin.rviz`、`map_origin_ui.launch.xml`。
- repo 的 `warehouse_small` 地圖以同一服務把原點改為倉庫左下角（地圖座標 = Gazebo 世界座標）；導航冒煙測試改以世界座標給初始位姿與目標，移除 (1, 1) 換算。
- 文件：README 新增「5.3 標地圖原點」並移除 (1, 1) 慣例；學習筆記 25。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities
- `mapping`：新增在存好的地圖上標原點的服務與 RViz 面板。

## Impact

- 新套件 `ros_ws/src/amr_interfaces`（ament_cmake、rosidl）；`amr_navigation` 新增模組、節點、相依；`amr_rviz_plugins` 新增面板、設定檔、launch。
- `docker/amr_sim/data/maps/warehouse_small.{pgm,yaml}` 原點改變；`.gitignore` 加入 `*.bak.pgm`、`*.bak.yaml`。
- `amr_hw_sim/test/test_navigation_smoke.py` 改用世界座標。
- 不需重建映像（numpy 1.21、rosidl 已在映像中）。
