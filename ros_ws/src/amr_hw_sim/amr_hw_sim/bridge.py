"""虛擬驅動的 ros_gz_bridge 設定（純邏輯，不依賴 ROS）。

ROS 2 與 Gazebo transport 是兩套獨立的通訊系統，名稱相同也不會互通；
ros_gz_bridge 依這份設定在兩邊之間轉送訊息並轉換型別。

每個虛擬元件一份設定、一個 bridge 節點，對應真車上的各個驅動：
    base_config   虛擬底盤（馬達驅動板）：cmd_vel 進、odom／TF／joint_states 出
    lidar_config  虛擬光達：scan
    imu_config    虛擬 IMU：imu
Gazebo 端的 topic 必須和 amr_description 的外掛／感測器設定一致（有測試檢查）。
模擬時間 /clock 屬於世界，由 amr_worlds 的 world.launch.py 轉送。
"""

from pathlib import Path
import re

import yaml

GZ_TO_ROS = 'GZ_TO_ROS'
ROS_TO_GZ = 'ROS_TO_GZ'
ROBOT_ID_PATTERN = re.compile(r'[A-Za-z0-9_]+')


def _entry(ros_topic, gz_topic, ros_type, gz_type, direction):
    return {
        'ros_topic_name': ros_topic,
        'gz_topic_name': gz_topic,
        'ros_type_name': ros_type,
        'gz_type_name': gz_type,
        'direction': direction,
    }


def _namespace(robot_id):
    if not isinstance(robot_id, str) or not ROBOT_ID_PATTERN.fullmatch(robot_id):
        raise ValueError(f'robot_id 只能包含英數字與底線，收到 {robot_id!r}')
    return f'/{robot_id}'


def base_config(robot_id):
    """虛擬底盤：唯一由 ROS 送進 Gazebo 的是經過 watchdog 的速度指令。"""
    ns = _namespace(robot_id)
    return [
        _entry(f'{ns}/cmd_vel_gz', f'{ns}/cmd_vel_gz',
               'geometry_msgs/msg/Twist', 'ignition.msgs.Twist', ROS_TO_GZ),
        _entry(f'{ns}/odom', f'{ns}/odom',
               'nav_msgs/msg/Odometry', 'ignition.msgs.Odometry', GZ_TO_ROS),
        # DiffDrive 的 odom→base_footprint TF：Gazebo 端每台車一個 topic，ROS 端合併到全域 /tf
        _entry('/tf', f'{ns}/tf',
               'tf2_msgs/msg/TFMessage', 'ignition.msgs.Pose_V', GZ_TO_ROS),
        _entry(f'{ns}/joint_states', f'{ns}/joint_states',
               'sensor_msgs/msg/JointState', 'ignition.msgs.Model', GZ_TO_ROS),
    ]


def lidar_config(robot_id):
    ns = _namespace(robot_id)
    return [_entry(f'{ns}/scan', f'{ns}/scan',
                   'sensor_msgs/msg/LaserScan', 'ignition.msgs.LaserScan', GZ_TO_ROS)]


def imu_config(robot_id):
    ns = _namespace(robot_id)
    return [_entry(f'{ns}/imu', f'{ns}/imu',
                   'sensor_msgs/msg/Imu', 'ignition.msgs.IMU', GZ_TO_ROS)]


COMPONENTS = {'base': base_config, 'lidar': lidar_config, 'imu': imu_config}


def write_bridge_config(robot_id, component, directory):
    """把某個元件的設定寫成 YAML 檔（parameter_bridge 只吃檔案路徑），回傳路徑。"""
    if component not in COMPONENTS:
        raise ValueError(f'未知的元件 {component!r}，可用：{", ".join(COMPONENTS)}')
    config = COMPONENTS[component](robot_id)
    path = Path(directory) / f'bridge_{robot_id}_{component}.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path
