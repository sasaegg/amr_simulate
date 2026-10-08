"""用 rclpy 實作 RobotBridge：每台車一個，全部掛在同一個節點 FleetNode 上。

只用車子系統的標準介面：
  /<id>/map                 nav_msgs/OccupancyGrid（Transient Local，map_server 發布）
  /<id>/plan                nav_msgs/Path（Nav2 規劃的路徑）
  TF map → <id>/base_footprint
  /<id>/navigate_to_pose    nav2_msgs/action/NavigateToPose
  /<id>/initialpose         geometry_msgs/PoseWithCovarianceStamped（AMCL 訂閱）

執行緒：ROS 回呼都在 executor 的單一執行緒；API 在其他執行緒呼叫這裡的方法。
共享的狀態以 lock 保護；送目標與取消交給 executor 執行緒做（executor.create_task）——
Humble 的 ActionClient 從其他執行緒 send_goal_async 時，回覆可能在 future 登記前就被處理掉。
"""

import threading

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Path
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

from amr_server.bridge import NavigationUnavailable, NoActiveGoal
from amr_server.geometry import downsample_path, quaternion_from_yaw, yaw_from_quaternion
from amr_server.map_image import occupancy_to_png
from amr_server.state import (
    CANCELED, FAILED, IDLE, NAVIGATING, SUCCEEDED, MapInfo, Pose2D, RobotState)

# RViz 2D Pose Estimate 送出的共變異數：x、y 各 0.5 m 標準差，yaw 約 15°
INITIAL_POSE_COVARIANCE = {0: 0.25, 7: 0.25, 35: 0.06853891945200942}


class RosRobotBridge:
    def __init__(self, node, robot_id, tf_buffer, pose_timeout=2.0, server_wait=0.5):
        self._node = node
        self._id = robot_id
        self._tf = tf_buffer
        self._pose_timeout = Duration(seconds=pose_timeout)
        self._server_wait = server_wait
        self._lock = threading.Lock()

        self._status = IDLE
        self._message = ''
        self._goal = None
        self._distance = None
        self._plan = []
        self._map_info = None
        self._map_png = None
        self._map_version = 0
        self._goal_seq = 0               # 每送一個目標加 1；回呼時比對，被取代的舊目標不得改寫狀態
        self._goal_handle = None
        self._cancel_requested = False

        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        node.create_subscription(OccupancyGrid, f'/{robot_id}/map', self._on_map, latched)
        node.create_subscription(Path, f'/{robot_id}/plan', self._on_plan, 10)
        self._action = ActionClient(node, NavigateToPose, f'/{robot_id}/navigate_to_pose')
        self._initial_pose_pub = node.create_publisher(
            PoseWithCovarianceStamped, f'/{robot_id}/initialpose', 10)

    # ---- 給 API 的介面（任何執行緒） ----

    def state(self):
        pose = self._lookup_pose()
        with self._lock:
            return RobotState(
                pose=pose, goal=self._goal, status=self._status, message=self._message,
                distance_remaining=self._distance, plan=list(self._plan),
                map_version=self._map_version, map_ready=self._map_info is not None,
                nav_ready=self._action.server_is_ready())

    def map_info(self):
        with self._lock:
            return self._map_info

    def map_png(self):
        with self._lock:
            return self._map_png

    def send_goal(self, x, y, yaw):
        if not self._action.wait_for_server(timeout_sec=self._server_wait):
            raise NavigationUnavailable(
                f'{self._id} 的導航沒有在執行（找不到 /{self._id}/navigate_to_pose）')
        with self._lock:
            self._goal_seq += 1
            seq = self._goal_seq
            self._status = NAVIGATING
            self._message = ''
            self._goal = Pose2D(x, y, yaw)
            self._distance = None
            self._plan = []
            self._goal_handle = None
            self._cancel_requested = False
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self._node.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        q = quaternion_from_yaw(yaw)
        (goal.pose.pose.orientation.x, goal.pose.pose.orientation.y,
         goal.pose.pose.orientation.z, goal.pose.pose.orientation.w) = q
        self._node.executor.create_task(self._send, seq, goal)

    def cancel(self):
        with self._lock:
            if self._status != NAVIGATING:
                raise NoActiveGoal(f'{self._id} 沒有進行中的目標')
            seq = self._goal_seq
        self._node.executor.create_task(self._cancel, seq)

    def set_initial_pose(self, x, y, yaw):
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)
        q = quaternion_from_yaw(yaw)
        (msg.pose.pose.orientation.x, msg.pose.pose.orientation.y,
         msg.pose.pose.orientation.z, msg.pose.pose.orientation.w) = q
        for index, value in INITIAL_POSE_COVARIANCE.items():
            msg.pose.covariance[index] = value
        self._initial_pose_pub.publish(msg)

    # ---- 位置 ----

    def _lookup_pose(self):
        try:
            t = self._tf.lookup_transform('map', f'{self._id}/base_footprint', Time())
        except TransformException:
            return None              # 還沒定位（沒有 map → odom）或車子系統沒在跑
        # 最新一筆太舊＝車子系統停了；TF 的時間和節點時鐘一致（模擬時都是 /clock）
        if self._node.get_clock().now() - Time.from_msg(t.header.stamp) > self._pose_timeout:
            return None
        r = t.transform.rotation
        return Pose2D(t.transform.translation.x, t.transform.translation.y,
                      yaw_from_quaternion(r.x, r.y, r.z, r.w))

    # ---- 訂閱回呼（executor 執行緒） ----

    def _on_map(self, msg):
        png = occupancy_to_png(msg.info.width, msg.info.height, msg.data)   # 在鎖外轉，不擋住 API
        # resolution 在訊息裡是 float32（0.05 會變成 0.05000000074…），四捨五入回原本寫在 yaml 的值
        resolution = round(float(msg.info.resolution), 6)
        with self._lock:
            self._map_version += 1
            self._map_info = MapInfo(
                width=msg.info.width, height=msg.info.height, resolution=resolution,
                origin_x=msg.info.origin.position.x, origin_y=msg.info.origin.position.y,
                version=self._map_version)
            self._map_png = png

    def _on_plan(self, msg):
        points = downsample_path([(p.pose.position.x, p.pose.position.y) for p in msg.poses])
        with self._lock:
            if self._status == NAVIGATING:
                self._plan = points

    # ---- 目標的生命週期（executor 執行緒） ----

    def _send(self, seq, goal):
        future = self._action.send_goal_async(
            goal, feedback_callback=lambda feedback: self._on_feedback(seq, feedback))
        future.add_done_callback(lambda f: self._on_goal_response(seq, f))

    def _cancel(self, seq):
        with self._lock:
            if seq != self._goal_seq:
                return
            handle = self._goal_handle
            if handle is None:
                self._cancel_requested = True      # 還在等 Nav2 接受：接受後立刻取消
                return
        handle.cancel_goal_async()

    def _on_feedback(self, seq, feedback):
        with self._lock:
            if seq == self._goal_seq and self._status == NAVIGATING:
                self._distance = feedback.feedback.distance_remaining

    def _on_goal_response(self, seq, future):
        handle = future.result()
        with self._lock:
            if seq != self._goal_seq:
                return                             # 已被新目標取代（Nav2 會自己結束舊目標）
            if not handle.accepted:
                self._finish(FAILED, 'Nav2 拒絕目標')
                return
            self._goal_handle = handle
            cancel_now = self._cancel_requested
        if cancel_now:
            handle.cancel_goal_async()
        handle.get_result_async().add_done_callback(lambda f: self._on_result(seq, f))

    def _on_result(self, seq, future):
        status = future.result().status
        with self._lock:
            if seq != self._goal_seq:
                return                             # 舊目標的結果晚到，不改寫目前的狀態
            if status == GoalStatus.STATUS_SUCCEEDED:
                self._finish(SUCCEEDED, '')
            elif status == GoalStatus.STATUS_CANCELED:
                self._finish(CANCELED, '')
            elif status == GoalStatus.STATUS_ABORTED:
                # Humble 的 NavigateToPose 結果沒有錯誤碼，只知道 Nav2 放棄了
                self._finish(FAILED, 'Nav2 放棄（到不了或卡住）')
            else:
                self._finish(FAILED, f'未預期的導航結果（狀態 {status}）')

    def _finish(self, status, message):
        # 呼叫時必須已持有 self._lock
        self._status = status
        self._message = message
        self._plan = []
        self._goal_handle = None
        if status == SUCCEEDED:
            self._distance = 0.0


class FleetNode(Node):
    """中控的 ROS 節點：一個 TF buffer 給所有車共用，每台車一個 RosRobotBridge。"""

    def __init__(self, robots, pose_timeout=2.0):
        super().__init__('amr_server')
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.bridges = {robot_id: RosRobotBridge(self, robot_id, self.tf_buffer, pose_timeout)
                        for robot_id in robots}
