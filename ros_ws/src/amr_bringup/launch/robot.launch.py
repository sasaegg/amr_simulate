"""車子系統的中控：依 hardware 帶起驅動，加上與硬體無關的共用節點。

用法（robot 容器內）：
    ros2 launch amr_bringup robot.launch.py config:=/config/robot.yaml
    ros2 launch amr_bringup robot.launch.py hardware:=sim robot_id:=amr1

hardware（robot.yaml 必須明確設定）：
    sim   include amr_hw_sim 的 sim_hardware.launch.py（虛擬驅動，資料由 Gazebo 提供），使用模擬時間
    real  真車驅動（尚未提供）
真車上不會安裝 amr_hw_sim：這裡只在 hardware: sim 時以「套件名稱」尋找它，不宣告相依。
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro

from amr_bringup.robot_config import load_config, merge

ARGUMENTS = {
    'config': '設定檔路徑（robot.yaml），空字串 = 不使用',
    'robot_id': '車輛 id，同時是 namespace 與 TF 前綴（預設 amr1）',
    'hardware': 'sim 或 real（必須在 robot.yaml 或這裡明確指定）',
}


def hardware_launch(config):
    if config['hardware'] == 'real':
        raise RuntimeError('hardware: real——尚未提供真車驅動（amr_hw_real），目前只能使用 hardware: sim')
    try:
        share = Path(get_package_share_directory('amr_hw_sim'))
    except PackageNotFoundError:
        raise RuntimeError('hardware: sim 需要 amr_hw_sim 套件，但這個環境沒有安裝') from None
    x, y, yaw = config['spawn']
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(share / 'launch' / 'sim_hardware.launch.py')),
        launch_arguments={'robot_id': config['robot_id'],
                          'x': str(x), 'y': str(y), 'yaw': str(yaw)}.items(),
    )


def launch_setup(context):
    overrides = {key: LaunchConfiguration(key).perform(context) for key in ('robot_id', 'hardware')}
    config = merge(load_config(LaunchConfiguration('config').perform(context)), overrides)
    robot_id = config['robot_id']

    xacro_file = Path(get_package_share_directory('amr_description')) / 'urdf' / 'amr.urdf.xacro'
    robot_description = xacro.process_file(str(xacro_file), mappings={'robot_id': robot_id}).toxml()

    return [
        LogInfo(msg=f'robot_id={robot_id} hardware={config["hardware"]} spawn={config["spawn"]} '
                    f'use_sim_time={config["use_sim_time"]}'),
        # ---- 與硬體無關：依 URDF 與 joint_states 發布車身各零件的 TF ----
        Node(
            package='robot_state_publisher', executable='robot_state_publisher',
            namespace=robot_id,
            parameters=[{
                'robot_description': robot_description,
                'frame_prefix': f'{robot_id}/',
                'use_sim_time': config['use_sim_time'],
            }],
            output='screen',
        ),
        # ---- 驅動：依 hardware 決定 ----
        hardware_launch(config),
    ]


def generate_launch_description():
    return LaunchDescription(
        [DeclareLaunchArgument(name, default_value='', description=text)
         for name, text in ARGUMENTS.items()]
        + [OpaqueFunction(function=launch_setup)]
    )
