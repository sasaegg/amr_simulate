"""server.launch.xml 的參數與預設值（specs/sim-runtime「執行設定」）。"""

from pathlib import Path
import xml.etree.ElementTree as ET

LAUNCH = Path(__file__).resolve().parents[1] / 'launch' / 'server.launch.xml'


def parse():
    return ET.parse(LAUNCH).getroot()


def test_arguments_and_defaults():
    args = {a.get('name'): a.get('default') for a in parse().iter('arg')}
    assert args == {'robots': 'amr1', 'host': '127.0.0.1', 'port': '8000',
                    'web_dir': '/web/dist', 'use_sim_time': 'false'}


def test_node_gets_every_argument():
    node = parse().find('node')
    assert (node.get('pkg'), node.get('exec')) == ('amr_server', 'server')
    params = {p.get('name'): p.get('value') for p in node.iter('param')}
    assert params == {name: f'$(var {name})' for name in ('robots', 'host', 'port', 'web_dir')}


def test_use_sim_time_is_process_wide():
    # 和車子系統一樣用 ros_args，不用 <param>（筆記 19：<param> 只套用到主節點）
    node = parse().find('node')
    assert node.get('ros_args') == '-p use_sim_time:=$(var use_sim_time)'
