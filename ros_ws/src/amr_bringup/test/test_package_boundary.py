"""車子系統套件的邊界：真車上只會安裝它，所以不能依賴任何模擬相關的套件。"""

from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SIM_ONLY = ('amr_hw_sim', 'amr_worlds')


def declared_dependencies():
    root = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    return {e.text.strip() for e in root if e.tag.endswith('depend') and e.text}


def test_no_gazebo_or_ros_gz_dependency():
    deps = declared_dependencies()
    assert not [d for d in deps if d.startswith(('ros_gz', 'ros_ign', 'ignition', 'gz'))], deps


def test_no_simulation_package_dependency():
    assert not declared_dependencies() & set(SIM_ONLY)


def test_python_code_does_not_import_simulation_packages():
    # 虛擬驅動只在 hardware: sim 時以「套件名稱」在執行期尋找，不在程式裡 import
    for path in (PACKAGE_DIR / 'amr_bringup').glob('*.py'):
        text = path.read_text(encoding='utf-8')
        for name in SIM_ONLY + ('ros_gz',):
            assert f'import {name}' not in text and f'from {name}' not in text, (path, name)
