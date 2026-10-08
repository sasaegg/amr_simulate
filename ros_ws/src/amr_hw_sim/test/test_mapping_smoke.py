"""建圖冒煙測試：headless 世界 + 車子系統（hardware=sim）+ 另外啟動 mapping.launch.xml。

驗證 spec mapping：地圖發布、map 座標系、行駛後地圖擴大、存圖。
方法依名稱排序執行。沒有 ROS 環境時整個檔案略過。
"""

from pathlib import Path
import subprocess
import tempfile
import time
import unittest

import pytest

launch_testing = pytest.importorskip('launch_testing')

from ament_index_python.packages import get_package_share_directory  # noqa: E402
from geometry_msgs.msg import Twist  # noqa: E402
from launch import LaunchDescription  # noqa: E402
from launch.actions import IncludeLaunchDescription, SetLaunchConfiguration, TimerAction  # noqa: E402
from launch.launch_description_sources import AnyLaunchDescriptionSource  # noqa: E402
import launch_testing.actions  # noqa: E402
from nav_msgs.msg import OccupancyGrid  # noqa: E402
import rclpy  # noqa: E402
from rclpy.qos import DurabilityPolicy, QoSProfile  # noqa: E402
import rclpy.time  # noqa: E402
from tf2_ros import Buffer, TransformListener  # noqa: E402
import yaml  # noqa: E402

ROBOT_ID = 'amr1'
WORLD = 'warehouse_small'
OCCUPIED = 100
UNKNOWN = -1


def include(package, launch_file, **arguments):
    path = Path(get_package_share_directory(package)) / 'launch' / launch_file
    return IncludeLaunchDescription(AnyLaunchDescriptionSource(str(path)),
                                    launch_arguments=arguments.items())


@pytest.mark.launch_test
def generate_test_description():
    return LaunchDescription([
        # 測試結束時所有程序同時收到 SIGINT，Gazebo 偶爾要超過預設的 5 秒才結束（3 次有 2 次被 SIGKILL）；
        # 單獨關閉時 0.2 秒。放寬升級到 SIGTERM／SIGKILL 前的等待時間，關閉檢查才反映真正的問題
        SetLaunchConfiguration('sigterm_timeout', '20'),
        include('amr_worlds', 'world.launch.xml', world=WORLD, headless='true'),
        TimerAction(period=3.0, actions=[
            include('amr_bringup', 'robot.launch.xml',
                    hardware='sim', robot_id=ROBOT_ID, x='1.0', y='1.0', yaw='0.0'),
        ]),
        # 驅動起來後才開始建圖（和使用者「車子系統執行中另外啟動建圖」的流程相同）
        TimerAction(period=8.0, actions=[
            include('amr_navigation', 'mapping.launch.xml',
                    robot_id=ROBOT_ID, use_sim_time='true'),
        ]),
        launch_testing.actions.ReadyToTest(),
    ])


class TestMappingSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('mapping_smoke_test')
        cls.latest = {}
        # 地圖用 Transient Local：訂閱前就發過的最後一筆也收得到
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        cls.node.create_subscription(OccupancyGrid, f'/{ROBOT_ID}/map',
                                     lambda m: cls.latest.__setitem__('map', m), qos)
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

    def drive(self, linear_x, angular_z, seconds):
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.cmd.publish(msg)
            self.spin_for(0.1)

    def counts(self):
        data = self.latest['map'].data
        known = sum(1 for c in data if c != UNKNOWN)
        occupied = sum(1 for c in data if c == OCCUPIED)
        return known, occupied

    # ---------- 測試（依名稱順序執行） ----------

    def test_01_map_arrives_within_30s_with_walls(self):
        ok = self.spin_until(lambda: 'map' in self.latest and self.counts()[1] > 0, timeout=30)
        self.assertTrue(ok, '30 s 內沒有收到含佔據格的 /amr1/map')
        info = self.latest['map'].info
        self.assertAlmostEqual(info.resolution, 0.05, places=3)
        self.assertEqual(self.latest['map'].header.frame_id, 'map')

    def test_02_vehicle_pose_in_map_frame(self):
        def available():
            return self.tf_buffer.can_transform('map', f'{ROBOT_ID}/base_footprint',
                                                rclpy.time.Time())
        self.assertTrue(self.spin_until(available, timeout=10))
        # map 座標系的原點是開始建圖時的車輛位置，車還沒動，所以在原點附近（design D4）
        t = self.tf_buffer.lookup_transform('map', f'{ROBOT_ID}/base_footprint',
                                            rclpy.time.Time()).transform.translation
        self.assertLess(abs(t.x) + abs(t.y), 0.2)

    def test_03_only_slam_toolbox_adds_tf(self):
        # /tf 的發布者：驅動（odom）、robot_state_publisher（車身）、slam_toolbox（map → odom）
        publishers = {(i.node_namespace, i.node_name)
                      for i in self.node.get_publishers_info_by_topic('/tf')}
        self.assertEqual(publishers, {(f'/{ROBOT_ID}', 'base_bridge'),
                                      (f'/{ROBOT_ID}', 'robot_state_publisher'),
                                      (f'/{ROBOT_ID}', 'slam_toolbox')})

    def test_04_map_grows_after_driving(self):
        known_before, _ = self.counts()
        self.drive(0.4, 0.0, 5.0)     # 往 +x 約 2 m
        self.drive(0.0, 0.8, 4.0)     # 原地左轉
        self.drive(0.4, 0.0, 4.0)
        stamp = self.latest['map'].header.stamp
        # map_update_interval 2 s：等下一張新地圖
        self.assertTrue(self.spin_until(lambda: self.latest['map'].header.stamp != stamp, 10))
        known_after, _ = self.counts()
        self.assertGreater(known_after, known_before * 1.5,
                           f'已知格 {known_before} → {known_after}')

    def test_05_save_map(self):
        prefix = Path(tempfile.mkdtemp()) / 'smoke_map'
        result = subprocess.run(
            ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', str(prefix),
             '--ros-args', '-r', f'map:=/{ROBOT_ID}/map', '-p', 'use_sim_time:=true'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        pgm = prefix.with_suffix('.pgm')
        meta = yaml.safe_load(prefix.with_suffix('.yaml').read_text())
        self.assertGreater(pgm.stat().st_size, 1000)
        self.assertEqual(meta['image'], 'smoke_map.pgm')
        self.assertAlmostEqual(meta['resolution'], 0.05, places=3)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_processes_exit_cleanly(self, proc_info):
        launch_testing.asserts.assertExitCodes(
            proc_info, allowable_exit_codes=[0, -2, 2, 130])
