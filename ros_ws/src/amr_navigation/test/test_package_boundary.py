"""建圖／導航套件的邊界：屬於車子系統，真車上也會安裝，所以不能依賴或引用任何模擬相關的套件。"""

from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SIM_ONLY = ('amr_hw_sim', 'amr_worlds', 'ros_gz', 'ros_ign', 'ignition', 'gazebo')


def declared_dependencies():
    root = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    return {e.text.strip() for e in root if e.tag.endswith('depend') and e.text}


def package_files():
    return [p for d in ('launch', 'config') for p in sorted((PACKAGE_DIR / d).glob('*'))
            if p.is_file() and p.name != '.gitkeep']


def test_no_simulation_dependency():
    deps = declared_dependencies()
    assert not [d for d in deps if d.startswith(SIM_ONLY)], deps


def test_launch_and_config_do_not_mention_simulation_packages():
    # launch／參數檔也不能以套件名稱引用模擬套件（例如 $(find-pkg-share amr_hw_sim)）
    for path in package_files():
        text = path.read_text(encoding='utf-8')
        for name in SIM_ONLY:
            assert name not in text, (path.name, name)


def test_depends_on_slam_and_nav2():
    deps = declared_dependencies()
    assert 'slam_toolbox' in deps
    assert {'nav2_map_server', 'nav2_amcl', 'nav2_lifecycle_manager', 'nav2_bt_navigator'} <= deps
