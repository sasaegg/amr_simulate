"""車子系統的啟動設定（純邏輯，不依賴 ROS）。

設定三層覆寫：套件預設 ← robot.yaml（docker/amr_sim/config/）← launch 命令列參數。
hardware 沒有預設值：真車不能不小心以模擬模式啟動，反之亦然。
"""

from pathlib import Path
import re

import yaml

HARDWARE_MODES = ('sim', 'real')
ROBOT_ID_PATTERN = re.compile(r'[A-Za-z0-9_]+')
TOP_LEVEL_KEYS = ('robot_id', 'hardware', 'sim')
SIM_KEYS = ('spawn',)
DEFAULT_ROBOT_ID = 'amr1'
DEFAULT_SPAWN = (0.0, 0.0, 0.0)


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


def _check_keys(section, allowed, where):
    unknown = set(section) - set(allowed)
    if unknown:
        raise ValueError(f'{where}未知的設定：{", ".join(sorted(unknown))}（可用：{", ".join(allowed)}）')


def _spawn(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)):
        raise ValueError(f'sim.spawn: 必須是 [x, y, yaw] 三個數字，收到 {value!r}')
    return tuple(float(v) for v in value)


def merge(file_config, overrides):
    """回傳 {'robot_id', 'hardware', 'spawn', 'use_sim_time'}；命令列值為空字串視為「沒給」。"""
    _check_keys(file_config, TOP_LEVEL_KEYS, '')
    overrides = {k: v for k, v in overrides.items() if v != ''}
    _check_keys(overrides, ('robot_id', 'hardware'), '命令列')

    sim = file_config.get('sim') or {}
    if not isinstance(sim, dict):
        raise ValueError('sim: 必須是 key: value 結構')
    _check_keys(sim, SIM_KEYS, 'sim.')

    robot_id = overrides.get('robot_id', file_config.get('robot_id', DEFAULT_ROBOT_ID))
    if not isinstance(robot_id, str) or not ROBOT_ID_PATTERN.fullmatch(robot_id):
        raise ValueError(f'robot_id: 只能包含英數字與底線，收到 {robot_id!r}')

    hardware = overrides.get('hardware', file_config.get('hardware'))
    if hardware is None:
        raise ValueError(f'hardware: 必須明確設定，可用值：{", ".join(HARDWARE_MODES)}')
    if hardware not in HARDWARE_MODES:
        raise ValueError(f'hardware: 只能是 {" 或 ".join(HARDWARE_MODES)}，收到 {hardware!r}')

    return {
        'robot_id': robot_id,
        'hardware': hardware,
        'spawn': _spawn(sim['spawn']) if 'spawn' in sim else DEFAULT_SPAWN,
        # 模擬時間由 hardware 決定，不另設參數，避免兩個設定互相矛盾
        'use_sim_time': hardware == 'sim',
    }
