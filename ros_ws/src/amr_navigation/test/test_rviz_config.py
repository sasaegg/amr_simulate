"""RViz 設定檔（config/navigate.rviz）：topic 都要帶 namespace，否則 namespace 下的節點收不到（design D7）。"""

import pytest
import yaml

from vehicle_model import PACKAGE_DIR

RVIZ_FILE = PACKAGE_DIR / 'config' / 'navigate.rviz'


@pytest.fixture(scope='module')
def config():
    return yaml.safe_load(RVIZ_FILE.read_text(encoding='utf-8'))['Visualization Manager']


def by_class(items, cls):
    found = [i for i in items if i['Class'] == cls]
    assert found, f'找不到 {cls}'
    return found


def topic(item):
    return item['Topic']['Value']


def test_fixed_frame_is_map(config):
    assert config['Global Options']['Fixed Frame'] == 'map'


def test_every_topic_is_namespaced(config):
    topics = [topic(i) for i in config['Displays'] + config['Tools'] if 'Topic' in i]
    assert topics
    assert all(t.startswith('/amr1/') for t in topics), topics


def test_tools_publish_to_namespaced_topics(config):
    # 2D Pose Estimate → amcl、2D Goal Pose → bt_navigator，兩者都在 namespace amr1 下
    assert topic(by_class(config['Tools'], 'rviz_default_plugins/SetInitialPose')[0]) == '/amr1/initialpose'
    assert topic(by_class(config['Tools'], 'rviz_default_plugins/SetGoal')[0]) == '/amr1/goal_pose'


def test_map_is_transient_local(config):
    # 地圖只在產生或載入時發布一次；Transient Local 才收得到 RViz 開啟之前就發過的那一筆
    for display in by_class(config['Displays'], 'rviz_default_plugins/Map'):
        assert display['Topic']['Durability Policy'] == 'Transient Local', display['Name']


def test_robot_model_uses_tf_prefix(config):
    # URDF 的 link 沒有前綴、TF 裡有（robot_state_publisher frame_prefix），要靠 TF Prefix 對上
    model = by_class(config['Displays'], 'rviz_default_plugins/RobotModel')[0]
    assert model['TF Prefix'] == 'amr1'
    assert model['Description Topic']['Value'] == '/amr1/robot_description'
    assert model['Description Topic']['Durability Policy'] == 'Transient Local'
