"""世界啟動設定（純邏輯，不依賴 ROS）。

設定三層覆寫：套件預設 ← world.yaml（docker/amr_sim/config/）← launch 命令列參數。
世界只管場景與 Gazebo 本身，不知道有哪些車輛。
"""

from pathlib import Path

import yaml

DEFAULTS = {
    'world': 'warehouse_small',
    'headless': False,
}


def to_bool(value, key):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    raise ValueError(f'{key}: 必須是 true 或 false，收到 {value!r}')


def load_config(path):
    """讀設定檔；path 為空代表不使用設定檔，回傳 {}。"""
    if not path:
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f'{path}: 必須是 key: value 結構')
    return data


def merge(file_config, overrides):
    """套件預設 ← 設定檔 ← 命令列；命令列值為空字串視為「沒給」。"""
    merged = dict(DEFAULTS)
    for source in (file_config, {k: v for k, v in overrides.items() if v != ''}):
        unknown = set(source) - set(DEFAULTS)
        if unknown:
            raise ValueError(f'未知的設定：{", ".join(sorted(unknown))}（可用：{", ".join(DEFAULTS)}）')
        merged.update(source)
    merged['headless'] = to_bool(merged['headless'], 'headless')
    if not isinstance(merged['world'], str) or not merged['world']:
        raise ValueError(f'world: 必須是非空字串，收到 {merged["world"]!r}')
    return merged


def world_file(worlds_dir, world):
    path = Path(worlds_dir) / f'{world}.sdf'
    if not path.is_file():
        raise FileNotFoundError(f'找不到 world：{path}（新增的 world 需要先 colcon build 才會安裝）')
    return path


def gazebo_command(world_path, headless):
    """headless：只跑 server（-s），用 EGL 離屏渲染（--headless-rendering），光達照常運作。"""
    command = ['ign', 'gazebo', '-r', str(world_path)]
    if headless:
        command[2:2] = ['-s', '--headless-rendering']
    return command


def clock_bridge_config():
    """模擬時間屬於世界：不論幾台車，/clock 都只由世界轉送一次。"""
    return [{
        'ros_topic_name': '/clock',
        'gz_topic_name': '/clock',
        'ros_type_name': 'rosgraph_msgs/msg/Clock',
        'gz_type_name': 'ignition.msgs.Clock',
        'direction': 'GZ_TO_ROS',
    }]
