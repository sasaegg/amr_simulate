"""模擬模式的虛擬驅動：由車子系統的中控（amr_bringup/robot.launch.py）在 hardware: sim 時 include。

每個虛擬元件是獨立節點，對應真車上的各個驅動；資料由 Gazebo 依車輛在世界中的實際位置計算：
    虛擬底盤   spawn（把車體放進世界）+ cmd_vel_watchdog（假驅動板的指令逾時）+ 底盤 bridge
    虛擬光達   scan bridge
    虛擬 IMU   imu bridge
對車子系統而言，這些節點提供的 topic 與真車驅動相同（/<id>/cmd_vel、scan、odom、imu、joint_states、/tf）。
"""

from pathlib import Path
import tempfile

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from amr_hw_sim.bridge import write_bridge_config

ARGUMENTS = {
    'robot_id': ('amr1', '車輛 id（namespace、TF 前綴、Gazebo 實體名稱）'),
    'x': ('0.0', '出生位置 x（公尺）'),
    'y': ('0.0', '出生位置 y（公尺）'),
    'yaw': ('0.0', '出生朝向（弧度）'),
}


def bridge_node(robot_id, component, directory):
    return Node(
        package='ros_gz_bridge', executable='parameter_bridge',
        name=f'{component}_bridge', namespace=robot_id,
        parameters=[{'config_file': str(write_bridge_config(robot_id, component, directory))}],
        output='screen',
    )


def launch_setup(context):
    robot_id = LaunchConfiguration('robot_id').perform(context)
    x, y, yaw = (LaunchConfiguration(k).perform(context) for k in ('x', 'y', 'yaw'))

    directory = Path(tempfile.gettempdir()) / 'amr_hw_sim'
    directory.mkdir(exist_ok=True)

    return [
        # ---- 虛擬底盤 ----
        Node(
            package='amr_hw_sim', executable='spawn_robot', name=f'spawn_{robot_id}',
            arguments=['--robot-id', robot_id, '--x', x, '--y', y, '--yaw', yaw],
            output='screen',
        ),
        Node(
            package='amr_hw_sim', executable='cmd_vel_watchdog', namespace=robot_id,
            parameters=[{'use_sim_time': True}],
            output='screen',
        ),
        bridge_node(robot_id, 'base', directory),
        # ---- 虛擬光達 ----
        bridge_node(robot_id, 'lidar', directory),
        # ---- 虛擬 IMU ----
        bridge_node(robot_id, 'imu', directory),
    ]


def generate_launch_description():
    return LaunchDescription(
        [DeclareLaunchArgument(name, default_value=default, description=text)
         for name, (default, text) in ARGUMENTS.items()]
        + [OpaqueFunction(function=launch_setup)]
    )
