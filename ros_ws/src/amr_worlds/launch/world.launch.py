"""啟動世界：Gazebo（倉庫 world）與模擬時間 /clock。世界中沒有車輛——車輛由車子系統帶進來。

用法（sim 容器內）：
    ros2 launch amr_worlds world.launch.py config:=/config/world.yaml
    ros2 launch amr_worlds world.launch.py world:=warehouse_small_edited headless:=true

設定三層覆寫：套件預設 ← config（world.yaml）← 命令列參數。
world 檔從套件 share 目錄讀取：--symlink-install 下修改既有檔案即時生效，新增檔案需 colcon build。
"""

from pathlib import Path
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml

from amr_worlds.world_config import (
    clock_bridge_config, gazebo_command, load_config, merge, world_file)

ARGUMENTS = {
    'config': '設定檔路徑（world.yaml），空字串 = 不使用',
    'world': 'world 名稱（worlds/<world>.sdf）',
    'headless': 'true = 不開 Gazebo GUI（以 EGL 離屏渲染，光達照常運作）',
}


def launch_setup(context):
    # launch 參數要等到「執行時」才有值，所以在 OpaqueFunction 裡才讀取並合併
    overrides = {key: LaunchConfiguration(key).perform(context) for key in ('world', 'headless')}
    config = merge(load_config(LaunchConfiguration('config').perform(context)), overrides)

    worlds_dir = Path(get_package_share_directory('amr_worlds')) / 'worlds'
    world = world_file(worlds_dir, config['world'])

    bridge_dir = Path(tempfile.gettempdir()) / 'amr_worlds'
    bridge_dir.mkdir(exist_ok=True)
    clock_file = bridge_dir / 'bridge_clock.yaml'
    clock_file.write_text(yaml.safe_dump(clock_bridge_config(), sort_keys=False))

    return [
        LogInfo(msg=f'world={world} headless={config["headless"]}'),
        ExecuteProcess(cmd=gazebo_command(world, config['headless']), output='screen'),
        Node(
            package='ros_gz_bridge', executable='parameter_bridge', name='clock_bridge',
            parameters=[{'config_file': str(clock_file)}],
            output='screen',
        ),
    ]


def generate_launch_description():
    return LaunchDescription(
        [DeclareLaunchArgument(name, default_value='', description=text)
         for name, text in ARGUMENTS.items()]
        + [OpaqueFunction(function=launch_setup)]
    )
