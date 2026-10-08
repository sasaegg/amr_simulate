"""建圖參數（config/mapping.yaml）與 mapping.launch.xml 的靜態檢查。"""

import xml.etree.ElementTree as ET

import pytest

from vehicle_model import frame_values, PACKAGE_DIR, params, vehicle

LAUNCH_FILE = PACKAGE_DIR / 'launch' / 'mapping.launch.xml'


def launch_nodes():
    """{節點名稱: <node> 元素}；所有節點都在 push-ros-namespace 的 group 內。"""
    group = ET.parse(LAUNCH_FILE).getroot().find('group')
    assert group.find('push-ros-namespace').get('namespace') == '$(var robot_id)'
    return {n.get('name'): n for n in group.iter('node')}


def mapping(robot_id='amr1'):
    """{節點完整名稱: ros__parameters}"""
    return {k: v['ros__parameters'] for k, v in params('mapping.yaml', robot_id).items()}


def slam(robot_id='amr1'):
    return mapping(robot_id)[f'/{robot_id}/slam_toolbox']


def test_every_launch_node_has_parameters():
    # 參數檔的鍵必須是節點完整名稱 /<namespace>/<name>，否則參數不會套用（筆記 15）
    for name in launch_nodes():
        assert f'/amr1/{name}' in mapping(), name


def test_every_node_sets_use_sim_time_for_whole_process():
    # use_sim_time 只由 launch 以 ros_args 設定（程序層級），參數檔不寫，避免兩處矛盾
    for name, node in launch_nodes().items():
        assert node.get('ros_args') == '-p use_sim_time:=$(var use_sim_time)', name
    for key, values in mapping().items():
        assert 'use_sim_time' not in values, key


def test_every_node_loads_params_with_substitution():
    for name, node in launch_nodes().items():
        files = [p for p in node.iter('param') if p.get('from')]
        assert [f.get('allow_substs') for f in files] == ['true'], name


def test_lifecycle_manager_covers_lifecycle_nodes():
    # slam_toolbox（Humble 2.6）是一般節點；map_saver 是 lifecycle node，要由 lifecycle_manager 帶起
    manager = mapping()['/amr1/lifecycle_manager_mapping']
    assert manager['node_names'] == ['map_saver']
    assert manager['autostart'] is True
    assert {'slam_toolbox', 'map_saver', 'lifecycle_manager_mapping'} == set(launch_nodes())


def test_map_saver_reads_latched_map():
    assert mapping()['/amr1/map_saver']['map_subscribe_transient_local'] is True


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
