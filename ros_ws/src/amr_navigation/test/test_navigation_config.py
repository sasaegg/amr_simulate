"""導航參數（config/nav2.yaml）與 navigation.launch.xml 的靜態檢查。"""

import xml.etree.ElementTree as ET

import pytest
import yaml

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


# ---------- costmap 與 DWB（task 4.2）：必須和車輛模型一致 ----------

COSTMAPS = ('local_costmap/local_costmap', 'global_costmap/global_costmap')


def footprint(name):
    return yaml.safe_load(node_params(name)['footprint'])   # 參數是字串 "[[x, y], ...]"


@pytest.mark.parametrize('costmap', COSTMAPS)
def test_footprint_covers_chassis_and_wheels(costmap):
    # 矩形車體：前後到車身邊緣、左右到輪子外緣（輪子突出車身）
    v = vehicle()
    half_length = v['chassis_length'] / 2
    half_width = v['chassis_width'] / 2 + v['wheel_width']      # 輪子中心在車身邊緣外 wheel_width/2
    xs = sorted({x for x, _ in footprint(costmap)})
    ys = sorted({y for _, y in footprint(costmap)})
    assert xs == pytest.approx([-half_length, half_length])
    assert ys == pytest.approx([-half_width, half_width])
    assert 'robot_radius' not in node_params(costmap)


@pytest.mark.parametrize('costmap', COSTMAPS)
def test_obstacle_layer_uses_vehicle_scan(costmap):
    layer = node_params(costmap)['obstacle_layer']
    assert layer['observation_sources'] == 'scan'
    assert layer['scan']['topic'] == '/amr1/scan'
    assert layer['scan']['obstacle_max_range'] <= vehicle()['lidar_max_range']


def test_global_costmap_reads_vehicle_map():
    assert node_params('global_costmap/global_costmap')['static_layer']['map_topic'] == '/amr1/map'


def test_local_costmap_follows_vehicle():
    local = node_params('local_costmap/local_costmap')
    assert local['rolling_window'] is True
    assert local['global_frame'] == 'amr1/odom'


def test_navigation_speed_limits():
    # 導航上限 0.5 m/s、1.0 rad/s（spec）；DWB 與 velocity_smoother 一致，且不超過硬體
    v = vehicle()
    dwb = node_params('controller_server')['FollowPath']
    smoother = node_params('velocity_smoother')
    assert dwb['max_vel_x'] == dwb['max_speed_xy'] == smoother['max_velocity'][0] == 0.5
    assert dwb['max_vel_theta'] == smoother['max_velocity'][2] == 1.0
    assert dwb['max_vel_y'] == 0.0                                 # 差速車不能橫移
    assert 0.5 <= v['max_linear_velocity'] and 1.0 <= v['max_angular_velocity']


def test_acceleration_limits_within_hardware():
    v = vehicle()
    dwb = node_params('controller_server')['FollowPath']
    smoother = node_params('velocity_smoother')
    for value in (dwb['acc_lim_x'], -dwb['decel_lim_x'], smoother['max_accel'][0], -smoother['max_decel'][0]):
        assert value <= v['max_linear_acceleration']
    for value in (dwb['acc_lim_theta'], -dwb['decel_lim_theta'], smoother['max_accel'][2], -smoother['max_decel'][2]):
        assert value <= v['max_angular_acceleration']


def test_goal_tolerance_within_spec():
    # spec：到達時位置誤差 0.3 m 以內
    checker = node_params('controller_server')['general_goal_checker']
    assert checker['xy_goal_tolerance'] < 0.3


def test_planner_does_not_replace_unreachable_goal():
    # tolerance > 0 時，目標在障礙物內會改規劃到附近的替代點，到了替代點就回報成功——
    # spec 要求到不了要回報失敗、到達時誤差 0.3 m 內
    assert node_params('planner_server')['GridBased']['tolerance'] == 0.0
