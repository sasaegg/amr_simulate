"""純幾何函式（沒有 ROS 相依，方便測試）。"""

import math


def yaw_from_quaternion(x, y, z, w):
    """只繞 z 軸的四元數 → yaw（弧度，−π～π）。"""
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def quaternion_from_yaw(yaw):
    """yaw → 繞 z 軸的四元數 (x, y, z, w)。"""
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def downsample_path(points, spacing=0.1):
    """每隔約 spacing 公尺保留一點，起點與終點一定保留（減少 WebSocket 的資料量）。"""
    if len(points) <= 1:
        return list(points)
    result = [points[0]]
    for point in points[1:-1]:
        last = result[-1]
        if math.hypot(point[0] - last[0], point[1] - last[1]) >= spacing:
            result.append(point)
    result.append(points[-1])
    return result


def in_map_bounds(info, x, y):
    """(x, y) 是否落在地圖圖片範圍內（含左下邊、不含右上邊）。"""
    max_x = info.origin_x + info.width * info.resolution
    max_y = info.origin_y + info.height * info.resolution
    return info.origin_x <= x < max_x and info.origin_y <= y < max_y
