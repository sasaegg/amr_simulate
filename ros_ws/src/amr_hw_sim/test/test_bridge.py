"""虛擬驅動的 bridge 設定（寫在 sim_hardware.launch.xml 的 parameter_bridge args）。

直接解析 launch XML，不需要 ROS：檢查 topic 對應、方向、namespace，以及與車輛模型的一致性。
"""

from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

LAUNCH_FILE = Path(__file__).resolve().parents[1] / 'launch' / 'sim_hardware.launch.xml'
DIRECTION = {'[': 'GZ_TO_ROS', ']': 'ROS_TO_GZ', '@': 'BIDIRECTIONAL'}
ARG = re.compile(r'(?P<topic>/[\w/]+)@(?P<ros>[\w/]+)(?P<dir>[\[\]@])(?P<gz>[\w.]+)')

# ROS topic: (Gazebo topic, ROS 型別, Gazebo 型別, 方向)
EXPECTED = {
    'base_bridge': {
        '/amr1/cmd_vel_gz': ('/amr1/cmd_vel_gz', 'geometry_msgs/msg/Twist',
                             'ignition.msgs.Twist', 'ROS_TO_GZ'),
        '/amr1/odom': ('/amr1/odom', 'nav_msgs/msg/Odometry', 'ignition.msgs.Odometry',
                       'GZ_TO_ROS'),
        '/tf': ('/amr1/tf', 'tf2_msgs/msg/TFMessage', 'ignition.msgs.Pose_V', 'GZ_TO_ROS'),
        '/amr1/joint_states': ('/amr1/joint_states', 'sensor_msgs/msg/JointState',
                               'ignition.msgs.Model', 'GZ_TO_ROS'),
    },
    'lidar_bridge': {
        '/amr1/scan': ('/amr1/scan', 'sensor_msgs/msg/LaserScan', 'ignition.msgs.LaserScan',
                       'GZ_TO_ROS'),
    },
    'imu_bridge': {
        '/amr1/imu': ('/amr1/imu', 'sensor_msgs/msg/Imu', 'ignition.msgs.IMU', 'GZ_TO_ROS'),
    },
}


def bridges(robot_id='amr1'):
    """{bridge 節點名稱: {ROS topic: (Gazebo topic, ROS 型別, Gazebo 型別, 方向)}}"""
    text = LAUNCH_FILE.read_text(encoding='utf-8').replace('$(var robot_id)', robot_id)
    result = {}
    for node in ET.fromstring(text).iter('node'):
        if node.get('exec') != 'parameter_bridge':
            continue
        remaps = {r.get('from'): r.get('to') for r in node.iter('remap')}
        table = {}
        for arg in node.get('args').split():
            m = ARG.fullmatch(arg)
            assert m, f'無法解析的 bridge 參數：{arg}'
            ros_topic = remaps.get(m['topic'], m['topic'])
            table[ros_topic] = (m['topic'], m['ros'], m['gz'], DIRECTION[m['dir']])
        result[node.get('name')] = table
    return result


def all_entries(robot_id='amr1'):
    return {k: v for table in bridges(robot_id).values() for k, v in table.items()}


def test_one_bridge_per_virtual_component():
    assert set(bridges()) == set(EXPECTED)


@pytest.mark.parametrize('name', EXPECTED)
def test_bridge_matches_design(name):
    assert bridges()[name] == EXPECTED[name]


def test_only_cmd_vel_goes_into_gazebo():
    to_gz = [ros for ros, entry in all_entries().items() if entry[3] != 'GZ_TO_ROS']
    assert to_gz == ['/amr1/cmd_vel_gz']


def test_clock_belongs_to_the_world_not_the_vehicle():
    # 時間屬於世界：不論幾台車都只有一個 /clock 發布者，所以虛擬驅動不轉送它
    assert '/clock' not in all_entries()


def test_robot_id_is_applied_everywhere():
    entries = all_entries('amr2')
    assert 'amr1' not in repr(entries)
    assert entries['/tf'][0] == '/amr2/tf'
    assert {'/amr2/scan', '/amr2/imu', '/amr2/odom'} <= set(entries)


def test_bridges_run_in_vehicle_namespace():
    text = LAUNCH_FILE.read_text(encoding='utf-8')
    for node in ET.fromstring(text).iter('node'):
        if node.get('exec') == 'parameter_bridge':
            assert node.get('namespace') == '$(var robot_id)', node.get('name')


# ---------- 與車輛模型的一致性（需要 xacro，沒有 ROS 環境時略過） ----------

XACRO_FILE = (Path(__file__).resolve().parents[2]
              / 'amr_description' / 'urdf' / 'amr.urdf.xacro')


@pytest.mark.skipif(shutil.which('xacro') is None, reason='需要 ROS 環境的 xacro')
def test_gazebo_topics_match_vehicle_model():
    # bridge 的 Gazebo 端 topic 必須和 xacro 外掛／感測器設定的 topic 一模一樣，否則資料接不起來
    urdf = subprocess.run(['xacro', str(XACRO_FILE), 'robot_id:=amr1'],
                          capture_output=True, text=True, check=True).stdout
    root = ET.fromstring(urdf)
    model_topics = {t.text.strip() for t in root.iter()
                    if t.tag in ('topic', 'odom_topic', 'tf_topic') and t.text}
    bridge_topics = {entry[0] for entry in all_entries().values()}
    assert bridge_topics == model_topics
    assert all(re.fullmatch(r'/amr1/\w+', t) for t in model_topics)
