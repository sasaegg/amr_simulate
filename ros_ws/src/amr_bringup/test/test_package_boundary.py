"""車子系統套件的邊界：真車上只會安裝它，所以不能依賴任何模擬相關的套件。"""

from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE_DIR = Path(__file__).resolve().parents[1]
LAUNCH_FILE = PACKAGE_DIR / 'launch' / 'robot.launch.xml'
SIM_ONLY = ('amr_hw_sim', 'amr_worlds')


def declared_dependencies():
    root = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    return {e.text.strip() for e in root if e.tag.endswith('depend') and e.text}


def test_no_gazebo_or_ros_gz_dependency():
    deps = declared_dependencies()
    assert not [d for d in deps if d.startswith(('ros_gz', 'ros_ign', 'ignition', 'gz'))], deps


def test_no_simulation_package_dependency():
    assert not declared_dependencies() & set(SIM_ONLY)


def test_simulation_packages_are_only_used_when_hardware_is_sim():
    # 虛擬驅動只在 hardware=sim 時以「套件名稱」在執行期尋找；其他地方不能提到模擬套件
    root = ET.parse(LAUNCH_FILE).getroot()
    sim_groups = [g for g in root.iter('group') if g.get('if') == '$(var is_sim)']
    assert len(sim_groups) == 1
    inside = ET.tostring(sim_groups[0], encoding='unicode')
    sim_groups[0].clear()
    outside = ET.tostring(root, encoding='unicode')
    assert 'amr_hw_sim' in inside
    for name in SIM_ONLY + ('ros_gz',):
        assert name not in outside, name


def test_hardware_has_no_default():
    # 必須明確指定 sim 或 real：不給預設值，沒傳就會被 launch 擋下
    args = {a.get('name'): a for a in ET.parse(LAUNCH_FILE).getroot().iter('arg')
            if a.get('name') and a.get('value') is None}
    assert 'hardware' in args
    assert args['hardware'].get('default') is None
