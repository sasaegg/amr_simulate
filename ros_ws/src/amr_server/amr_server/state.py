"""後端內部與 API 共用的資料型別（不依賴 ROS，API 與測試都能直接用）。"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# 導航狀態：idle（還沒派過車）、navigating、succeeded、failed、canceled
IDLE = 'idle'
NAVIGATING = 'navigating'
SUCCEEDED = 'succeeded'
FAILED = 'failed'
CANCELED = 'canceled'


@dataclass(frozen=True)
class Pose2D:
    """地圖座標系 map 中的位置（公尺）與朝向（弧度）。"""

    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class MapInfo:
    """地圖的大小與位置：格子 (0, 0) 的左下角在 (origin_x, origin_y)。version 每收到一次新地圖加 1。"""

    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float
    version: int


@dataclass
class RobotState:
    """一台車在某個時刻的狀態快照（WebSocket 推送的內容）。"""

    pose: Optional[Pose2D] = None
    goal: Optional[Pose2D] = None
    status: str = IDLE
    message: str = ''
    distance_remaining: Optional[float] = None
    plan: List[Tuple[float, float]] = field(default_factory=list)
    map_version: int = 0
    map_ready: bool = False
    nav_ready: bool = False
