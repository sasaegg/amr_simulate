"""實際執行 robot.launch.xml，檢查 hardware 的必填與錯誤值處理（需要 ROS 環境，否則略過）。

hardware=sim 的正常啟動由 amr_hw_sim 的冒煙測試涵蓋（需要世界）。
"""

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which('ros2') is None, reason='需要 ROS 環境')


def launch(*arguments):
    result = subprocess.run(['ros2', 'launch', 'amr_bringup', 'robot.launch.xml', *arguments],
                            capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout + result.stderr


def test_hardware_is_required():
    code, output = launch()
    assert code != 0
    assert "missing required argument 'hardware'" in output


def test_real_is_not_available_yet():
    code, output = launch('hardware:=real')
    assert '尚未提供真車驅動' in output
    assert 'robot_state_publisher' not in output   # 沒有啟動任何節點就結束


@pytest.mark.parametrize('value', ['foo', 'SIM', 'Sim'])
def test_rejects_unknown_hardware(value):
    code, output = launch(f'hardware:={value}')
    assert f"hardware 必須是 sim 或 real，收到 '{value}'" in output
    assert 'robot_state_publisher' not in output


@pytest.mark.parametrize('value', ['foo', 'Mapping', 'nav'])
def test_rejects_unknown_mode(value):
    code, output = launch('hardware:=sim', f'mode:={value}')
    assert f"mode 必須是 none、mapping 或 navigation，收到 '{value}'" in output
    assert 'robot_state_publisher' not in output
