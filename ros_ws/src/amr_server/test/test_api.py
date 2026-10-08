"""API 測試：以假的 bridge 取代 ROS，逐一檢查 specs/fleet-server 的狀態碼與訊息格式。"""

from fastapi.testclient import TestClient
import pytest

from amr_server.api import create_app
from amr_server.bridge import NavigationUnavailable, NoActiveGoal
from amr_server.state import FAILED, IDLE, NAVIGATING, MapInfo, Pose2D, RobotState

# 地圖範圍 x ∈ [−0.5, 19.5)、y ∈ [−0.5, 14.5)
MAP = MapInfo(width=400, height=300, resolution=0.05, origin_x=-0.5, origin_y=-0.5, version=3)


class FakeBridge:
    def __init__(self, map_info=MAP, nav_running=True):
        self._map = map_info
        self.nav_running = nav_running
        self.goals = []
        self.initial_poses = []
        self.canceled = 0
        self.current = RobotState(map_version=map_info.version if map_info else 0,
                                  map_ready=map_info is not None, nav_ready=nav_running)

    def state(self):
        return self.current

    def map_info(self):
        return self._map

    def map_png(self):
        return b'\x89PNG fake' if self._map else None

    def send_goal(self, x, y, yaw):
        if not self.nav_running:
            raise NavigationUnavailable('amr1 的導航沒有在執行')
        self.goals.append((x, y, yaw))
        self.current.status = NAVIGATING
        self.current.goal = Pose2D(x, y, yaw)

    def cancel(self):
        if self.current.status != NAVIGATING:
            raise NoActiveGoal('沒有進行中的目標')
        self.canceled += 1

    def set_initial_pose(self, x, y, yaw):
        self.initial_poses.append((x, y, yaw))


@pytest.fixture
def bridge():
    return FakeBridge()


@pytest.fixture
def client(bridge, tmp_path):
    return TestClient(create_app({'amr1': bridge}, web_dir=str(tmp_path / 'no_dist'), push_period=0.01))


# ---- 車輛清單 ----

def test_list_robots(client, bridge):
    bridge.current.pose = Pose2D(1.0, 1.0, 0.0)
    assert client.get('/api/robots').json() == [
        {'id': 'amr1', 'map_ready': True, 'pose_ready': True, 'nav_ready': True}]


def test_list_robots_not_ready(tmp_path):
    client = TestClient(create_app({'amr1': FakeBridge(map_info=None, nav_running=False)}, web_dir=None))
    assert client.get('/api/robots').json() == [
        {'id': 'amr1', 'map_ready': False, 'pose_ready': False, 'nav_ready': False}]


@pytest.mark.parametrize('method, path', [
    ('get', '/api/robots/amr9/map'),
    ('get', '/api/robots/amr9/map.png'),
    ('post', '/api/robots/amr9/goal'),
    ('delete', '/api/robots/amr9/goal'),
    ('post', '/api/robots/amr9/initial_pose'),
])
def test_unknown_robot_is_404(client, method, path):
    response = getattr(client, method)(path, **({'json': {'x': 1, 'y': 1, 'yaw': 0}} if method == 'post' else {}))
    assert response.status_code == 404
    assert 'amr9' in response.json()['detail']


# ---- 地圖 ----

def test_map_info(client):
    assert client.get('/api/robots/amr1/map').json() == {
        'width': 400, 'height': 300, 'resolution': 0.05, 'origin_x': -0.5, 'origin_y': -0.5, 'version': 3}


def test_map_png(client):
    response = client.get('/api/robots/amr1/map.png')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.content == b'\x89PNG fake'


@pytest.mark.parametrize('path', ['/api/robots/amr1/map', '/api/robots/amr1/map.png'])
def test_map_not_received_is_503(path):
    client = TestClient(create_app({'amr1': FakeBridge(map_info=None)}, web_dir=None))
    response = client.get(path)
    assert response.status_code == 503
    assert '地圖' in response.json()['detail']


# ---- 派車 ----

def test_send_goal(client, bridge):
    response = client.post('/api/robots/amr1/goal', json={'x': 10, 'y': 1, 'yaw': 1.57})
    assert response.status_code == 202
    assert bridge.goals == [(10.0, 1.0, 1.57)]


@pytest.mark.parametrize('body', [
    {'x': 999, 'y': 1, 'yaw': 0},
    {'x': 1, 'y': -0.51, 'yaw': 0},
    {'x': 19.5, 'y': 1, 'yaw': 0},
])
def test_goal_outside_map_is_422(client, bridge, body):
    response = client.post('/api/robots/amr1/goal', json=body)
    assert response.status_code == 422
    assert '地圖範圍外' in response.json()['detail']
    assert bridge.goals == []


@pytest.mark.parametrize('content', [
    '{"x": 1, "y": 1, "yaw": NaN}',
    '{"x": Infinity, "y": 1, "yaw": 0}',
    '{"x": 1, "yaw": 0}',
    '{"x": "a", "y": 1, "yaw": 0}',
    'not json',
])
def test_invalid_goal_is_422(client, bridge, content):
    response = client.post('/api/robots/amr1/goal', content=content,
                           headers={'content-type': 'application/json'})
    assert response.status_code == 422
    assert response.json()['detail'].startswith('輸入不正確')
    assert bridge.goals == []


def test_goal_when_navigation_not_running_is_503(tmp_path):
    bridge = FakeBridge(nav_running=False)
    client = TestClient(create_app({'amr1': bridge}, web_dir=None))
    response = client.post('/api/robots/amr1/goal', json={'x': 1, 'y': 1, 'yaw': 0})
    assert response.status_code == 503
    assert '導航' in response.json()['detail']


def test_goal_without_map_is_503():
    client = TestClient(create_app({'amr1': FakeBridge(map_info=None)}, web_dir=None))
    response = client.post('/api/robots/amr1/goal', json={'x': 1, 'y': 1, 'yaw': 0})
    assert response.status_code == 503


# ---- 取消 ----

def test_cancel(client, bridge):
    client.post('/api/robots/amr1/goal', json={'x': 10, 'y': 1, 'yaw': 0})
    response = client.delete('/api/robots/amr1/goal')
    assert response.status_code == 202
    assert bridge.canceled == 1


def test_cancel_without_goal_is_409(client, bridge):
    response = client.delete('/api/robots/amr1/goal')
    assert response.status_code == 409
    assert response.json()['detail']
    assert bridge.canceled == 0


# ---- 初始位姿 ----

def test_initial_pose(client, bridge):
    response = client.post('/api/robots/amr1/initial_pose', json={'x': 1, 'y': 1, 'yaw': 0})
    assert response.status_code == 202
    assert bridge.initial_poses == [(1.0, 1.0, 0.0)]


def test_initial_pose_outside_map_is_422(client, bridge):
    response = client.post('/api/robots/amr1/initial_pose', json={'x': 1, 'y': 99, 'yaw': 0})
    assert response.status_code == 422
    assert bridge.initial_poses == []


# ---- WebSocket ----

def test_websocket_pushes_all_robots(client, bridge):
    bridge.current.pose = Pose2D(3.2, 1.0, 0.1)
    bridge.current.goal = Pose2D(10.0, 1.0, 0.0)
    bridge.current.status = NAVIGATING
    bridge.current.distance_remaining = 6.8
    bridge.current.plan = [(3.2, 1.0), (3.3, 1.0)]
    with client.websocket_connect('/api/ws') as ws:
        message = ws.receive_json()
    assert message == {'robots': {'amr1': {
        'pose': {'x': 3.2, 'y': 1.0, 'yaw': 0.1},
        'goal': {'x': 10.0, 'y': 1.0, 'yaw': 0.0},
        'status': 'navigating',
        'message': '',
        'distance_remaining': 6.8,
        'plan': [[3.2, 1.0], [3.3, 1.0]],
        'map_version': 3,
        'map_ready': True,
        'nav_ready': True,
    }}}


def test_websocket_null_pose_and_updates(client, bridge):
    with client.websocket_connect('/api/ws') as ws:
        first = ws.receive_json()['robots']['amr1']
        bridge.current.status = FAILED
        bridge.current.message = 'Nav2 放棄（到不了或卡住）'
        for _ in range(20):                         # 推送是週期性的，下一則（或再下一則）就會反映
            later = ws.receive_json()['robots']['amr1']
            if later['status'] == FAILED:
                break
    assert first['pose'] is None and first['goal'] is None and first['status'] == IDLE
    assert later['status'] == FAILED and later['message'] == 'Nav2 放棄（到不了或卡住）'


# ---- 網頁 ----

def test_root_explains_how_to_build_when_web_missing(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'npm run build' in response.text
    assert client.get('/api/robots').status_code == 200


def test_serves_built_web(tmp_path, bridge):
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html>operator</html>', encoding='utf-8')
    (dist / 'app.js').write_text('console.log(1)', encoding='utf-8')
    client = TestClient(create_app({'amr1': bridge}, web_dir=str(dist)))
    assert client.get('/').text == '<html>operator</html>'
    assert client.get('/app.js').text == 'console.log(1)'
    assert client.get('/api/robots').status_code == 200          # API 不被靜態檔蓋掉

