"""啟動模擬：Gazebo（倉庫 world）+ 一台 AMR（生成、bridge、robot_state_publisher、watchdog）。

用法（容器內）：
    ros2 launch amr_bringup sim.launch.py config:=/config/sim.yaml
    ros2 launch amr_bringup sim.launch.py world:=warehouse_small_edited headless:=true

設定三層覆寫：套件預設 ← config（sim.yaml）← 命令列參數。
world 與場景 YAML 從 AMR_WORLDS_DIR（原始碼目錄，改 YAML 不用重新 build）讀取，
沒設定時用 amr_worlds 的安裝目錄。
"""

import os
from pathlib import Path
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro

from amr_bringup.bridge import write_bridge_config
from amr_bringup.sim_config import load_config, merge, resolve_spawn, world_file

ARGUMENTS = {
    'config': '設定檔路徑（sim.yaml），空字串 = 不使用',
    'world': 'world 名稱（worlds/<world>.sdf）',
    'robot_id': '車輛 id，同時是 namespace 與 TF 前綴',
    'headless': 'true = 不開 Gazebo GUI（以 EGL 離屏渲染，光達照常運作）',
}


def worlds_dir():
    return Path(os.environ.get('AMR_WORLDS_DIR') or get_package_share_directory('amr_worlds'))


def spawn_robot(robot_id, pose, include_clock=True):
    """生成一台車需要的所有東西；多車時對每個 robot_id 呼叫一次（第二台起 include_clock=False）。"""
    x, y, yaw = pose
    xacro_file = Path(get_package_share_directory('amr_description')) / 'urdf' / 'amr.urdf.xacro'
    robot_description = xacro.process_file(
        str(xacro_file), mappings={'robot_id': robot_id}).toxml()

    bridge_dir = Path(tempfile.gettempdir()) / 'amr_bringup'
    bridge_dir.mkdir(exist_ok=True)
    bridge_file = write_bridge_config(robot_id, bridge_dir, include_clock)

    return [
        # 依 URDF 與 joint_states 發布 TF；frame_prefix 讓 base_link 變成 amr1/base_link
        Node(
            package='robot_state_publisher', executable='robot_state_publisher',
            namespace=robot_id,
            parameters=[{
                'robot_description': robot_description,
                'frame_prefix': f'{robot_id}/',
                'use_sim_time': True,
            }],
            output='screen',
        ),
        # 從 /<id>/robot_description 讀模型，在 Gazebo 中生成
        Node(
            package='ros_gz_sim', executable='create',
            arguments=['-name', robot_id, '-topic', f'/{robot_id}/robot_description',
                       '-x', str(x), '-y', str(y), '-z', '0.0', '-Y', str(yaw)],
            output='screen',
        ),
        Node(
            package='ros_gz_bridge', executable='parameter_bridge',
            parameters=[{'config_file': str(bridge_file), 'use_sim_time': True}],
            output='screen',
        ),
        Node(
            package='amr_bringup', executable='cmd_vel_watchdog',
            namespace=robot_id,
            parameters=[{'use_sim_time': True}],
            output='screen',
        ),
    ]


def launch_setup(context):
    # OpaqueFunction：launch 參數要等到「執行時」才有值，所以在這裡才讀取並合併
    overrides = {key: LaunchConfiguration(key).perform(context)
                 for key in ('world', 'robot_id', 'headless')}
    config = merge(load_config(LaunchConfiguration('config').perform(context)), overrides)

    directory = worlds_dir()
    world = world_file(directory / 'worlds', config['world'])
    pose = resolve_spawn(directory / 'scenes', config['world'], config['robot_id'])

    gazebo = ['ign', 'gazebo', '-r', str(world)]
    if config['headless']:
        gazebo[2:2] = ['-s', '--headless-rendering']

    return [
        LogInfo(msg=f'world={world} robot_id={config["robot_id"]} spawn={pose} '
                    f'headless={config["headless"]}'),
        ExecuteProcess(cmd=gazebo, output='screen'),
        *spawn_robot(config['robot_id'], pose),
    ]


def generate_launch_description():
    return LaunchDescription(
        [DeclareLaunchArgument(name, default_value='', description=text)
         for name, text in ARGUMENTS.items()]
        + [OpaqueFunction(function=launch_setup)]
    )
