"""cmd_vel 看門狗節點：轉發速度指令，逾時沒有新指令就送一次停車。

Gazebo Fortress 的 DiffDrive 沒有指令逾時；teleop 或導航程式當掉時，
車子會照最後一筆指令一直走。這個節點夾在中間補上這個安全機制：

    cmd_vel ──▶ [watchdog] ──▶ cmd_vel_gz ──bridge──▶ Gazebo DiffDrive

topic 用相對名稱，由 launch 以 namespace（例如 /amr1）放進各車自己的命名空間。
只負責轉發與逾時；速度截斷交給 DiffDrive 的速度上限。
"""

from geometry_msgs.msg import Twist
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from amr_bringup.watchdog import Watchdog


class CmdVelWatchdog(Node):

    def __init__(self):
        super().__init__('cmd_vel_watchdog')
        timeout = self.declare_parameter('timeout', 0.5).value
        check_rate = self.declare_parameter('check_rate', 20.0).value

        self._watchdog = Watchdog(timeout)
        self._publisher = self.create_publisher(Twist, 'cmd_vel_gz', 10)
        self.create_subscription(Twist, 'cmd_vel', self._on_command, 10)
        # 計時器跟著節點的時鐘走：use_sim_time 為 true 時就是模擬時間（/clock）
        self.create_timer(1.0 / check_rate, self._on_timer)

        self.get_logger().info(f'timeout={timeout}s，檢查頻率 {check_rate} Hz')

    def _now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_command(self, msg):
        self._watchdog.on_command(self._now())
        self._publisher.publish(msg)

    def _on_timer(self):
        if self._watchdog.check(self._now()):
            self._publisher.publish(Twist())     # Twist() 預設全為 0 = 停車
            self.get_logger().info('超過 timeout 沒有收到 cmd_vel，送出停車指令')


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelWatchdog()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
