# 學習筆記

子專案 1（OpenSpec change `add-sim-environment`，筆記 00–14）與子專案 2（`add-navigation`，筆記 15 起）每個實作步驟一篇。每篇固定段落：

- **為什麼要做**：這一步解決什麼問題
- **做了什麼**：指令／檔案，逐段解釋
- **怎麼驗證**：指令與預期輸出
- **面試追問**：可能被問到的問題與答案
- **踩坑紀錄**：實際遇到的錯誤與解法（沒有則省略）

| # | 主題 | 對應 task |
|---|---|---|
| 00 | [git 與換行設定](00-git與換行設定.md) | 1.1 |
| 01 | [docker 群組](01-docker群組.md) | 1.2 |
| 02 | [NVIDIA 驅動](02-NVIDIA驅動.md) | 1.3 |
| 03 | [NVIDIA Container Toolkit](03-NVIDIA-Container-Toolkit.md) | 1.4 |
| 04 | [Dockerfile](04-Dockerfile.md) | 2.1 |
| 05 | [entrypoint](05-entrypoint.md) | 2.2 |
| 06 | [compose：容器內的 GPU 與 X11](06-compose與容器內GPU-X11.md) | 2.3–2.5 |
| 07 | [ROS 工作區與 colcon](07-ROS工作區與colcon.md) | 3.1 |
| 08 | [場景產生器（TDD）](08-場景產生器TDD.md) | 3.2–3.5 |
| 09 | [車輛 xacro 與外掛](09-車輛xacro與外掛.md) | 4.1–4.2 |
| 10 | [bridge 與 watchdog](10-bridge與watchdog.md) | 5.1–5.3 |
| 11 | [世界與車子系統分離（三個 launch）](11-世界與車子系統分離.md) | 5.4–5.12 |
| 12 | [冒煙測試](12-冒煙測試.md) | 6.1 |
| 13 | [README 與最終驗收](13-README與最終驗收.md) | 7.1–7.2 |
| 14 | [launch 改為 XML（ROS 1 對照）](14-launch改為XML.md) | 5.13 |

### 子專案 2：建圖、定位、導航

| # | 主題 | 對應 task |
|---|---|---|
| 15 | [導航套件、參數代換與執行資料目錄](15-導航套件與參數代換.md) | 1.1–1.3 |
| 16 | [slam_toolbox 建圖](16-slam_toolbox建圖.md) | 2.1、2.2、2.4、2.5 |
| 17 | [存圖與地圖格式（含輪子碰撞修正）](17-存圖與地圖格式.md) | 2.3 |
| 18 | [AMCL 定位](18-AMCL定位.md) | 3.1 |
| 19 | [Nav2 架構與 lifecycle](19-Nav2架構與lifecycle.md) | 4.1 |
| 20 | [costmap、DWB 與導航冒煙測試](20-costmap與DWB.md) | 4.2–4.4 |
| 21 | [中控模式整合](21-中控模式整合.md) | 5.1–5.2 |
| 22 | [建圖面板（RViz 外掛）](22-建圖面板RViz外掛.md) | 6.1–6.3 |
| 23 | [子專案 2 最終驗收](23-子專案2最終驗收.md) | 7.1 |

### 之後的修改

| # | 主題 | change |
|---|---|---|
| 24 | [啟動腳本合併（up.sh）](24-啟動腳本合併.md) | unify-up-script |
| 25 | [標地圖原點](25-標地圖原點.md) | add-map-origin |

### 子專案 3：網頁派車（change `add-web-dispatch`）

| # | 主題 | task |
|---|---|---|
| 26 | [server 容器與映像](26-server容器與映像.md) | 1.1–1.2 |
| 27 | [後端骨架與 rclpy／FastAPI 共存](27-後端骨架與rclpy-FastAPI共存.md) | 2.1、3.2 |
| 28 | [RobotBridge：TF 查位置、action client 狀態機](28-RobotBridge.md) | 3.1 |
| 29 | [REST 與 WebSocket（FastAPI）](29-REST與WebSocket.md) | 2.2 |
| 30 | [前端骨架與 SVG 座標系](30-前端骨架與SVG座標系.md) | 4.1 |
| 31 | [拖曳派車與設定初始位姿](31-拖曳派車與初始位姿.md) | 4.2 |
| 32 | [端到端冒煙測試與 README](32-端到端冒煙測試與README.md) | 3.3、4.3 |
