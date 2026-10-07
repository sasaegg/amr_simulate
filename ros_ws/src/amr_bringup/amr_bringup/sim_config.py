"""模擬啟動設定與出生點解析（純邏輯，不依賴 ROS）。

設定三層覆寫：套件預設 ← sim.yaml（docker/amr_sim/config/）← launch 命令列參數。
"""

from pathlib import Path

import yaml

DEFAULTS = {
    'world': 'warehouse_small',
    'robot_id': 'amr1',
    'headless': False,
}

EDITED_SUFFIX = '_edited'


def _to_bool(value, key):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    raise ValueError(f'{key}: 必須是 true 或 false，收到 {value!r}')


def load_config(path):
    """讀 sim.yaml；path 為空代表不使用設定檔，回傳 {}。"""
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
    merged['headless'] = _to_bool(merged['headless'], 'headless')
    for key in ('world', 'robot_id'):
        if not isinstance(merged[key], str) or not merged[key]:
            raise ValueError(f'{key}: 必須是非空字串，收到 {merged[key]!r}')
    return merged


def world_file(worlds_dir, world):
    path = Path(worlds_dir) / f'{world}.sdf'
    if not path.is_file():
        raise FileNotFoundError(f'找不到 world：{path}')
    return path


def resolve_spawn(scenes_dir, world, robot_id):
    """出生位姿 (x, y, yaw)：<world>.yaml → 去掉 _edited 的同名 YAML → 原點。"""
    candidates = [world]
    if world.endswith(EDITED_SUFFIX):
        candidates.append(world[:-len(EDITED_SUFFIX)])
    for name in candidates:
        path = Path(scenes_dir) / f'{name}.yaml'
        if path.is_file():
            scene = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            pose = (scene.get('spawn') or {}).get(robot_id)
            if pose is None:
                return (0.0, 0.0, 0.0)
            x, y, yaw = pose
            return (float(x), float(y), float(yaw))
    return (0.0, 0.0, 0.0)
