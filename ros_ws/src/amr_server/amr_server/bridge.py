"""API 與車輛之間的介面。

api.py 只認識這個介面：正式執行時是 ros_bridge.RosRobotBridge（用 rclpy 和車子系統溝通），
測試時換成假的實作，API 的測試就完全不需要 ROS。
"""

from typing import Optional, Protocol

from amr_server.state import MapInfo, RobotState


class NavigationUnavailable(Exception):
    """這台車的導航沒有在執行（找不到 navigate_to_pose action）。"""


class NoActiveGoal(Exception):
    """要取消時沒有進行中的目標。"""


class RobotBridge(Protocol):
    def state(self) -> RobotState:
        """目前狀態的複本（可以在任何執行緒呼叫）。"""

    def map_info(self) -> Optional[MapInfo]:
        """地圖資訊；還沒收到地圖時是 None。"""

    def map_png(self) -> Optional[bytes]:
        """地圖圖片（PNG）；還沒收到地圖時是 None。"""

    def send_goal(self, x: float, y: float, yaw: float) -> None:
        """派車；導航沒在執行時丟出 NavigationUnavailable。會等待最多 0.5 秒。"""

    def cancel(self) -> None:
        """取消進行中的目標；沒有時丟出 NoActiveGoal。"""

    def set_initial_pose(self, x: float, y: float, yaw: float) -> None:
        """發布初始位姿（同 RViz 的 2D Pose Estimate）。"""
