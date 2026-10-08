# 22 建圖面板（RViz 外掛）

檔案：[`mapping_panel.hpp`](../../ros_ws/src/amr_rviz_plugins/include/amr_rviz_plugins/mapping_panel.hpp)、[`mapping_panel.cpp`](../../ros_ws/src/amr_rviz_plugins/src/mapping_panel.cpp)、[`plugins_description.xml`](../../ros_ws/src/amr_rviz_plugins/plugins_description.xml)、[`CMakeLists.txt`](../../ros_ws/src/amr_rviz_plugins/CMakeLists.txt)、[`mapping_ui.launch.xml`](../../ros_ws/src/amr_rviz_plugins/launch/mapping_ui.launch.xml)、[`mapping.launch.xml`](../../ros_ws/src/amr_navigation/launch/mapping.launch.xml)（存圖服務）

子專案 2 task 6.1–6.3（使用者要求：建圖要有嵌入 RViz 的 GUI、用按鈕存圖）。

## 為什麼要做

原本存圖要在終端機打一長串 `map_saver_cli` 指令（還要記得 remap 和 use_sim_time）。操作員需要的是：看著地圖長出來，覺得可以了就輸入名字、按一下存檔。

做法的選擇：
- **RViz 面板外掛**（採用）：3D 顯示直接用 RViz，只加一塊面板；pluginlib 註冊後可以存進 `.rviz` 設定檔，一開就有。
- 自己寫視窗嵌入 RViz：ROS 2 的 RViz 沒有 Python 綁定，要用 C++ 直接操作 rviz_common 的渲染元件，複雜很多。
- slam_toolbox 自帶的 RViz 面板也有 Save Map 按鈕，但它寫死呼叫 `/slam_toolbox/save_map`，**不支援 namespace**（我們的車在 `/amr1`），不能用。

## 做了什麼

### 1. 存圖服務（task 6.1）

面板不直接寫檔，而是呼叫車上的服務。用 Nav2 現成的 `map_saver_server`（常駐的 lifecycle node，提供 `save_map` 服務），放進 `mapping.launch.xml`：

```xml
<group>
  <push-ros-namespace namespace="$(var robot_id)"/>
  <node pkg="slam_toolbox" exec="async_slam_toolbox_node" name="slam_toolbox" .../>
  <node pkg="nav2_map_server" exec="map_saver_server" name="map_saver" .../>        <!-- /amr1/map_saver/save_map -->
  <node pkg="nav2_lifecycle_manager" exec="lifecycle_manager" name="lifecycle_manager_mapping" .../>
</group>
```

- 服務介面 `nav2_msgs/srv/SaveMap`：`map_topic`、`map_url`（存放路徑，不含副檔名）、`image_format`、`map_mode`、門檻 → 回傳 `result`。
- 為什麼不讓面板自己寫檔：之後 RViz 開在操作員的筆電、建圖跑在車上時，地圖檔要存在車上（導航才讀得到）。服務在車上，面板在哪裡都一樣。
- 參數檔改名 `slam_toolbox.yaml` → `mapping.yaml`（多了 map_saver 與 lifecycle_manager 的參數）。改名後 colcon build 失敗——`build/` 裡指向舊檔的 symlink 還在（筆記 12 的老坑），刪掉該套件的 build／install 重建。

### 2. 面板外掛（task 6.2）

**新套件 `amr_rviz_plugins`**（ament_cmake、C++、Qt5）——操作員工具，不依賴模擬套件，也不是車上執行的系統。

RViz 外掛的三個要素：

| 要素 | 檔案 | 作用 |
|---|---|---|
| 類別繼承 `rviz_common::Panel` | `mapping_panel.hpp/.cpp` | 面板本身是一個 Qt 元件 |
| `PLUGINLIB_EXPORT_CLASS(amr_rviz_plugins::MappingPanel, rviz_common::Panel)` | `mapping_panel.cpp` | 告訴 pluginlib 這個類別可以被動態載入 |
| `plugins_description.xml` + `pluginlib_export_plugin_description_file(rviz_common ...)` | XML、CMakeLists | 登記到 ament index，RViz 啟動時列出可用的外掛 |

CMake 的重點：`set(CMAKE_AUTOMOC ON)`，並把標頭檔列進 `add_library`——有 `Q_OBJECT` 的類別要由 Qt 的 moc 產生 signal／slot 的程式碼，沒列標頭檔就不會處理，連結時找不到 vtable。

面板的行為：

```
┌ AMR 建圖 ─────────────────────┐
│ 車輛     [amr1           ]     │
│ 地圖名稱 [warehouse_small]     │
│ [           存圖           ]   │
│ 地圖 277 × 250，已知 5%，最後更新 0 秒前 │
│ 已存：/data/maps/ui_test.pgm／.yaml      │
└───────────────────────────────┘
```

- `onInitialize()`：RViz 建好 DisplayContext 後才呼叫，這時才能拿 ROS 節點（`getDisplayContext()->getRosNodeAbstraction().lock()->get_raw_node()`）。建構子裡還拿不到。
- 訂閱 `/<id>/map`（**Transient Local**，筆記 16）算尺寸和已知比例；`QTimer` 每秒刷新「最後更新 N 秒前」與按鈕狀態（服務沒就緒時按鈕反灰）。
- 按「存圖」：檢查名稱（只允許英數字 `_` `-`，防止 `../` 路徑穿越）→ `QMessageBox::question` 顯示完整路徑並提醒同名會覆蓋 → **非同步**呼叫服務（`async_send_request` + 回呼），不卡住 RViz 畫面。
- 執行緒：RViz 的 executor 在 Qt 主執行緒的更新迴圈裡 `spin_some`，所以訂閱與服務的回呼都在 Qt 執行緒，直接更新元件是安全的。
- `load()`／`save()`：車輛 id 與地圖名稱存進 `.rviz` 設定檔；欄位一改就發 `configChanged()`，RViz 關閉時會提醒存檔。

`navigate.rviz` 的 `Panels` 加入這個面板；`mapping_ui.launch.xml` 一次啟動建圖 + RViz（RViz 關掉時 `on_exit="shutdown"` 讓建圖一起結束）。這個 launch 放在 `amr_rviz_plugins` 而不是 `amr_navigation`：它啟動 RViz，車上的系統不該依賴 RViz。

### 3. 測試

- **gtest**：用 `pluginlib::ClassLoader<rviz_common::Panel>` 載入 `amr_rviz_plugins/MappingPanel` 並建立——和 RViz 找外掛的方式相同。Qt 設 `QT_QPA_PLATFORM=offscreen`，沒有螢幕也能建立元件；檢查輸入框、按鈕、狀態列都在。另測名稱驗證（`../etc/passwd`、`a/b`、空白、中文都拒絕）。
- **pytest**：外掛描述檔與 `PLUGINLIB_EXPORT_CLASS` 一致、沒有模擬套件相依、面板的存圖目錄 = 導航載入地圖的目錄（`/data/maps`）、面板呼叫的服務名稱對應建圖 launch 裡名為 `map_saver` 的節點、`navigate.rviz` 含面板、`mapping_ui.launch.xml` 的內容。
- **建圖冒煙測試**新增 test_06：呼叫 `/amr1/map_saver/save_map` 存到暫存目錄，`.pgm`／`.yaml` 產生。

## 怎麼驗證（2026-10-08 實測）

```bash
colcon test && colcon test-result --all      # 171 tests, 0 failures（6 個套件）
```

RViz 需要螢幕，`QT_QPA_PLATFORM=offscreen` 時 Ogre 建不出 OpenGL 視窗，RViz 直接中止（-6）。為了不在使用者桌面跳出視窗，在 robot 容器裡**暫時**裝 Xvfb（虛擬 X server，容器重建就消失），用軟體渲染開 RViz、截圖：

1. 面板顯示在左下角；開車後狀態更新為「地圖 277 × 250，已知 5%，最後更新 0 秒前」，地圖與光達、車身都在。
2. 用 xdotool 把地圖名稱改成 `ui_test`（避免覆蓋正式地圖）、按「存圖」→ 確認視窗列出 `/data/maps/ui_test.pgm`、`.yaml` 並提醒覆蓋 → Enter（預設 Yes）。
3. `/data/maps/ui_test.{pgm,yaml}` 產生，面板顯示「已存：/data/maps/ui_test.pgm／.yaml」；`warehouse_small` 未被動到。

## 面試追問

**Q：RViz 外掛怎麼寫？**
A：繼承對應的基底類別（Panel、Display、Tool），`PLUGINLIB_EXPORT_CLASS` 匯出，寫 plugin description XML 並用 `pluginlib_export_plugin_description_file` 登記到 ament index；RViz 啟動時透過 pluginlib 列出並動態載入 `.so`。Qt 類別要開 AUTOMOC。

**Q：GUI 裡呼叫 ROS 服務要注意什麼？**
A：不能在 GUI 執行緒同步等待結果（畫面會卡住）；用非同步呼叫 + 回呼。要知道回呼在哪個執行緒執行：RViz 是在 Qt 主執行緒 spin，可以直接改元件；如果是自己開執行緒 spin，就要用 Qt 的 signal 或 `QMetaObject::invokeMethod` 回到 GUI 執行緒。

**Q：為什麼存圖要做成服務而不是 GUI 直接寫檔？**
A：分散式部署時 GUI 和車不在同一台電腦，地圖要存在車上；服務讓「誰來存」和「誰按按鈕」解耦，也方便之後網頁（子專案 3）用同一個服務。

**Q：使用者輸入的檔名要怎麼處理？**
A：白名單驗證（只允許英數字、底線、連字號），不要直接拼進路徑——否則 `../` 可以寫到任意位置。覆蓋前要確認。

**Q：沒有螢幕的環境怎麼測 GUI？**
A：單元層級用 Qt 的 offscreen 平台建立元件、檢查狀態；要看真正的畫面就用 Xvfb（虛擬 X server）加軟體 OpenGL，搭配 xdotool 模擬點擊、截圖。

## 踩坑紀錄

- **參數檔改名後 colcon build 失敗**：`build/` 留著指向舊檔的 symlink。刪該套件的 build、install 重建。
- **RViz 在 offscreen 平台會中止**：Ogre 需要真的 OpenGL 視窗；改用 Xvfb + 軟體渲染。
- **Xvfb 下整張截圖時對話框是黑的**：沒有視窗管理器／合成器，`xwd -root` 抓不到對話框內容；用 `xdotool search --name` 找到視窗、`import -window <id>` 單獨截圖。
- **建圖畫面的 Global／Local Costmap 顯示警告**：costmap 只在導航時存在，建圖時沒有資料，屬正常（README 有寫）。
- **停止時 RViz 被強制結束**：軟體渲染下 RViz 收到 SIGINT 後 10 秒內沒結束；只發生在 Xvfb 測試環境。
