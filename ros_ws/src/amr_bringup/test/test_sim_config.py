import pytest
import yaml

from amr_bringup.sim_config import DEFAULTS, load_config, merge, resolve_spawn, world_file


# ---------- 三層覆寫 ----------

def test_defaults_when_nothing_given():
    assert merge({}, {}) == DEFAULTS


def test_file_overrides_defaults():
    assert merge({'world': 'other'}, {})['world'] == 'other'


def test_command_line_overrides_file():
    cfg = merge({'world': 'from_file'}, {'world': 'from_cli'})
    assert cfg['world'] == 'from_cli'


def test_empty_command_line_value_means_not_given():
    # launch 參數沒給時是空字串，不能把設定檔的值蓋成空字串
    cfg = merge({'world': 'from_file'}, {'world': '', 'robot_id': '', 'headless': ''})
    assert cfg['world'] == 'from_file'
    assert cfg['robot_id'] == 'amr1'


@pytest.mark.parametrize('value, expected', [
    (True, True), (False, False), ('true', True), ('False', False), ('TRUE', True),
])
def test_headless_accepts_bool_and_strings(value, expected):
    assert merge({}, {'headless': value})['headless'] is expected


@pytest.mark.parametrize('value', ['yes', '1', 1, None])
def test_headless_rejects_other_values(value):
    with pytest.raises(ValueError):
        merge({'headless': value}, {})


def test_unknown_key_is_rejected():
    # 打錯字（例如 wrold）要報錯，而不是默默忽略
    with pytest.raises(ValueError, match='wrold'):
        merge({'wrold': 'x'}, {})


@pytest.mark.parametrize('key', ['world', 'robot_id'])
def test_names_must_be_non_empty_strings(key):
    with pytest.raises(ValueError):
        merge({key: 123}, {})


# ---------- 設定檔 ----------

def test_load_config_without_path_is_empty():
    assert load_config('') == {}
    assert load_config(None) == {}


def test_load_config_reads_yaml(tmp_path):
    path = tmp_path / 'sim.yaml'
    path.write_text(yaml.safe_dump({'world': 'w', 'headless': True}))
    assert load_config(str(path)) == {'world': 'w', 'headless': True}


def test_load_config_empty_file_is_empty(tmp_path):
    path = tmp_path / 'sim.yaml'
    path.write_text('# 全部用預設值\n')
    assert load_config(str(path)) == {}


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        load_config(str(tmp_path / 'nope.yaml'))


def test_load_config_rejects_non_mapping(tmp_path):
    path = tmp_path / 'sim.yaml'
    path.write_text('- a\n- b\n')
    with pytest.raises(ValueError):
        load_config(str(path))


# ---------- world 檔 ----------

def test_world_file_found(tmp_path):
    (tmp_path / 'w.sdf').write_text('<sdf/>')
    assert world_file(tmp_path, 'w') == tmp_path / 'w.sdf'


def test_world_file_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match='nope.sdf'):
        world_file(tmp_path, 'nope')


# ---------- 出生點 ----------

def write_scene(directory, name, spawn):
    (directory / f'{name}.yaml').write_text(yaml.safe_dump({'name': name, 'spawn': spawn}))


def test_spawn_from_matching_scene(tmp_path):
    write_scene(tmp_path, 'w', {'amr1': [1, 2, 0.5]})
    assert resolve_spawn(tmp_path, 'w', 'amr1') == (1.0, 2.0, 0.5)


def test_edited_world_falls_back_to_original_scene(tmp_path):
    # GUI 另存的 w_edited.sdf 沒有自己的 YAML，沿用 w.yaml 的出生點
    write_scene(tmp_path, 'w', {'amr1': [3, 4, 0]})
    assert resolve_spawn(tmp_path, 'w_edited', 'amr1') == (3.0, 4.0, 0.0)


def test_edited_world_prefers_its_own_scene(tmp_path):
    write_scene(tmp_path, 'w', {'amr1': [3, 4, 0]})
    write_scene(tmp_path, 'w_edited', {'amr1': [5, 6, 0]})
    assert resolve_spawn(tmp_path, 'w_edited', 'amr1') == (5.0, 6.0, 0.0)


def test_no_scene_means_origin(tmp_path):
    assert resolve_spawn(tmp_path, 'unknown', 'amr1') == (0.0, 0.0, 0.0)


def test_robot_not_in_spawn_means_origin(tmp_path):
    write_scene(tmp_path, 'w', {'amr1': [1, 1, 0]})
    assert resolve_spawn(tmp_path, 'w', 'amr2') == (0.0, 0.0, 0.0)
