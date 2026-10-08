"""導航冒煙測試：headless 世界 + 車子系統（hardware=sim，出生點 (1, 1)）+ 另外啟動 navigation.launch.xml。

驗證 spec navigation：載入地圖、給初始位姿後定位、導航到目標（速度上限、到達誤差）、目標不可達時回報失敗。
地圖預設 warehouse_small（repo 內的地圖，原點已標在倉庫左下角：地圖座標 = Gazebo 世界座標，
change add-map-origin D5）；
開發時可用環境變數 NAV_SMOKE_MAP 換成別的地圖。方法依名稱排序執行。沒有 ROS 環境時整個檔案略過。
"""

import math
import os
from pathlib import Path
import subprocess
import time
import unittest

import pytest

launch_testing = pytest.importorskip('launch_testing')

from action_msgs.msg import GoalStatus  # noqa: E402
from ament_index_python.packages import get_package_share_directory  # noqa: E402
from geometry_msgs.msg import PoseWithCovarianceStamped  # noqa: E402
from launch import LaunchDescription  # noqa: E402
from launch.actions import IncludeLaunchDescription, TimerAction  # noqa: E402
from launch.launch_description_sources import AnyLaunchDescriptionSource  # noqa: E402
import launch_testing.actions  # noqa: E402
from nav2_msgs.action import NavigateToPose  # noqa: E402
from nav_msgs.msg import OccupancyGrid, Odometry  # noqa: E402
import rclpy  # noqa: E402
from rclpy.action import ActionClient  # noqa: E402
from rclpy.qos import DurabilityPolicy, QoSProfile  # noqa: E402
import rclpy.time  # noqa: E402
from std_srvs.srv import Trigger  # noqa: E402
from tf2_ros import Buffer, TransformListener  # noqa: E402

ROBOT_ID = 'amr1'
WORLD = 'warehouse_small'
MAP = os.environ.get('NAV_SMOKE_MAP', 'warehouse_small')
# 以下都是世界座標，也就是地圖座標（地圖原點標在倉庫左下角）
SPAWN = (1.0, 1.0)                 # 出生點
REACHABLE_GOAL = (10.0, 1.0)       # 沿南牆的開闊通道
GOAL_IN_OBSTACLE = (7.0, 4.0)      # 場景中 1 × 1 m 箱子的中心
NAV_NODES = ('map_server', 'amcl', 'controller_server', 'smoother_server', 'planner_server',
             'behavior_server', 'bt_navigator', 'waypoint_follower', 'velocity_smoother')


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
                    x=str(SPAWN[0]), y=str(SPAWN[1]), yaw='0.0'),
        ]),
        TimerAction(period=8.0, actions=[
            include('amr_navigation', 'navigation.launch.xml',
                    robot_id=ROBOT_ID, use_sim_time='true', map=MAP),
        ]),
        launch_testing.actions.ReadyToTest(),
    ])


def true_pose_in_map():
    """Gazebo 真實位姿 (x, y, yaw)；地圖座標 = 世界座標，不需換算。"""
    out = subprocess.run(['ign', 'model', '-m', ROBOT_ID, '-p'],
                         capture_output=True, text=True, check=True).stdout
    lines = [ln.strip(' []') for ln in out.strip().splitlines()]
    x, y, _ = map(float, lines[-2].split())
    yaw = float(lines[-1].split()[2])
    return x, y, yaw


class TestNavigationSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('navigation_smoke_test')
        cls.latest = {'vmax': 0.0}
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        cls.node.create_subscription(OccupancyGrid, f'/{ROBOT_ID}/map',
                                     lambda m: cls.latest.__setitem__('map', m), qos)
        cls.node.create_subscription(Odometry, f'/{ROBOT_ID}/odom', cls.on_odom, 10)
        cls.initial_pose = cls.node.create_publisher(
            PoseWithCovarianceStamped, f'/{ROBOT_ID}/initialpose', 10)
        cls.navigate = ActionClient(cls.node, NavigateToPose, f'/{ROBOT_ID}/navigate_to_pose')
        cls.nav_is_active = cls.node.create_client(
            Trigger, f'/{ROBOT_ID}/lifecycle_manager_navigation/is_active')
        cls.tf_buffer = Buffer()
        cls.tf_listener = TransformListener(cls.tf_buffer, cls.node)

    @classmethod
    def on_odom(cls, msg):
        cls.latest['odom'] = msg
        cls.latest['vmax'] = max(cls.latest['vmax'], abs(msg.twist.twist.linear.x))

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    # ---------- 小工具 ----------

    def spin_until(self, condition, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rclpy.spin_once(self.node, timeout_sec=0.05)
            if condition():
                return True
        return False

    def estimate(self):
        t = self.tf_buffer.lookup_transform('map', f'{ROBOT_ID}/base_footprint',
                                            rclpy.time.Time()).transform
        return t.translation.x, t.translation.y

    def wait_navigation_active(self, timeout):
        # 導航節點要等 map 的 TF（給初始位姿後）才會 active；之前送的目標會被拒絕
        self.assertTrue(self.nav_is_active.wait_for_service(timeout_sec=timeout))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            future = self.nav_is_active.call_async(Trigger.Request())
            if self.spin_until(future.done, 5) and future.result().success:
                return
            self.spin_until(lambda: False, 1.0)
        self.fail(f'{timeout} s 內導航節點沒有全部 active')

    def navigate_to(self, x, y, timeout):
        """送 navigate_to_pose，回傳最終狀態（GoalStatus）。"""
        self.wait_navigation_active(60)
        self.assertTrue(self.navigate.wait_for_server(timeout_sec=30), 'navigate_to_pose 不存在')
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.node.get_clock().now().to_msg()
        goal.pose.pose.position.x, goal.pose.pose.position.y = x, y
        goal.pose.pose.orientation.w = 1.0
        send = self.navigate.send_goal_async(goal)
        self.assertTrue(self.spin_until(send.done, 10))
        handle = send.result()
        self.assertTrue(handle.accepted, '目標被拒絕')
        result = handle.get_result_async()
        self.assertTrue(self.spin_until(result.done, timeout), f'{timeout} s 內沒有結果')
        return result.result().status

    # ---------- 測試（依名稱順序執行） ----------

    def test_01_map_is_loaded(self):
        self.assertTrue(self.spin_until(lambda: 'map' in self.latest, 30),
                        f'30 s 內沒有收到 /{ROBOT_ID}/map（地圖 {MAP}）')
        self.assertEqual(self.latest['map'].header.frame_id, 'map')
        self.assertAlmostEqual(self.latest['map'].info.resolution, 0.05, places=3)

    def test_02_no_map_frame_before_initial_pose(self):
        # 定位要等使用者給初始位姿（spec：給定之前不發布 map → odom）
        self.assertFalse(self.tf_buffer.can_transform('map', f'{ROBOT_ID}/base_footprint',
                                                      rclpy.time.Time()))

    def test_03_localizes_after_initial_pose(self):
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.pose.pose.position.x, msg.pose.pose.position.y = SPAWN   # 車在出生點，朝 +x
        msg.pose.pose.orientation.w = 1.0
        msg.pose.covariance[0] = msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.0685
        self.initial_pose.publish(msg)

        def localized():
            return self.tf_buffer.can_transform('map', f'{ROBOT_ID}/base_footprint',
                                                rclpy.time.Time())
        self.assertTrue(self.spin_until(localized, 10), '10 s 內沒有 map → base_footprint')
        ex, ey = self.estimate()
        tx, ty, _ = true_pose_in_map()
        self.assertLess(math.hypot(ex - tx, ey - ty), 0.3)

    def test_04_navigates_to_reachable_goal(self):
        self.latest['vmax'] = 0.0
        status = self.navigate_to(*REACHABLE_GOAL, timeout=90)
        self.assertEqual(status, GoalStatus.STATUS_SUCCEEDED)
        tx, ty, _ = true_pose_in_map()
        self.assertLess(math.hypot(REACHABLE_GOAL[0] - tx, REACHABLE_GOAL[1] - ty), 0.3)
        self.assertLessEqual(self.latest['vmax'], 0.5 + 0.05)   # 導航上限 0.5 m/s
        self.assertGreater(self.latest['vmax'], 0.3)            # 確實有開起來

    def test_05_localization_still_correct_after_driving(self):
        ex, ey = self.estimate()
        tx, ty, _ = true_pose_in_map()
        self.assertLess(math.hypot(ex - tx, ey - ty), 0.3)

    def test_06_goal_inside_obstacle_fails(self):
        status = self.navigate_to(*GOAL_IN_OBSTACLE, timeout=120)
        self.assertEqual(status, GoalStatus.STATUS_ABORTED)
        self.assertTrue(self.spin_until(
            lambda: abs(self.latest['odom'].twist.twist.linear.x) < 0.01, 5), '失敗後車沒有停下')

    def test_07_navigation_nodes_are_namespaced(self):
        names = {(ns, n) for n, ns in self.node.get_node_names_and_namespaces()}
        for name in NAV_NODES:
            self.assertIn((f'/{ROBOT_ID}', name), names)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_processes_exit_cleanly(self, proc_info):
        # 被測的程序（車子系統、虛擬驅動節點、建圖／導航）關閉時都要正常結束（SIGINT 而不是被強制 kill）。
        # 模擬器管線例外：測試結束時所有程序同時收到 SIGINT，Gazebo 偶爾卡死被 SIGKILL（等 20 秒也一樣）、
        # ros_gz 的 parameter_bridge 偶爾在收尾時 segfault（-11）；單獨關閉 Gazebo 時 0.2 秒（筆記 20）。
        # 它們是上游模擬工具不是被測系統，只要求最後有結束，並印出警告
        simulator_plumbing = ('ign-', 'parameter_bridge-')
        for info in proc_info:
            if info.process_name.startswith(simulator_plumbing):
                if info.returncode not in (0, -2, 2, 130):
                    print(f'警告：{info.process_name} 以 {info.returncode} 結束（模擬器管線關閉時異常）')
                continue
            self.assertIn(info.returncode, [0, -2, 2, 130],
                          f'{info.process_name} 以 {info.returncode} 結束')
