import pytest
import yaml

from amr_worlds.world_config import (
    clock_bridge_config, DEFAULTS, gazebo_command, load_config, merge, world_file)


# ---------- 三層覆寫 ----------

def test_defaults_when_nothing_given():
    assert merge({}, {}) == DEFAULTS


def test_file_overrides_defaults():
    assert merge({'world': 'other'}, {})['world'] == 'other'


def test_command_line_overrides_file():
    assert merge({'world': 'from_file'}, {'world': 'from_cli'})['world'] == 'from_cli'


def test_empty_command_line_value_means_not_given():
    cfg = merge({'world': 'from_file', 'headless': True}, {'world': '', 'headless': ''})
    assert cfg == {'world': 'from_file', 'headless': True}


@pytest.mark.parametrize('value, expected', [
    (True, True), (False, False), ('true', True), ('False', False), ('TRUE', True),
])
def test_headless_accepts_bool_and_strings(value, expected):
    assert merge({}, {'headless': value})['headless'] is expected


@pytest.mark.parametrize('value', ['yes', '1', 1, None])
def test_headless_rejects_other_values(value):
    with pytest.raises(ValueError):
        merge({'headless': value}, {})


@pytest.mark.parametrize('key', ['wrold', 'robot_id'])
def test_unknown_key_is_rejected(key):
    # 打錯字要報錯；robot_id 也不屬於世界（世界不知道有哪些車）
    with pytest.raises(ValueError, match=key):
        merge({key: 'x'}, {})


@pytest.mark.parametrize('value', [123, '', None])
def test_world_must_be_non_empty_string(value):
    with pytest.raises(ValueError):
        merge({'world': value}, {})


# ---------- 設定檔 ----------

def test_load_config_without_path_is_empty():
    assert load_config('') == {}
    assert load_config(None) == {}


def test_load_config_reads_yaml(tmp_path):
    path = tmp_path / 'world.yaml'
    path.write_text(yaml.safe_dump({'world': 'w', 'headless': True}))
    assert load_config(str(path)) == {'world': 'w', 'headless': True}


def test_load_config_empty_file_is_empty(tmp_path):
    path = tmp_path / 'world.yaml'
    path.write_text('# 全部用預設值\n')
    assert load_config(str(path)) == {}


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        load_config(str(tmp_path / 'nope.yaml'))


def test_load_config_rejects_non_mapping(tmp_path):
    path = tmp_path / 'world.yaml'
    path.write_text('- a\n- b\n')
    with pytest.raises(ValueError):
        load_config(str(path))


# ---------- world 檔與 Gazebo 指令 ----------

def test_world_file_found(tmp_path):
    (tmp_path / 'w.sdf').write_text('<sdf/>')
    assert world_file(tmp_path, 'w') == tmp_path / 'w.sdf'


def test_world_file_missing_mentions_build(tmp_path):
    with pytest.raises(FileNotFoundError, match='colcon build'):
        world_file(tmp_path, 'nope')


def test_gazebo_command_with_gui():
    assert gazebo_command('/w.sdf', False) == ['ign', 'gazebo', '-r', '/w.sdf']


def test_gazebo_command_headless():
    assert gazebo_command('/w.sdf', True) == [
        'ign', 'gazebo', '-s', '--headless-rendering', '-r', '/w.sdf']


def test_clock_bridge_is_only_gazebo_to_ros_clock():
    (entry,) = clock_bridge_config()
    assert entry['ros_topic_name'] == entry['gz_topic_name'] == '/clock'
    assert entry['direction'] == 'GZ_TO_ROS'
    assert entry['gz_type_name'] == 'ignition.msgs.Clock'
