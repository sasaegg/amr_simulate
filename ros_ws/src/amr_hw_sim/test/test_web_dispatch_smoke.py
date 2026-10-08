"""網頁派車端到端冒煙測試：headless 世界 + 車子系統（hardware=sim、mode=navigation）+ 中控後端。

只透過後端的 HTTP 與 WebSocket 操作（和網頁一樣），驗證 spec fleet-server：地圖、設定初始位姿、
派車到達（比對 Gazebo 真實位置）、目標到不了回報失敗、取消、錯誤碼。
地圖 warehouse_small（地圖座標 = Gazebo 世界座標）。方法依名稱排序執行。沒有 ROS 環境時整個檔案略過。
後端埠預設 8150（環境變數 WEB_SMOKE_PORT 可改），避免和使用者正在跑的後端（8000）撞埠。
"""

import json
import math
import os
from pathlib import Path
import subprocess
import time
import unittest
import urllib.error
import urllib.request

import pytest

launch_testing = pytest.importorskip('launch_testing')
websockets_client = pytest.importorskip('websockets.sync.client')

from ament_index_python.packages import get_package_share_directory  # noqa: E402
from launch import LaunchDescription  # noqa: E402
from launch.actions import IncludeLaunchDescription, TimerAction  # noqa: E402
from launch.launch_description_sources import AnyLaunchDescriptionSource  # noqa: E402
import launch_testing.actions  # noqa: E402
import yaml  # noqa: E402

ROBOT_ID = 'amr1'
WORLD = 'warehouse_small'
MAP = 'warehouse_small'
PORT = int(os.environ.get('WEB_SMOKE_PORT', '8150'))
BASE = f'http://127.0.0.1:{PORT}/api'
SPAWN = (1.0, 1.0)
REACHABLE_GOAL = (10.0, 1.0, math.pi / 2)
GOAL_IN_OBSTACLE = (7.0, 4.0, 0.0)       # 場景中 1 × 1 m 箱子的中心


def include(package, launch_file, **arguments):
    path = Path(get_package_share_directory(package)) / 'launch' / launch_file
    return IncludeLaunchDescription(AnyLaunchDescriptionSource(str(path)),
                                    launch_arguments=arguments.items())


@pytest.mark.launch_test
def generate_test_description():
    return LaunchDescription([
        include('amr_worlds', 'world.launch.xml', world=WORLD, headless='true'),
        TimerAction(period=3.0, actions=[
            include('amr_bringup', 'robot.launch.xml', hardware='sim', robot_id=ROBOT_ID,
                    x=str(SPAWN[0]), y=str(SPAWN[1]), yaw='0.0', mode='navigation', map=MAP),
        ]),
        include('amr_server', 'server.launch.xml', robots=ROBOT_ID, port=str(PORT),
                use_sim_time='true'),
        launch_testing.actions.ReadyToTest(),
    ])


def true_pose():
    """Gazebo 真實位姿 (x, y)；地圖座標 = 世界座標。"""
    out = subprocess.run(['ign', 'model', '-m', ROBOT_ID, '-p'],
                         capture_output=True, text=True, check=True).stdout
    lines = [ln.strip(' []') for ln in out.strip().splitlines()]
    x, y, _ = map(float, lines[-2].split())
    return x, y


def call(method, path, body=None):
    request = urllib.request.Request(
        BASE + path, method=method, headers={'content-type': 'application/json'},
        data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def call_json(method, path, body=None):
    status, data = call(method, path, body)
    return status, json.loads(data)


def wait_http(timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if call('GET', '/robots')[0] == 200:
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def watch(condition, timeout, seen=None):
    """接 WebSocket，直到 condition(amr1 的狀態) 成立；回傳最後一則。seen 收集看過的狀態。"""
    end = time.monotonic() + timeout
    state = None
    with websockets_client.connect(f'ws://127.0.0.1:{PORT}/api/ws') as ws:
        while time.monotonic() < end:
            state = json.loads(ws.recv(timeout=5))['robots'][ROBOT_ID]
            if seen is not None:
                seen.append(state)
            if condition(state):
                return state
    raise AssertionError(f'{timeout} s 內條件沒有成立，最後狀態 {state}')


class TestWebDispatchSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        assert wait_http(60), f'60 s 內後端 {BASE} 沒有回應'

    def test_01_map_matches_yaml(self):
        watch(lambda s: s['map_ready'], 60)
        status, info = call_json('GET', f'/robots/{ROBOT_ID}/map')
        self.assertEqual(status, 200)
        with open(f'/data/maps/{MAP}.yaml', encoding='utf-8') as f:
            expected = yaml.safe_load(f)
        self.assertEqual(info['resolution'], expected['resolution'])
        self.assertAlmostEqual(info['origin_x'], expected['origin'][0], places=6)
        self.assertAlmostEqual(info['origin_y'], expected['origin'][1], places=6)
        status, png = call('GET', f'/robots/{ROBOT_ID}/map.png')
        self.assertEqual(status, 200)
        self.assertTrue(png.startswith(b'\x89PNG'))

    def test_02_not_localized_before_initial_pose(self):
        status, robots = call_json('GET', '/robots')
        self.assertEqual(status, 200)
        self.assertEqual(robots[0]['id'], ROBOT_ID)
        self.assertFalse(robots[0]['pose_ready'])

    def test_03_initial_pose_localizes(self):
        status, _ = call_json('POST', f'/robots/{ROBOT_ID}/initial_pose',
                              {'x': SPAWN[0], 'y': SPAWN[1], 'yaw': 0.0})
        self.assertEqual(status, 202)
        state = watch(lambda s: s['pose'] is not None, 10)
        tx, ty = true_pose()
        self.assertLess(math.hypot(state['pose']['x'] - tx, state['pose']['y'] - ty), 0.3)

    def test_04_dispatch_reaches_goal(self):
        watch(lambda s: s['nav_ready'], 90)                    # Nav2 在初始位姿之後才全部啟動
        x, y, yaw = REACHABLE_GOAL
        status, _ = call_json('POST', f'/robots/{ROBOT_ID}/goal', {'x': x, 'y': y, 'yaw': yaw})
        self.assertEqual(status, 202)
        seen = []
        state = watch(lambda s: s['status'] != 'navigating', 120, seen)
        self.assertEqual(state['status'], 'succeeded', state['message'])
        self.assertEqual(state['goal'], {'x': x, 'y': y, 'yaw': yaw})
        self.assertTrue(any(s['plan'] for s in seen), '導航中沒有收到規劃路徑')
        tx, ty = true_pose()
        self.assertLess(math.hypot(x - tx, y - ty), 0.3)
        # WebSocket 的位置和真實位置一致
        self.assertLess(math.hypot(state['pose']['x'] - tx, state['pose']['y'] - ty), 0.3)

    def test_05_goal_inside_obstacle_fails(self):
        x, y, yaw = GOAL_IN_OBSTACLE
        status, _ = call_json('POST', f'/robots/{ROBOT_ID}/goal', {'x': x, 'y': y, 'yaw': yaw})
        self.assertEqual(status, 202)
        state = watch(lambda s: s['status'] != 'navigating', 150)
        self.assertEqual(state['status'], 'failed')
        self.assertTrue(state['message'])

    def test_06_cancel_stops_the_robot(self):
        status, _ = call_json('POST', f'/robots/{ROBOT_ID}/goal', {'x': 3.0, 'y': 1.0, 'yaw': 0.0})
        self.assertEqual(status, 202)
        watch(lambda s: s['status'] == 'navigating' and s['plan'], 30)
        time.sleep(2.0)
        status, _ = call_json('DELETE', f'/robots/{ROBOT_ID}/goal')
        self.assertEqual(status, 202)
        watch(lambda s: s['status'] == 'canceled', 10)
        time.sleep(1.5)                                          # 1 秒內要停下（spec），多等一點再量
        before = true_pose()
        time.sleep(1.0)
        after = true_pose()
        self.assertLess(math.hypot(after[0] - before[0], after[1] - before[1]), 0.03)

    def test_07_error_codes(self):
        self.assertEqual(call_json('DELETE', f'/robots/{ROBOT_ID}/goal')[0], 409)
        status, body = call_json('POST', f'/robots/{ROBOT_ID}/goal', {'x': 999, 'y': 1, 'yaw': 0})
        self.assertEqual(status, 422)
        self.assertIn('地圖範圍外', body['detail'])
        self.assertEqual(call_json('GET', '/robots/amr9/map')[0], 404)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_processes_exit_cleanly(self, proc_info):
        # 同導航冒煙測試：模擬器管線（Gazebo、parameter_bridge）關閉時偶爾異常，只警告；其他（含後端）必須正常結束
        simulator_plumbing = ('ign-', 'parameter_bridge-')
        for info in proc_info:
            if info.process_name.startswith(simulator_plumbing):
                if info.returncode not in (0, -2, 2, 130):
                    print(f'警告：{info.process_name} 以 {info.returncode} 結束（模擬器管線關閉時異常）')
                continue
            self.assertIn(info.returncode, [0, -2, 2, 130],
                          f'{info.process_name} 以 {info.returncode} 結束')
