# Spec Delta

## Purpose

定義模擬 AMR 對 ROS 2 其他元件（SLAM、Nav2、後端）公開的介面：速度指令、里程計、感測器資料、座標轉換與模擬時間，並以 namespace 隔離以支援未來多車。這組介面即「硬體介面」：模擬時由虛擬驅動提供，真車上由真實驅動提供相同的 topic。

## ADDED Requirements

### Requirement: 以 namespace 隔離車輛介面
每台模擬車的所有 topic SHALL 位於 `/<robot_id>/` 之下，所有該車的 TF frame SHALL 以 `<robot_id>/` 為前綴（例如 `amr1/base_link`）。第一版 SHALL 提供 `robot_id = amr1`。全域共用的 `/tf`、`/tf_static`、`/clock` 不在此限。

#### Scenario: topic 帶 namespace
- **WHEN** 模擬啟動後列出 ROS topic
- **THEN** 出現 `/amr1/cmd_vel`、`/amr1/odom`、`/amr1/scan`、`/amr1/imu`、`/amr1/joint_states`，且不存在未帶 namespace 的 `/cmd_vel`、`/odom`、`/scan`、`/imu`、`/joint_states`

### Requirement: 接受速度指令移動
車輛 SHALL 訂閱 `/<robot_id>/cmd_vel`（`geometry_msgs/Twist`），以差速運動學依線速度 `linear.x` 與角速度 `angular.z` 移動；線速度上限 1.0 m/s、角速度上限 1.5 rad/s，超過者 SHALL 被截斷至上限。

#### Scenario: 鍵盤遙控
- **WHEN** 使用者以 teleop 工具向 `/amr1/cmd_vel` 發送前進指令
- **THEN** 車輛在 Gazebo 中向前移動，`/amr1/odom` 的位置隨之改變

#### Scenario: 超速指令被截斷
- **WHEN** 向 `/amr1/cmd_vel` 持續發送 `linear.x = 5.0`
- **THEN** `/amr1/odom` 回報的線速度不超過 1.0 m/s

### Requirement: 指令逾時停車
若 0.5 秒內未收到新的速度指令，車輛 SHALL 停止，且停止後 SHALL 不持續重複送出停車指令。

#### Scenario: 指令來源中斷
- **WHEN** 車輛移動中且 teleop 程式被關閉
- **THEN** 車輛在 1 秒內速度降為 0

### Requirement: 發布里程計與 TF
車輛 SHALL 以至少 20 Hz 發布 `/<robot_id>/odom`（`nav_msgs/Odometry`），並在 `/tf` 發布 `<robot_id>/odom → <robot_id>/base_footprint` 轉換；車體各部件與感測器 frame 的固定轉換 SHALL 發布於 `/tf_static`。

#### Scenario: TF 樹完整
- **WHEN** 模擬執行中查詢 `amr1/odom` 到 `amr1/laser_link` 的轉換
- **THEN** 可取得有效轉換

### Requirement: 2D 光達
車輛 SHALL 以 10 Hz 發布 `/<robot_id>/scan`（`sensor_msgs/LaserScan`），水平 360°、量測範圍 0.12–12 m，frame 為 `<robot_id>/laser_link`。

#### Scenario: 掃描反映環境
- **WHEN** 車輛距離正前方牆面 2 m
- **THEN** 對應正前方角度的量測值約為 2 m（誤差 ±0.1 m）

### Requirement: IMU
車輛 SHALL 以 100 Hz 發布 `/<robot_id>/imu`（`sensor_msgs/Imu`），frame 為 `<robot_id>/imu_link`。

#### Scenario: 原地旋轉
- **WHEN** 車輛以固定角速度原地旋轉
- **THEN** IMU 的 `angular_velocity.z` 與指令角速度同號且量級相近

### Requirement: 模擬時間
模擬 SHALL 發布 `/clock`，所有車輛資料的時間戳 SHALL 使用模擬時間，以便下游節點設定 `use_sim_time`。

#### Scenario: 時間戳來自模擬時鐘
- **WHEN** 在 Gazebo 中暫停模擬
- **THEN** `/clock` 停止前進，且 `/amr1/odom` 不再發布新時間戳的訊息

### Requirement: 出生位姿
模擬模式下，車輛 SHALL 在車子系統啟動時出現在啟動參數 `x`、`y`、`yaw` 指定的位姿（公尺、弧度）；未指定的參數 SHALL 為 0。世界（場景）本身不定義車輛的出生位置。

#### Scenario: 車輛於指定位姿出生
- **WHEN** 以 `hardware:=sim x:=1 y:=1 yaw:=0` 啟動車子系統
- **THEN** `amr1` 出現在 (1, 1) 且車頭朝 +x 方向

#### Scenario: 未指定出生位姿
- **WHEN** 以 `hardware:=sim` 啟動車子系統，沒有指定 `x`、`y`、`yaw`
- **THEN** `amr1` 出現在 (0, 0) 且車頭朝 +x 方向
