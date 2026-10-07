from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest
import yaml

from amr_bringup.bridge import bridge_config, write_bridge_config

# ROS topic: (Gazebo topic, ROS 型別, Gazebo 型別, 方向)
EXPECTED_AMR1 = {
    '/clock': ('/clock', 'rosgraph_msgs/msg/Clock', 'ignition.msgs.Clock', 'GZ_TO_ROS'),
    '/amr1/odom': ('/amr1/odom', 'nav_msgs/msg/Odometry', 'ignition.msgs.Odometry', 'GZ_TO_ROS'),
    '/amr1/scan': ('/amr1/scan', 'sensor_msgs/msg/LaserScan', 'ignition.msgs.LaserScan',
                   'GZ_TO_ROS'),
    '/amr1/imu': ('/amr1/imu', 'sensor_msgs/msg/Imu', 'ignition.msgs.IMU', 'GZ_TO_ROS'),
    '/amr1/joint_states': ('/amr1/joint_states', 'sensor_msgs/msg/JointState',
                           'ignition.msgs.Model', 'GZ_TO_ROS'),
    '/tf': ('/amr1/tf', 'tf2_msgs/msg/TFMessage', 'ignition.msgs.Pose_V', 'GZ_TO_ROS'),
    '/amr1/cmd_vel_gz': ('/amr1/cmd_vel_gz', 'geometry_msgs/msg/Twist', 'ignition.msgs.Twist',
                         'ROS_TO_GZ'),
}


def as_table(config):
    return {e['ros_topic_name']: (e['gz_topic_name'], e['ros_type_name'], e['gz_type_name'],
                                  e['direction']) for e in config}


def test_amr1_config_matches_design():
    assert as_table(bridge_config('amr1')) == EXPECTED_AMR1


def test_every_entry_has_exactly_the_bridge_keys():
    keys = {'ros_topic_name', 'gz_topic_name', 'ros_type_name', 'gz_type_name', 'direction'}
    for entry in bridge_config('amr1'):
        assert set(entry) == keys


def test_only_cmd_vel_goes_into_gazebo():
    to_gz = [e['ros_topic_name'] for e in bridge_config('amr1') if e['direction'] == 'ROS_TO_GZ']
    assert to_gz == ['/amr1/cmd_vel_gz']


def test_robot_id_is_applied_everywhere():
    text = yaml.safe_dump(bridge_config('amr2'))
    assert 'amr1' not in text
    table = as_table(bridge_config('amr2'))
    assert table['/tf'][0] == '/amr2/tf'          # 每台車各自的 gz tf，在 ROS 合併到全域 /tf
    assert '/amr2/scan' in table


def test_clock_can_be_left_out_for_additional_robots():
    # 多車時 /clock 只需要一座 bridge 轉送，重複轉送會讓 ROS 收到兩份時間
    topics = {e['ros_topic_name'] for e in bridge_config('amr2', include_clock=False)}
    assert '/clock' not in topics
    assert '/amr2/odom' in topics


@pytest.mark.parametrize('robot_id', ['', 'amr 1', '../amr', '/amr1', None])
def test_rejects_invalid_robot_id(robot_id):
    with pytest.raises(ValueError):
        bridge_config(robot_id)


def test_write_bridge_config_round_trips(tmp_path):
    path = write_bridge_config('amr1', tmp_path)
    assert path == tmp_path / 'bridge_amr1.yaml'
    assert yaml.safe_load(path.read_text()) == bridge_config('amr1')


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
    bridge_topics = {e['gz_topic_name'] for e in bridge_config('amr1')} - {'/clock'}
    assert bridge_topics == model_topics
    assert all(re.fullmatch(r'/amr1/\w+', t) for t in model_topics)
