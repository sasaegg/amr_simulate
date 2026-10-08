"""標地圖原點的服務節點：在同一個程序裡啟動節點，用服務客戶端呼叫（需要 ROS 環境，否則略過）。"""

import math
import threading

import pytest

rclpy = pytest.importorskip('rclpy')
SetMapOrigin = pytest.importorskip('amr_interfaces.srv').SetMapOrigin

from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.parameter import Parameter  # noqa: E402

from amr_navigation.map_origin_server import MapOriginServer  # noqa: E402
from test_map_origin import load, make_map, ORIGIN  # noqa: E402


@pytest.fixture
def call(tmp_path):
    """啟動節點（maps_dir = tmp_path）並回傳呼叫服務的函式。"""
    rclpy.init()
    server = MapOriginServer()
    server.set_parameters([Parameter('maps_dir', value=str(tmp_path))])
    client_node = rclpy.create_node('map_origin_test_client')
    client = client_node.create_client(SetMapOrigin, 'map_origin/set')
    executor = SingleThreadedExecutor()
    executor.add_node(server)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()

    def _call(name, x, y, yaw):
        assert client.wait_for_service(timeout_sec=5)
        request = SetMapOrigin.Request(map_name=name, x=x, y=y, yaw=yaw)
        future = client.call_async(request)
        rclpy.spin_until_future_complete(client_node, future, timeout_sec=5)
        return future.result()

    yield _call
    executor.shutdown()
    server.destroy_node()
    client_node.destroy_node()
    rclpy.shutdown()


def test_success_rewrites_map(tmp_path, call):
    make_map(tmp_path)
    response = call('m', 1.0, 0.5, 0.0)
    assert response.success, response.message
    assert 'm.bak' in response.message
    _, meta = load(tmp_path)
    assert meta['origin'] == pytest.approx([ORIGIN[0] - 1.0, ORIGIN[1] - 0.5, 0.0])


def test_right_angle_via_service(tmp_path, call):
    make_map(tmp_path)
    assert call('m', 0.0, 0.0, math.pi / 2).success
    image, _ = load(tmp_path)
    assert image.shape == (20, 10)                               # 寬高互換


@pytest.mark.parametrize('name', ['nope', '../etc'])
def test_failure_is_reported(tmp_path, call, name):
    response = call(name, 0.0, 0.0, 0.0)
    assert not response.success
    assert response.message
    assert list(tmp_path.iterdir()) == []
