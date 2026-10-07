"""ros_gz_bridge 的 topic 對照設定（純邏輯，不依賴 ROS）。

ROS 2 與 Gazebo transport 是兩套獨立的通訊系統，名稱相同也不會互通；
ros_gz_bridge 依這份設定在兩邊之間轉送訊息並轉換型別。
Gazebo 端的 topic 必須和 amr_description 的外掛／感測器設定一致（有測試檢查）。
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


def bridge_config(robot_id, include_clock=True):
    """回傳 parameter_bridge 的 config_file 內容（list of dict）。

    include_clock：多車時只讓其中一座 bridge 轉送 /clock。
    """
    if not isinstance(robot_id, str) or not ROBOT_ID_PATTERN.fullmatch(robot_id):
        raise ValueError(f'robot_id 只能包含英數字與底線，收到 {robot_id!r}')
    ns = f'/{robot_id}'

    config = []
    if include_clock:
        # 模擬時間：所有 use_sim_time 的節點都靠它
        config.append(_entry('/clock', '/clock',
                             'rosgraph_msgs/msg/Clock', 'ignition.msgs.Clock', GZ_TO_ROS))
    config += [
        _entry(f'{ns}/odom', f'{ns}/odom',
               'nav_msgs/msg/Odometry', 'ignition.msgs.Odometry', GZ_TO_ROS),
        _entry(f'{ns}/scan', f'{ns}/scan',
               'sensor_msgs/msg/LaserScan', 'ignition.msgs.LaserScan', GZ_TO_ROS),
        _entry(f'{ns}/imu', f'{ns}/imu',
               'sensor_msgs/msg/Imu', 'ignition.msgs.IMU', GZ_TO_ROS),
        _entry(f'{ns}/joint_states', f'{ns}/joint_states',
               'sensor_msgs/msg/JointState', 'ignition.msgs.Model', GZ_TO_ROS),
        # DiffDrive 的 odom→base_footprint TF：Gazebo 端每台車一個 topic，ROS 端合併到全域 /tf
        _entry('/tf', f'{ns}/tf',
               'tf2_msgs/msg/TFMessage', 'ignition.msgs.Pose_V', GZ_TO_ROS),
        # 唯一由 ROS 送進 Gazebo 的：經過 watchdog 的速度指令
        _entry(f'{ns}/cmd_vel_gz', f'{ns}/cmd_vel_gz',
               'geometry_msgs/msg/Twist', 'ignition.msgs.Twist', ROS_TO_GZ),
    ]
    return config


def write_bridge_config(robot_id, directory, include_clock=True):
    """把設定寫成 YAML 檔（parameter_bridge 只吃檔案路徑），回傳路徑。"""
    path = Path(directory) / f'bridge_{robot_id}.yaml'
    path.write_text(yaml.safe_dump(bridge_config(robot_id, include_clock), sort_keys=False),
                    encoding='utf-8')
    return path
