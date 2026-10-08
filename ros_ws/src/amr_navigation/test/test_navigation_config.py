"""導航參數（config/nav2.yaml）與 navigation.launch.xml 的靜態檢查。"""

import xml.etree.ElementTree as ET

import pytest

from vehicle_model import frame_values, PACKAGE_DIR, params, vehicle

LAUNCH_FILE = PACKAGE_DIR / 'launch' / 'navigation.launch.xml'


def launch_nodes():
    """{節點名稱: <node> 元素}；所有節點都在 push-ros-namespace 的 group 內。"""
    root = ET.parse(LAUNCH_FILE).getroot()
    group = root.find('group')
    assert group.find('push-ros-namespace').get('namespace') == '$(var robot_id)'
    return {n.get('name'): n for n in group.iter('node')}


def nav2(robot_id='amr1'):
    """{節點完整名稱: ros__parameters}"""
    return {k: v['ros__parameters'] for k, v in params('nav2.yaml', robot_id).items()}


def node_params(name, robot_id='amr1'):
    return nav2(robot_id)[f'/{robot_id}/{name}']


def test_every_launch_node_has_parameters():
    # 參數檔的鍵是完整名稱 /<namespace>/<name>，名稱打錯參數就不會套用
    for name in launch_nodes():
        assert f'/amr1/{name}' in nav2(), name


def test_every_node_sets_use_sim_time_for_whole_process():
    # 用 ros_args（程序層級）而不是 <param>（只套主節點）：costmap 子節點、bt_navigator 內部節點也要用模擬時間
    for name, node in launch_nodes().items():
        assert node.get('ros_args') == '-p use_sim_time:=$(var use_sim_time)', name
        assert 'use_sim_time' not in [p.get('name') for p in node.iter('param')], name
    for key, values in nav2().items():
        assert 'use_sim_time' not in values, key


def test_every_node_loads_params_with_substitution():
    for name, node in launch_nodes().items():
        files = [p for p in node.iter('param') if p.get('from')]
        assert [f.get('allow_substs') for f in files] == ['true'], name


def test_lifecycle_managers_cover_all_nodes_exactly_once():
    # 每個 Nav2 節點都是 lifecycle node，要由一個 lifecycle_manager 帶起；漏掉的會一直停在 unconfigured
    nodes = launch_nodes()
    managers = [n for n in nodes if n.startswith('lifecycle_manager')]
    managed = [m for name in managers for m in node_params(name)['node_names']]
    assert sorted(managed) == sorted(set(nodes) - set(managers))
    for name in managers:
        assert node_params(name)['autostart'] is True


@pytest.mark.parametrize('robot_id', ['amr1', 'amr2'])
def test_frames_are_map_or_prefixed(robot_id):
    for key, values in nav2(robot_id).items():
        for name, frame in frame_values(values).items():
            assert frame == 'map' or frame.startswith(f'{robot_id}/'), (key, name, frame)


def test_map_file_comes_from_data_directory():
    node = launch_nodes()['map_server']
    value = {p.get('name'): p.get('value') for p in node.iter('param')}['yaml_filename']
    assert value == '/data/maps/$(var map).yaml'


def test_amcl_interface():
    amcl = node_params('amcl')
    assert amcl['scan_topic'] == '/amr1/scan'
    assert amcl['set_initial_pose'] is False          # 初始位姿由使用者在 RViz 給
    assert amcl['tf_broadcast'] is True
    assert amcl['robot_model_type'] == 'nav2_amcl::DifferentialMotionModel'


def test_amcl_laser_range_matches_vehicle_model():
    v = vehicle()
    amcl = node_params('amcl')
    assert amcl['laser_min_range'] == v['lidar_min_range']
    assert amcl['laser_max_range'] == v['lidar_max_range']
