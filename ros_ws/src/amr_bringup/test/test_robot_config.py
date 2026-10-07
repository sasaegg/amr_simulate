import pytest
import yaml

from amr_bringup.robot_config import load_config, merge


def test_minimal_sim_config():
    assert merge({'hardware': 'sim'}, {}) == {
        'robot_id': 'amr1', 'hardware': 'sim', 'spawn': (0.0, 0.0, 0.0), 'use_sim_time': True}


def test_real_mode_uses_system_time():
    assert merge({'hardware': 'real'}, {})['use_sim_time'] is False


# ---------- hardware：必填、只能是 sim／real ----------

def test_hardware_is_required():
    # 沒有預設值：真車不能不小心以模擬模式啟動
    with pytest.raises(ValueError, match='hardware.*sim.*real'):
        merge({}, {})


def test_empty_command_line_hardware_still_required():
    with pytest.raises(ValueError, match='hardware'):
        merge({}, {'hardware': ''})


@pytest.mark.parametrize('value', ['gazebo', 'SIM', True, 1])
def test_hardware_rejects_other_values(value):
    with pytest.raises(ValueError, match='hardware'):
        merge({'hardware': value}, {})


def test_command_line_hardware_overrides_file():
    assert merge({'hardware': 'real'}, {'hardware': 'sim'})['hardware'] == 'sim'


# ---------- robot_id ----------

def test_robot_id_from_file_and_command_line():
    assert merge({'hardware': 'sim', 'robot_id': 'amr2'}, {})['robot_id'] == 'amr2'
    assert merge({'hardware': 'sim', 'robot_id': 'amr2'}, {'robot_id': 'amr3'})['robot_id'] == 'amr3'


@pytest.mark.parametrize('value', ['', 'amr 1', '../amr', '/amr1', 5])
def test_invalid_robot_id(value):
    with pytest.raises(ValueError, match='robot_id'):
        merge({'hardware': 'sim', 'robot_id': value}, {})


# ---------- sim.spawn ----------

def test_spawn_from_file():
    cfg = merge({'hardware': 'sim', 'sim': {'spawn': [1, 2, 0.5]}}, {})
    assert cfg['spawn'] == (1.0, 2.0, 0.5)


@pytest.mark.parametrize('spawn', [[1, 1], 'here', [1, 'a', 0], [True, 1, 0]])
def test_invalid_spawn(spawn):
    with pytest.raises(ValueError, match='sim.spawn'):
        merge({'hardware': 'sim', 'sim': {'spawn': spawn}}, {})


def test_empty_sim_section_uses_origin():
    assert merge({'hardware': 'sim', 'sim': None}, {})['spawn'] == (0.0, 0.0, 0.0)


# ---------- 未知設定 ----------

@pytest.mark.parametrize('config', [
    {'hardware': 'sim', 'hardwear': 'sim'},
    {'hardware': 'sim', 'world': 'warehouse_small'},      # world 不屬於車子系統
    {'hardware': 'sim', 'sim': {'spwan': [1, 1, 0]}},
])
def test_unknown_keys_are_rejected(config):
    with pytest.raises(ValueError, match='未知'):
        merge(config, {})


def test_unknown_command_line_key_is_rejected():
    with pytest.raises(ValueError, match='未知'):
        merge({'hardware': 'sim'}, {'spawn': '1,1,0'})


# ---------- 設定檔 ----------

def test_load_config_without_path_is_empty():
    assert load_config('') == {}


def test_load_config_reads_yaml(tmp_path):
    path = tmp_path / 'robot.yaml'
    path.write_text(yaml.safe_dump({'hardware': 'sim', 'sim': {'spawn': [1, 1, 0]}}))
    assert merge(load_config(str(path)), {})['spawn'] == (1.0, 1.0, 0.0)


def test_load_config_rejects_non_mapping(tmp_path):
    path = tmp_path / 'robot.yaml'
    path.write_text('- sim\n')
    with pytest.raises(ValueError):
        load_config(str(path))
