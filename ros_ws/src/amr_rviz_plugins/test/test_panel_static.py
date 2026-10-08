"""建圖面板的靜態檢查：外掛描述、套件邊界、與導航套件的約定（存圖目錄、服務名稱、RViz 設定檔）。"""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

import yaml

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SRC = PACKAGE_DIR.parent
SIM_ONLY = ('amr_hw_sim', 'amr_worlds', 'ros_gz', 'ros_ign', 'ignition', 'gazebo')


def test_plugin_description():
    cls = ET.parse(PACKAGE_DIR / 'plugins_description.xml').getroot().find('class')
    assert cls.get('name') == 'amr_rviz_plugins/MappingPanel'
    assert cls.get('type') == 'amr_rviz_plugins::MappingPanel'
    assert cls.get('base_class_type') == 'rviz_common::Panel'
    source = (PACKAGE_DIR / 'src' / 'mapping_panel.cpp').read_text(encoding='utf-8')
    assert 'PLUGINLIB_EXPORT_CLASS(amr_rviz_plugins::MappingPanel, rviz_common::Panel)' in source


def test_no_simulation_dependency():
    root = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    deps = {e.text.strip() for e in root if e.tag.endswith('depend') and e.text}
    assert not [d for d in deps if d.startswith(SIM_ONLY)], deps


def test_maps_dir_matches_navigation_launch():
    # 面板存圖的目錄必須是導航載入地圖的目錄
    header = (PACKAGE_DIR / 'include' / 'amr_rviz_plugins' / 'mapping_panel.hpp').read_text(encoding='utf-8')
    maps_dir = re.search(r'kMapsDir = "([^"]+)"', header).group(1)
    launch = (SRC / 'amr_navigation' / 'launch' / 'navigation.launch.xml').read_text(encoding='utf-8')
    assert f'{maps_dir}/$(var map).yaml' in launch


def test_service_matches_mapping_launch():
    # 面板呼叫 /<id>/map_saver/save_map：建圖 launch 要有名為 map_saver 的 map_saver_server
    source = (PACKAGE_DIR / 'src' / 'mapping_panel.cpp').read_text(encoding='utf-8')
    assert '"/map_saver/save_map"' in source
    root = ET.parse(SRC / 'amr_navigation' / 'launch' / 'mapping.launch.xml').getroot()
    savers = [n for n in root.iter('node') if n.get('exec') == 'map_saver_server']
    assert [n.get('name') for n in savers] == ['map_saver']


def rviz_config(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def test_mapping_rviz_has_panel_and_no_navigation_displays():
    config = rviz_config(PACKAGE_DIR / 'config' / 'mapping.rviz')
    panels = [p for p in config['Panels'] if p['Class'] == 'amr_rviz_plugins/MappingPanel']
    assert len(panels) == 1
    assert panels[0]['robot_id'] == 'amr1'
    names = {d['Name'] for d in config['Visualization Manager']['Displays']}
    assert {'Map', 'LaserScan', 'RobotModel', 'TF'} <= names
    assert not names & {'Global Costmap', 'Local Costmap', 'AMCL Particles', 'Global Plan'}   # 建圖時沒有
    for display in config['Visualization Manager']['Displays']:
        if 'Topic' in display:
            assert display['Topic']['Value'].startswith('/amr1/'), display['Name']


def test_navigation_rviz_has_no_mapping_panel():
    # 導航時不需要建圖面板（使用者要求）
    config = rviz_config(SRC / 'amr_navigation' / 'config' / 'navigate.rviz')
    assert not [p for p in config['Panels'] if p['Class'].startswith('amr_rviz_plugins/')]


def test_mapping_ui_launch_opens_rviz_with_panel_config():
    root = ET.parse(PACKAGE_DIR / 'launch' / 'mapping_ui.launch.xml').getroot()
    includes = [i.get('file') for i in root.iter('include')]
    assert includes == ['$(find-pkg-share amr_navigation)/launch/mapping.launch.xml']
    rviz = [n for n in root.iter('node') if n.get('exec') == 'rviz2']
    assert len(rviz) == 1
    assert rviz[0].get('args') == '-d $(find-pkg-share amr_rviz_plugins)/config/mapping.rviz'
    assert rviz[0].get('ros_args') == '-p use_sim_time:=$(var use_sim_time)'


def test_map_origin_rviz_uses_namespaced_topics_and_tool():
    config = rviz_config(PACKAGE_DIR / 'config' / 'map_origin.rviz')
    vm = config['Visualization Manager']
    assert [p for p in config['Panels'] if p['Class'] == 'amr_rviz_plugins/MapOriginPanel']
    tools = [t for t in vm['Tools'] if t['Class'] == 'amr_rviz_plugins/SetOriginTool']
    assert len(tools) == 1 and tools[0]['Topic']['Value'] == '/amr1/map_origin/candidate'
    # 不應出現會被誤認為導航目標的工具
    assert not [t for t in vm['Tools'] if t['Class'] in ('rviz_default_plugins/SetGoal',
                                                         'rviz_default_plugins/SetInitialPose')]
    topics = {d['Name']: d['Topic']['Value'] for d in vm['Displays'] if 'Topic' in d}
    assert topics == {'Map': '/amr1/map_origin/map', '新原點': '/amr1/map_origin/candidate'}


def test_map_origin_ui_launch():
    root = ET.parse(PACKAGE_DIR / 'launch' / 'map_origin_ui.launch.xml').getroot()
    args = {a.get('name'): a for a in root.iter('arg')}
    assert args['map'].get('default') is None                    # 必填：不會改到預設地圖
    nodes = {n.get('name'): n for n in root.iter('node')}
    viewer = {p.get('name'): p.get('value') for p in nodes['map_origin_viewer'].iter('param')}
    assert viewer['yaml_filename'] == '/data/maps/$(var map).yaml'
    assert viewer['topic_name'] == 'map_origin/map'               # 和導航用的 map 分開
    assert nodes['map_origin_server'].get('pkg') == 'amr_navigation'
    assert nodes['rviz_map_origin'].get('args') == '-d $(find-pkg-share amr_rviz_plugins)/config/map_origin.rviz'


def test_map_origin_panel_targets_viewer_and_service():
    source = (PACKAGE_DIR / 'src' / 'map_origin_panel.cpp').read_text(encoding='utf-8')
    for name in ('"/map_origin/set"', '"/map_origin/candidate"', '"/map_origin_viewer/load_map"',
                 '"/map_origin_viewer/get_parameters"'):
        assert name in source, name
