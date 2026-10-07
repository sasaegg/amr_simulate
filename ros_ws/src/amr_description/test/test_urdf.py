"""amr.urdf.xacro 的結構測試：能展開、是合法 URDF、link／joint 符合設計、四個接觸點貼地。"""

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
