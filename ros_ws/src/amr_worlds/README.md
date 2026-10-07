# amr_worlds

以 YAML 描述倉庫場景，產生 Gazebo Fortress 可載入的 SDF world。

```
scenes/<name>.yaml  ──gen_world──▶  worlds/<name>.sdf  ──▶  ign gazebo / sim.launch.py
```

## 產生 world

在容器內（`docker/amr_sim/exec.sh` 進入）：

```bash
ros2 run amr_worlds gen_world /ros_ws/src/amr_worlds/scenes/warehouse_small.yaml
# → /ros_ws/src/amr_worlds/worlds/warehouse_small.sdf
```

- 輸出檔名取自 YAML 的 `name`，不是 YAML 的檔名。
- 預設輸出到場景檔上一層的 `worlds/`；可用 `--out-dir <資料夾>` 指定。
- 驗證失敗時以非零結束碼結束、錯誤訊息印到 stderr，**不會寫入或覆蓋任何檔案**。
- 同一份 YAML 每次產生的內容逐位元組相同，`.sdf` 納入版控，可用 `git diff` 檢查變更。
- 產生器不依賴 ROS：`python3 -m amr_worlds.gen_world <yaml>`（在本套件目錄執行）也可以。

預覽：

```bash
ign gazebo /ros_ws/src/amr_worlds/worlds/warehouse_small.sdf
```

新增場景檔或 `.sdf` 後要重新 `colcon build`，才會安裝到 `share/amr_worlds/`（`setup.py` 的 `glob` 在 build 時執行）。

## 場景 YAML 格式

座標原點在地板左下角，x 往右、y 往上；長度單位公尺、角度單位弧度。

```yaml
name: warehouse_small          # 必填。只能用英數字、底線、連字號（會當檔名）
size: [20, 15]                 # 必填。地板 [寬(x), 長(y)]，皆 > 0

walls:                         # 選填。內牆（線段）
  - {from: [12, 6], to: [12, 15]}
  - {from: [15, 9], to: [20, 9], thickness: 0.3, height: 1.5}

shelves:                       # 選填。貨架（長方體）
  - {pos: [3, 8], yaw: 0, size: [2.0, 0.6, 1.8]}

obstacles:                     # 選填。障礙物
  - {type: box, pos: [7, 4], yaw: 0.5, size: [1.0, 1.0, 1.0]}
  - {type: cylinder, pos: [17, 12], radius: 0.3, height: 1.2}

spawn:                         # 選填。車輛出生位姿
  amr1: [1, 1, 0]              # [x, y, yaw]
```

| 元素 | 欄位 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `walls[]` | `from`、`to` | ✅ | | 牆的兩端點 `[x, y]`，不能相同 |
| | `thickness` | | `0.2` | 厚度，> 0 |
| | `height` | | `2.0` | 高度，> 0 |
| `shelves[]` | `pos` | ✅ | | 中心 `[x, y]` |
| | `size` | ✅ | | `[長, 寬, 高]`，皆 > 0；`yaw: 0` 時長邊沿 x 軸 |
| | `yaw` | | `0` | 繞 z 軸旋轉 |
| `obstacles[]` | `type` | ✅ | | `box` 或 `cylinder` |
| | `pos` | ✅ | | 中心 `[x, y]` |
| （box） | `size` | ✅ | | `[長, 寬, 高]`，皆 > 0 |
| （box） | `yaw` | | `0` | 繞 z 軸旋轉 |
| （cylinder） | `radius`、`height` | ✅ | | 皆 > 0 |
| `spawn` | `<robot_id>` | | | `[x, y, yaw]` |

自動產生、不必寫在 YAML 裡：

- **地板**：`size` 大小、0.1 m 厚，頂面在 z = 0。
- **四面外牆**：厚 0.2 m、高 2.0 m，放在地板外側，內側面貼齊邊界——可用空間剛好是 `size`。

### 驗證規則

產生前會檢查，任一條不符就報錯並指出位置（例如 `shelves[0].size[1]: 必須 > 0`）：

- 必填欄位存在、型別正確（數字不接受 `true`／`false`）、尺寸 > 0。
- 元素在地板範圍內：牆看兩端點；貨架與 box 看旋轉後的四個角；圓柱看半徑範圍。
- 出生點距外牆內側面與每個元素的佔地邊緣都 **≥ 0.35 m**（訊息會指出衝突的元素，例如 `spawn.amr1: 距 obstacles[0] 僅 0.20 m`）。

## 產生的 SDF 結構

```
<world name="<name>">
  physics、系統外掛（Physics、UserCommands、SceneBroadcaster、Sensors(ogre2)、Imu）、sun
  <model name="warehouse"> static
    floor、outer_wall_0（南）~ outer_wall_3（西）
    wall_<i>、shelf_<i>、obstacle_<i>     ← 依 YAML 中的順序編號
```

每個 link 同時有 `collision`（物理與光達偵測）與 `visual`（外觀），幾何相同。

## 編輯流程：YAML 與 GUI 另存

- **結構變更**（加減牆、貨架、障礙物、改尺寸）：改 YAML → 重新產生。
- **細節微調**（燈光、材質、加入 Gazebo 模型庫的物件）：在 Gazebo GUI 中修改後另存為 `worlds/<name>_edited.sdf`。產生器只會寫 `<name>.sdf`，**永遠不會覆蓋 `_edited.sdf`**。
- 兩者不會自動同步：`_edited.sdf` 視為 YAML 的衍生分支；YAML 改了之後，需要的話再從新的 `.sdf` 重新微調。
