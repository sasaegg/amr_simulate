"""測試共用：從 amr_description 的 xacro 讀車輛規格、讀本套件的參數檔（純 Python，不需要 ROS）。

建圖／導航的參數（光達距離、車體外形、速度上限）必須和車輛模型一致，測試用這裡的函式比對。
"""

from pathlib import Path
import xml.etree.ElementTree as ET

import yaml

PACKAGE_DIR = Path(__file__).resolve().parents[1]
XACRO_FILE = PACKAGE_DIR.parent / 'amr_description' / 'urdf' / 'amr.urdf.xacro'
XACRO_NS = '{http://www.ros.org/wiki/xacro}'


def vehicle():
    """xacro 中直接寫數字的 property，例如 {'lidar_max_range': 12.0, ...}。"""
    root = ET.parse(XACRO_FILE).getroot()
    result = {}
    for prop in root.iter(f'{XACRO_NS}property'):
        try:
            result[prop.get('name')] = float(prop.get('value'))
        except (TypeError, ValueError):
            pass      # 運算式（${...}）或非數字的 property 不收
    return result


def params(name, robot_id='amr1'):
    """讀 config/<name>，把 launch 會代換的 $(var robot_id) 換成 robot_id 後解析。"""
    text = (PACKAGE_DIR / 'config' / name).read_text(encoding='utf-8')
    return yaml.safe_load(text.replace('$(var robot_id)', robot_id))


def frame_values(node_params):
    """參數中名稱以 _frame 或 _frame_id 結尾的值。"""
    return {k: v for k, v in node_params.items()
            if isinstance(v, str) and k.endswith(('_frame', '_frame_id'))}
