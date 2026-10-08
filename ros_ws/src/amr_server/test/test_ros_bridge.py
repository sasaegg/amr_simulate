"""RosRobotBridge 整合測試：同一個程序裡放假的 NavigateToPose action server、TF 與地圖／路徑發布者。

不需要 Gazebo 與 Nav2，幾秒跑完。車輛 id 用 tst1（不和使用者可能正在跑的 amr1 撞名）。
"""

import math
import threading
import time

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Path
import pytest
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger
from tf2_ros import TransformBroadcaster

from amr_server.bridge import NavigationUnavailable, NoActiveGoal
from amr_server.ros_bridge import FleetNode
from amr_server.state import CANCELED, FAILED, IDLE, NAVIGATING, SUCCEEDED

ROBOT = 'tst1'


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class FakeCar(Node):
    """假的車子系統：navigate_to_pose action server、TF、地圖、路徑；也收 initialpose。

    目標的行為由 x 座標決定（behaviors[x]）：
      'succeed'       0.3 s 後成功（過程中送 feedback 與路徑）
      'reject'        拒絕目標
      'abort'         0.3 s 後放棄
      'until_cancel'  一直執行，直到被取消
      'hold'          等到 release[x] 被設定，再以 release 的結果結束
    """

    def __init__(self):
        super().__init__('fake_car')
        group = ReentrantCallbackGroup()
        self.behaviors = {}
        self.release = {}
        self.server = ActionServer(
            self, NavigateToPose, f'/{ROBOT}/navigate_to_pose',
            execute_callback=self.execute, goal_callback=self.on_goal,
            cancel_callback=lambda _: CancelResponse.ACCEPT, callback_group=group)
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.map_pub = self.create_publisher(OccupancyGrid, f'/{ROBOT}/map', latched)
        self.plan_pub = self.create_publisher(Path, f'/{ROBOT}/plan', 10)
        self.initial_poses = []
        self.create_subscription(PoseWithCovarianceStamped, f'/{ROBOT}/initialpose',
                                 self.initial_poses.append, 10)
        self.nav_active = True
        self.create_service(Trigger, f'/{ROBOT}/lifecycle_manager_navigation/is_active',
                            self.on_is_active, callback_group=group)
        self.tf = TransformBroadcaster(self)
        self.pose = (1.0, 2.0, 0.5)
        self.broadcast = True
        self.create_timer(0.05, self.publish_tf, callback_group=group)

    def on_is_active(self, request, response):
        response.success = self.nav_active
        return response

    def publish_tf(self):
        if not self.broadcast:
            return
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'map'
        t.child_frame_id = f'{ROBOT}/base_footprint'
        t.transform.translation.x, t.transform.translation.y = self.pose[0], self.pose[1]
        t.transform.rotation.z = math.sin(self.pose[2] / 2)
        t.transform.rotation.w = math.cos(self.pose[2] / 2)
        self.tf.sendTransform(t)

    def publish_map(self, width=40, height=20, origin=(-1.0, -0.5)):
        grid = OccupancyGrid()
        grid.header.frame_id = 'map'
        grid.info.width, grid.info.height, grid.info.resolution = width, height, 0.05
        grid.info.origin.position.x, grid.info.origin.position.y = origin
        grid.info.origin.orientation.w = 1.0
        grid.data = [0] * (width * height)
        grid.data[0] = 100
        self.map_pub.publish(grid)

    def publish_plan(self, n=101):
        path = Path()
        path.header.frame_id = 'map'
        for i in range(n):
            p = PoseStamped()
            p.pose.position.x = i * 0.01
            path.poses.append(p)
        self.plan_pub.publish(path)

    def on_goal(self, request):
        x = request.pose.pose.position.x
        return GoalResponse.REJECT if self.behaviors.get(x) == 'reject' else GoalResponse.ACCEPT

    def execute(self, goal_handle):
        x = goal_handle.request.pose.pose.position.x
        behavior = self.behaviors.get(x, 'succeed')
        feedback = NavigateToPose.Feedback()
        if behavior == 'until_cancel':
            while not goal_handle.is_cancel_requested:
                feedback.distance_remaining = 5.0
                goal_handle.publish_feedback(feedback)
                time.sleep(0.05)
            goal_handle.canceled()
            return NavigateToPose.Result()
        if behavior == 'hold':
            while x not in self.release:
                time.sleep(0.02)
            outcome = self.release[x]
        else:
            for remaining in (3.0, 2.0, 1.0):
                feedback.distance_remaining = remaining
                goal_handle.publish_feedback(feedback)
                self.publish_plan()
                time.sleep(0.1)
            outcome = behavior
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
        elif outcome == 'succeed':
            goal_handle.succeed()
        else:
            goal_handle.abort()
        return NavigateToPose.Result()


@pytest.fixture(scope='module')
def ros():
    rclpy.init()
    car = FakeCar()
    fleet = FleetNode([ROBOT, 'nocar'], pose_timeout=0.5)
    car_executor = MultiThreadedExecutor()
    car_executor.add_node(car)
    fleet_executor = SingleThreadedExecutor()          # 和 main.py 一樣：ROS 回呼都在同一個執行緒
    fleet_executor.add_node(fleet)
    threads = [threading.Thread(target=e.spin, daemon=True) for e in (car_executor, fleet_executor)]
    for t in threads:
        t.start()
    assert wait_until(lambda: fleet.bridges[ROBOT].state().nav_ready, 10.0)
    yield car, fleet
    car_executor.shutdown()
    fleet_executor.shutdown()
    rclpy.shutdown()


@pytest.fixture
def car(ros):
    car, _ = ros
    car.behaviors.clear()
    car.release.clear()
    car.broadcast = True
    car.nav_active = True
    return car


@pytest.fixture
def bridge(ros, car):
    bridge = ros[1].bridges[ROBOT]
    # 前一個測試留下的目標要先結束
    assert wait_until(lambda: bridge.state().status != NAVIGATING, 10.0)
    return bridge


def test_initial_state_before_any_goal(ros):
    state = ros[1].bridges['nocar'].state()
    assert state.status == IDLE
    assert state.goal is None
    assert state.map_ready is False and state.nav_ready is False
    assert ros[1].bridges['nocar'].map_info() is None
    assert ros[1].bridges['nocar'].map_png() is None


def test_pose_from_tf(bridge):
    assert wait_until(lambda: bridge.state().pose is not None)
    pose = bridge.state().pose
    assert (pose.x, pose.y, pose.yaw) == pytest.approx((1.0, 2.0, 0.5), abs=1e-6)


def test_pose_becomes_none_when_tf_stops(bridge, car):
    assert wait_until(lambda: bridge.state().pose is not None)
    car.broadcast = False
    assert wait_until(lambda: bridge.state().pose is None, 3.0)       # pose_timeout 0.5 s
    car.broadcast = True
    assert wait_until(lambda: bridge.state().pose is not None)


def test_map_info_png_and_version(bridge, car):
    car.publish_map()
    assert wait_until(lambda: bridge.map_info() is not None)
    info = bridge.map_info()
    assert (info.width, info.height, info.resolution, info.origin_x, info.origin_y) == (40, 20, 0.05, -1.0, -0.5)
    assert bridge.map_png().startswith(b'\x89PNG')
    assert bridge.state().map_ready
    version = info.version
    car.publish_map(width=60)
    assert wait_until(lambda: bridge.map_info().version == version + 1)
    assert bridge.map_info().width == 60
    assert bridge.state().map_version == version + 1


def test_goal_succeeds_with_feedback_and_plan(bridge, car):
    bridge.send_goal(10.0, 1.0, 1.57)
    state = bridge.state()
    assert state.status == NAVIGATING
    assert (state.goal.x, state.goal.y, state.goal.yaw) == (10.0, 1.0, 1.57)
    assert wait_until(lambda: bridge.state().distance_remaining is not None)
    assert wait_until(lambda: len(bridge.state().plan) > 0)
    assert len(bridge.state().plan) == 11                      # 1 m、每 1 cm 一點 → 降取樣成每 0.1 m
    assert wait_until(lambda: bridge.state().status == SUCCEEDED)
    assert bridge.state().plan == []
    assert bridge.state().message == ''


def test_goal_rejected(bridge, car):
    car.behaviors[11.0] = 'reject'
    bridge.send_goal(11.0, 1.0, 0.0)
    assert wait_until(lambda: bridge.state().status == FAILED)
    assert '拒絕' in bridge.state().message


def test_goal_aborted(bridge, car):
    car.behaviors[12.0] = 'abort'
    bridge.send_goal(12.0, 1.0, 0.0)
    assert wait_until(lambda: bridge.state().status == FAILED)
    assert '放棄' in bridge.state().message


def test_cancel(bridge, car):
    car.behaviors[13.0] = 'until_cancel'
    bridge.send_goal(13.0, 1.0, 0.0)
    assert wait_until(lambda: bridge.state().distance_remaining == 5.0)
    bridge.cancel()
    assert wait_until(lambda: bridge.state().status == CANCELED)


def test_cancel_right_after_send(bridge, car):
    # 目標還在等 Nav2 接受時就取消：接受後要立刻取消
    car.behaviors[14.0] = 'until_cancel'
    bridge.send_goal(14.0, 1.0, 0.0)
    bridge.cancel()
    assert wait_until(lambda: bridge.state().status == CANCELED)


def test_cancel_without_goal(bridge):
    assert wait_until(lambda: bridge.state().status != NAVIGATING)
    with pytest.raises(NoActiveGoal):
        bridge.cancel()


def test_new_goal_replaces_old_and_late_result_is_ignored(bridge, car):
    car.behaviors[15.0] = 'hold'
    bridge.send_goal(15.0, 1.0, 0.0)
    assert wait_until(lambda: car.server is not None and bridge.state().status == NAVIGATING)
    time.sleep(0.3)                                             # 讓舊目標確實被接受
    bridge.send_goal(16.0, 2.0, 0.0)                            # 新目標（預設 succeed）
    assert wait_until(lambda: bridge.state().status == SUCCEEDED)
    car.release[15.0] = 'abort'                                 # 舊目標的結果現在才到
    time.sleep(0.5)
    state = bridge.state()
    assert state.status == SUCCEEDED
    assert (state.goal.x, state.goal.y) == (16.0, 2.0)


def test_send_goal_without_navigation(ros):
    nocar = ros[1].bridges['nocar']
    start = time.monotonic()
    with pytest.raises(NavigationUnavailable):
        nocar.send_goal(1.0, 1.0, 0.0)
    assert time.monotonic() - start < 2.0
    assert nocar.state().status == IDLE


def test_navigation_still_starting(ros, car):
    # action server 已存在，但 Nav2 的節點還沒全部 active（例如還在等初始位姿）：不能派車
    bridge = ros[1].bridges[ROBOT]
    assert wait_until(lambda: bridge.state().status != NAVIGATING, 10.0)
    car.nav_active = False
    assert wait_until(lambda: not bridge.state().nav_ready, 3.0)
    status = bridge.state().status
    with pytest.raises(NavigationUnavailable, match='還在啟動'):
        bridge.send_goal(1.0, 1.0, 0.0)
    assert bridge.state().status == status
    car.nav_active = True
    assert wait_until(lambda: bridge.state().nav_ready, 3.0)


def test_initial_pose_message(bridge, car):
    count = len(car.initial_poses)
    bridge.set_initial_pose(1.0, 2.0, math.pi / 2)
    assert wait_until(lambda: len(car.initial_poses) > count)
    msg = car.initial_poses[-1]
    assert msg.header.frame_id == 'map'
    assert (msg.pose.pose.position.x, msg.pose.pose.position.y) == (1.0, 2.0)
    assert (msg.pose.pose.orientation.z, msg.pose.pose.orientation.w) == pytest.approx(
        (math.sqrt(0.5), math.sqrt(0.5)))
    cov = msg.pose.covariance
    assert cov[0] == pytest.approx(0.25) and cov[7] == pytest.approx(0.25)
    assert cov[35] == pytest.approx(0.06853891945200942)


def test_goal_status_constants_used_by_bridge():
    # Humble 的 NavigateToPose 結果沒有錯誤碼，只能看 action 的結束狀態
    assert (GoalStatus.STATUS_SUCCEEDED, GoalStatus.STATUS_CANCELED, GoalStatus.STATUS_ABORTED) == (4, 5, 6)
