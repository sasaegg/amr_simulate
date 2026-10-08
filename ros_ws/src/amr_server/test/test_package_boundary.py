"""中控後端的邊界：只用車子系統的標準介面，真車部署時不用改，所以不能依賴或引用任何模擬套件。"""

from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SIM_ONLY = ('amr_hw_sim', 'amr_worlds', 'ros_gz', 'ros_ign', 'ignition', 'gazebo')


def declared_dependencies():
    root = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    return {e.text.strip() for e in root if e.tag.endswith('depend') and e.text}


def source_files():
    files = sorted((PACKAGE_DIR / 'amr_server').glob('*.py'))
    files += sorted((PACKAGE_DIR / 'launch').glob('*.launch.xml'))
    return files


def test_no_simulation_dependency():
    deps = declared_dependencies()
    assert not [d for d in deps if d.startswith(SIM_ONLY)], deps


def test_sources_do_not_mention_simulation_packages():
    for path in source_files():
        text = path.read_text(encoding='utf-8')
        for name in SIM_ONLY:
            assert name not in text, (path.name, name)
