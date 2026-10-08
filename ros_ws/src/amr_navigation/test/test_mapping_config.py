"""建圖參數（config/slam_toolbox.yaml）與 launch 的靜態檢查。"""

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from vehicle_model import frame_values, PACKAGE_DIR, params, vehicle

LAUNCH_FILE = PACKAGE_DIR / 'launch' / 'mapping.launch.xml'


def slam(robot_id='amr1'):
    return params('slam_toolbox.yaml', robot_id)[f'/{robot_id}/slam_toolbox']['ros__parameters']


def test_node_key_matches_launch_node():
    # 參數檔的鍵必須是節點完整名稱 /<namespace>/<name>，否則參數不會套用（筆記 15）
    node = ET.parse(LAUNCH_FILE).getroot().find('node')
    assert node.get('namespace') == '$(var robot_id)'
    assert f"/amr1/{node.get('name')}" in params('slam_toolbox.yaml')


def test_frames():
    assert frame_values(slam()) == {
        'map_frame': 'map',                       # 多車共用，不加前綴
        'odom_frame': 'amr1/odom',
        'base_frame': 'amr1/base_footprint',
    }


@pytest.mark.parametrize('robot_id', ['amr1', 'amr2'])
def test_topics_follow_robot_id(robot_id):
    p = slam(robot_id)
    assert p['scan_topic'] == f'/{robot_id}/scan'
    assert p['map_name'] == f'/{robot_id}/map'


def test_laser_range_matches_vehicle_model():
    v = vehicle()
    assert slam()['min_laser_range'] == v['lidar_min_range']
    assert slam()['max_laser_range'] == v['lidar_max_range']


def test_mapping_mode_and_resolution():
    assert slam()['mode'] == 'mapping'
    assert slam()['resolution'] == 0.05


def test_use_sim_time_comes_from_launch():
    # use_sim_time 只由 launch 以 ros_args 設定（程序層級），參數檔不寫，避免兩處矛盾
    assert 'use_sim_time' not in slam()
    node = ET.parse(LAUNCH_FILE).getroot().find('node')
    assert node.get('ros_args') == '-p use_sim_time:=$(var use_sim_time)'


def test_params_loaded_with_substitution():
    node = ET.parse(LAUNCH_FILE).getroot().find('node')
    files = [p for p in node.iter('param') if p.get('from')]
    assert len(files) == 1
    assert files[0].get('allow_substs') == 'true'
    assert Path(files[0].get('from')).name == 'slam_toolbox.yaml'
