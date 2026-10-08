"""冒煙測試：headless 啟動世界與車子系統（hardware: sim），驗證整條資料路徑。

用 launch_testing：generate_test_description() 啟動被測系統，下面的 unittest 類別在系統執行時檢查。
方法依名稱排序執行：光達幾何要在車子移動之前、暫停 /clock 放最後。
沒有 ROS 環境（例如 env -i 跑純邏輯測試）時整個檔案略過。
"""

import math
from pathlib import Path
import subprocess
import time
import unittest

import pytest

launch_testing = pytest.importorskip('launch_testing')

from ament_index_python.packages import get_package_share_directory  # noqa: E402
from geometry_msgs.msg import Twist  # noqa: E402
from launch import LaunchDescription  # noqa: E402
from launch.actions import IncludeLaunchDescription, TimerAction  # noqa: E402
from launch.launch_description_sources import AnyLaunchDescriptionSource  # noqa: E402
import launch_testing.actions  # noqa: E402
from nav_msgs.msg import Odometry  # noqa: E402
import rclpy  # noqa: E402
from rosgraph_msgs.msg import Clock  # noqa: E402
from sensor_msgs.msg import LaserScan  # noqa: E402
from tf2_ros import Buffer, TransformListener  # noqa: E402

ROBOT_ID = 'amr1'
SPAWN = (1.0, 1.0, 0.0)
LASER_X = 0.15          # laser_link 在 base_link 前方 0.15 m（amr_description）
WORLD = 'warehouse_small'


def include(package, launch_file, **arguments):
    path = Path(get_package_share_directory(package)) / 'launch' / launch_file
    return IncludeLaunchDescription(AnyLaunchDescriptionSource(str(path)),
                                    launch_arguments=arguments.items())


@pytest.mark.launch_test
def generate_test_description():
    x, y, yaw = (str(v) for v in SPAWN)
    return LaunchDescription([
        include('amr_worlds', 'world.launch.xml', world=WORLD, headless='true'),
        # 世界先起來再啟動車子系統（spawn 也會自己等世界，這裡只是讓啟動順序接近實際操作）
        TimerAction(period=3.0, actions=[
            include('amr_bringup', 'robot.launch.xml',
                    hardware='sim', robot_id=ROBOT_ID, x=x, y=y, yaw=yaw),
        ]),
        launch_testing.actions.ReadyToTest(),
    ])


class TestSimSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('sim_smoke_test')
        cls.latest = {}
        cls.node.create_subscription(LaserScan, f'/{ROBOT_ID}/scan',
                                     lambda m: cls.latest.__setitem__('scan', m), 10)
        cls.node.create_subscription(Odometry, f'/{ROBOT_ID}/odom',
                                     lambda m: cls.latest.__setitem__('odom', m), 10)
        cls.node.create_subscription(Clock, '/clock',
                                     lambda m: cls.latest.__setitem__('clock', m), 10)
        cls.cmd = cls.node.create_publisher(Twist, f'/{ROBOT_ID}/cmd_vel', 10)
        cls.tf_buffer = Buffer()
        cls.tf_listener = TransformListener(cls.tf_buffer, cls.node)

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    # ---------- 小工具 ----------

    def spin_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self.node, timeout_sec=0.02)

    def spin_until(self, condition, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rclpy.spin_once(self.node, timeout_sec=0.05)
            if condition():
                return True
        return False

    def drive(self, linear_x, seconds):
        msg = Twist()
        msg.linear.x = linear_x
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.cmd.publish(msg)
            self.spin_for(0.1)

    def odom_speed(self):
        return self.latest['odom'].twist.twist.linear.x

    def odom_xy(self):
        p = self.latest['odom'].pose.pose.position
        return p.x, p.y

    def range_at(self, degrees):
        scan = self.latest['scan']
        index = round((math.radians(degrees) - scan.angle_min) / scan.angle_increment)
        return scan.ranges[index % len(scan.ranges)]

    # ---------- 測試（依名稱順序執行） ----------

    def test_01_scan_and_odom_arrive_within_30s(self):
        ok = self.spin_until(lambda: 'scan' in self.latest and 'odom' in self.latest, timeout=30)
        self.assertTrue(ok, f'30 s 內收到的資料：{sorted(self.latest)}')
        self.assertEqual(self.latest['scan'].header.frame_id, f'{ROBOT_ID}/laser_link')
        self.assertEqual(self.latest['odom'].header.frame_id, f'{ROBOT_ID}/odom')
        self.assertEqual(self.latest['odom'].child_frame_id, f'{ROBOT_ID}/base_footprint')

    def test_02_lidar_matches_scene_geometry(self):
        # 出生點 (1, 1) 朝 +x：光達在 x = 1.15；後方是 x = 0 的外牆內側面、右方是 y = 0 的外牆內側面
        self.spin_for(1.0)
        self.assertAlmostEqual(self.range_at(180), SPAWN[0] + LASER_X, delta=0.1)
        self.assertAlmostEqual(self.range_at(-90), SPAWN[1], delta=0.1)

    def test_03_vehicle_topics_are_namespaced(self):
        topics = {name for name, _ in self.node.get_topic_names_and_types()}
        for name in ('cmd_vel', 'odom', 'scan', 'imu', 'joint_states'):
            self.assertIn(f'/{ROBOT_ID}/{name}', topics)
            self.assertNotIn(f'/{name}', topics)

    def test_04_clock_has_exactly_one_publisher(self):
        self.assertEqual(self.node.count_publishers('/clock'), 1)

    def test_05_tf_from_odom_to_laser(self):
        def available():
            return self.tf_buffer.can_transform(
                f'{ROBOT_ID}/odom', f'{ROBOT_ID}/laser_link', rclpy.time.Time())
        self.assertTrue(self.spin_until(available, timeout=10))
        t = self.tf_buffer.lookup_transform(
            f'{ROBOT_ID}/odom', f'{ROBOT_ID}/laser_link', rclpy.time.Time()).transform.translation
        self.assertAlmostEqual(t.z, 0.255, delta=0.01)

    def test_06_cmd_vel_moves_the_vehicle(self):
        x0, y0 = self.odom_xy()
        self.drive(0.5, 2.0)
        x1, y1 = self.odom_xy()
        self.assertGreater(math.hypot(x1 - x0, y1 - y0), 0.3)

    def test_07_speed_is_clamped(self):
        self.drive(5.0, 2.0)
        self.assertLessEqual(self.odom_speed(), 1.0 + 0.05)
        self.assertGreater(self.odom_speed(), 0.9)

    def test_08_stops_within_1s_after_commands_stop(self):
        self.drive(1.0, 1.0)
        start = time.monotonic()
        stopped = self.spin_until(lambda: abs(self.odom_speed()) < 0.01, timeout=3)
        elapsed = time.monotonic() - start
        self.assertTrue(stopped, '3 s 內沒有停下')
        self.assertLess(elapsed, 1.0, f'停車花了 {elapsed:.2f} s')

    def test_09_pausing_simulation_stops_clock(self):
        def control(pause):
            subprocess.run(['ign', 'service', '-s', f'/world/{WORLD}/control',
                            '--reqtype', 'ignition.msgs.WorldControl',
                            '--reptype', 'ignition.msgs.Boolean', '--timeout', '3000',
                            '--req', f'pause: {str(pause).lower()}'],
                           check=True, capture_output=True)
        try:
            control(True)
            self.spin_for(1.0)
            before = self.latest['clock'].clock
            self.spin_for(1.5)
            after = self.latest['clock'].clock
            self.assertEqual((before.sec, before.nanosec), (after.sec, after.nanosec))
        finally:
            control(False)
        self.spin_for(1.0)
        resumed = self.latest['clock'].clock
        self.assertNotEqual((resumed.sec, resumed.nanosec), (after.sec, after.nanosec))

    def test_10_odom_heading_matches_ground_truth(self):
        # 原地旋轉時 odom 的角度變化要和 Gazebo 真實值一致。輪子碰撞形狀若用圓柱，
        # 接觸點落在輪緣、有效輪距變小，實際多轉約 10%，SLAM 地圖會扭曲（筆記 17）
        def true_yaw():
            out = subprocess.run(['ign', 'model', '-m', ROBOT_ID, '-p'],
                                 capture_output=True, text=True, check=True).stdout
            return float(out.strip().splitlines()[-1].strip(' []').split()[2])

        def odom_yaw():
            q = self.latest['odom'].pose.pose.orientation
            return 2 * math.atan2(q.z, q.w)

        def wrap(a):
            return math.atan2(math.sin(a), math.cos(a))

        self.spin_for(1.0)
        truth0, odom0 = true_yaw(), odom_yaw()
        msg = Twist()
        msg.angular.z = 0.6
        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            self.cmd.publish(msg)
            self.spin_for(0.1)
        self.cmd.publish(Twist())
        self.spin_for(1.5)
        turned_truth = wrap(true_yaw() - truth0)
        turned_odom = wrap(odom_yaw() - odom0)
        self.assertGreater(abs(turned_truth), 1.0)
        self.assertAlmostEqual(turned_odom, turned_truth, delta=math.radians(2))


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_processes_exit_cleanly(self, proc_info):
        # 被測的程序在關閉時都要正常結束（SIGINT 而不是被強制 kill）
        launch_testing.asserts.assertExitCodes(
            proc_info, allowable_exit_codes=[0, -2, 2, 130])
