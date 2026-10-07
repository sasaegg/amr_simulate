"""amr.urdf.xacro 的結構測試：能展開、是合法 URDF、link／joint 符合設計、四個接觸點貼地。"""

import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest

XACRO_FILE = Path(__file__).resolve().parent.parent / 'urdf' / 'amr.urdf.xacro'

EXPECTED_LINKS = {
    'base_footprint', 'base_link',
    'left_wheel_link', 'right_wheel_link',
    'front_caster_link', 'rear_caster_link',
    'laser_link', 'imu_link',
}

# joint 名稱: (類型, parent, child)
EXPECTED_JOINTS = {
    'base_joint': ('fixed', 'base_footprint', 'base_link'),
    'left_wheel_joint': ('continuous', 'base_link', 'left_wheel_link'),
    'right_wheel_joint': ('continuous', 'base_link', 'right_wheel_link'),
    'front_caster_joint': ('fixed', 'base_link', 'front_caster_link'),
    'rear_caster_joint': ('fixed', 'base_link', 'rear_caster_link'),
    'laser_joint': ('fixed', 'base_link', 'laser_link'),
    'imu_joint': ('fixed', 'base_link', 'imu_link'),
}


def expand(*args):
    result = subprocess.run(['xacro', str(XACRO_FILE), *args],
                            capture_output=True, text=True, check=True)
    return result.stdout


@pytest.fixture(scope='module')
def urdf_text():
    return expand()


@pytest.fixture(scope='module')
def robot(urdf_text):
    return ET.fromstring(urdf_text)


def floats(text):
    return [float(v) for v in text.split()]


def joint_xyz(robot, name):
    return floats(robot.find(f"joint[@name='{name}']/origin").get('xyz'))


def test_check_urdf_passes(urdf_text, tmp_path):
    path = tmp_path / 'amr.urdf'
    path.write_text(urdf_text)
    result = subprocess.run(['check_urdf', str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_links_match_design(robot):
    assert {link.get('name') for link in robot.iter('link')} == EXPECTED_LINKS


def test_joints_match_design(robot):
    joints = {
        j.get('name'): (j.get('type'), j.find('parent').get('link'), j.find('child').get('link'))
        for j in robot.iter('joint')
    }
    assert joints == EXPECTED_JOINTS


def test_names_have_no_prefix(robot):
    # TF 前綴由 robot_state_publisher 的 frame_prefix 加上，URDF 裡不能再加（否則變成 amr1/amr1/...）
    for element in list(robot.iter('link')) + list(robot.iter('joint')):
        assert '/' not in element.get('name'), element.get('name')


def test_wheels_rotate_about_y(robot):
    for side in ('left', 'right'):
        axis = robot.find(f"joint[@name='{side}_wheel_joint']/axis").get('xyz')
        assert floats(axis) == pytest.approx([0, 1, 0])


def test_wheels_are_symmetric(robot):
    left = joint_xyz(robot, 'left_wheel_joint')
    right = joint_xyz(robot, 'right_wheel_joint')
    assert left[1] == pytest.approx(-right[1])
    assert left[1] > 0


def test_physical_links_have_positive_inertia(robot):
    # base_footprint（KDL 不接受有慣量的根 link）與 imu_link（純座標系）除外
    for link in robot.iter('link'):
        name = link.get('name')
        if name in ('base_footprint', 'imu_link'):
            assert link.find('inertial') is None, name
            continue
        inertial = link.find('inertial')
        assert inertial is not None, name
        assert float(inertial.find('mass').get('value')) > 0, name
        inertia = inertial.find('inertia')
        for axis in ('ixx', 'iyy', 'izz'):
            assert float(inertia.get(axis)) > 0, f'{name}.{axis}'


def test_four_contact_points_touch_ground(robot):
    # 地面 = base_footprint 的 z = 0；輪子底部與支撐球底部都要剛好在地面上（車身才不會傾斜）
    base_z = joint_xyz(robot, 'base_joint')[2]
    wheel_r = float(robot.find("link[@name='left_wheel_link']//cylinder").get('radius'))
    caster_r = float(robot.find("link[@name='front_caster_link']//sphere").get('radius'))
    for side in ('left', 'right'):
        z = base_z + joint_xyz(robot, f'{side}_wheel_joint')[2] - wheel_r
        assert z == pytest.approx(0, abs=1e-9), side
    for side in ('front', 'rear'):
        z = base_z + joint_xyz(robot, f'{side}_caster_joint')[2] - caster_r
        assert z == pytest.approx(0, abs=1e-9), side


def test_accepts_robot_id_argument():
    # robot_id 給 Gazebo 外掛用（task 4.2）；不同 id 都要能展開
    assert '<robot name="amr"' in expand('robot_id:=amr2')


# ---------- Gazebo 外掛與感測器（task 4.2） ----------

DIFF_DRIVE = "gazebo/plugin[@name='ignition::gazebo::systems::DiffDrive']"
JOINT_STATE = "gazebo/plugin[@name='ignition::gazebo::systems::JointStatePublisher']"


def text_of(element, path):
    found = element.find(path)
    assert found is not None, path
    return found.text.strip()


def sensor(robot, link, name):
    found = robot.find(f"gazebo[@reference='{link}']/sensor[@name='{name}']")
    assert found is not None, f'{link}/{name}'
    return found


def test_diff_drive_geometry_matches_model(robot):
    plugin = robot.find(DIFF_DRIVE)
    assert text_of(plugin, 'left_joint') == 'left_wheel_joint'
    assert text_of(plugin, 'right_joint') == 'right_wheel_joint'
    wheel_y = joint_xyz(robot, 'left_wheel_joint')[1]
    wheel_r = float(robot.find("link[@name='left_wheel_link']//cylinder").get('radius'))
    assert float(text_of(plugin, 'wheel_separation')) == pytest.approx(2 * wheel_y)
    assert float(text_of(plugin, 'wheel_radius')) == pytest.approx(wheel_r)


def test_diff_drive_topics_and_frames(robot):
    plugin = robot.find(DIFF_DRIVE)
    assert text_of(plugin, 'topic') == '/amr1/cmd_vel_gz'
    assert text_of(plugin, 'odom_topic') == '/amr1/odom'
    assert text_of(plugin, 'tf_topic') == '/amr1/tf'
    assert text_of(plugin, 'frame_id') == 'amr1/odom'
    assert text_of(plugin, 'child_frame_id') == 'amr1/base_footprint'
    assert float(text_of(plugin, 'odom_publish_frequency')) >= 20


@pytest.mark.parametrize('name, value', [
    ('max_linear_velocity', 1.0), ('min_linear_velocity', -1.0),
    ('max_angular_velocity', 1.5), ('min_angular_velocity', -1.5),
    ('max_linear_acceleration', 2.5), ('min_linear_acceleration', -2.5),
    ('max_angular_acceleration', 5.0), ('min_angular_acceleration', -5.0),
])
def test_diff_drive_limits(robot, name, value):
    assert float(text_of(robot.find(DIFF_DRIVE), name)) == pytest.approx(value)


def test_stop_time_fits_spec(robot):
    # spec：停送指令後 1 s 內停車 = watchdog 逾時 0.5 s + 從最高速減速到 0 的時間
    plugin = robot.find(DIFF_DRIVE)
    decel_time = (float(text_of(plugin, 'max_linear_velocity'))
                  / float(text_of(plugin, 'max_linear_acceleration')))
    assert 0.5 + decel_time < 1.0


def test_joint_state_topic(robot):
    assert text_of(robot.find(JOINT_STATE), 'topic') == '/amr1/joint_states'


def test_lidar_parameters(robot):
    lidar = sensor(robot, 'laser_link', 'lidar')
    assert lidar.get('type') == 'gpu_lidar'
    assert text_of(lidar, 'topic') == '/amr1/scan'
    assert text_of(lidar, 'ignition_frame_id') == 'amr1/laser_link'
    assert float(text_of(lidar, 'update_rate')) == pytest.approx(10)
    horizontal = lidar.find('lidar/scan/horizontal')
    samples = int(text_of(horizontal, 'samples'))
    span = float(text_of(horizontal, 'max_angle')) - float(text_of(horizontal, 'min_angle'))
    assert samples == 360
    assert span / (samples - 1) == pytest.approx(math.radians(1))   # 間隔剛好 1°，不重複 ±π
    assert float(text_of(lidar, 'lidar/range/min')) == pytest.approx(0.12)
    assert float(text_of(lidar, 'lidar/range/max')) == pytest.approx(12.0)


def test_imu_parameters(robot):
    imu = sensor(robot, 'imu_link', 'imu')
    assert text_of(imu, 'topic') == '/amr1/imu'
    assert text_of(imu, 'ignition_frame_id') == 'amr1/imu_link'
    assert float(text_of(imu, 'update_rate')) == pytest.approx(100)


def test_robot_id_changes_all_gazebo_names():
    # 先解析再轉回文字：ElementTree 解析時會丟掉 XML 註解，只檢查真正的內容
    text = ET.tostring(ET.fromstring(expand('robot_id:=amr2')), encoding='unicode')
    assert 'amr1' not in text
    for name in ('/amr2/cmd_vel_gz', '/amr2/odom', '/amr2/scan', '/amr2/imu',
                 '/amr2/joint_states', 'amr2/base_footprint', 'amr2/laser_link'):
        assert name in text, name


def test_converts_to_sdf_with_sensors(urdf_text, tmp_path):
    # Gazebo 實際讀的是 SDF：fixed joint 會被併入根 link，感測器與零摩擦設定要跟著保留
    path = tmp_path / 'amr.urdf'
    path.write_text(urdf_text)
    result = subprocess.run(['ign', 'sdf', '-p', str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    sdf = ET.fromstring(result.stdout)
    links = {link.get('name') for link in sdf.iter('link')}
    assert links == {'base_footprint', 'left_wheel_link', 'right_wheel_link'}
    frames = {s.get('name'): s.find('ignition_frame_id').text for s in sdf.iter('sensor')}
    assert frames == {'lidar': 'amr1/laser_link', 'imu': 'amr1/imu_link'}
    caster_mu = [float(c.find('.//mu').text) for c in sdf.iter('collision')
                 if 'caster' in c.get('name')]
    assert caster_mu and all(mu == 0 for mu in caster_mu)
