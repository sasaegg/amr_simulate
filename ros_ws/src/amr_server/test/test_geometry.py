"""純幾何函式：四元數 ↔ yaw、路徑降取樣、點是否在地圖範圍內。"""

import math

import pytest

from amr_server.geometry import downsample_path, in_map_bounds, quaternion_from_yaw, yaw_from_quaternion
from amr_server.state import MapInfo


@pytest.mark.parametrize('yaw', [0.0, 0.5, math.pi / 2, -2.0, math.pi - 1e-6])
def test_yaw_round_trip(yaw):
    assert yaw_from_quaternion(*quaternion_from_yaw(yaw)) == pytest.approx(yaw)


def test_quaternion_is_about_z():
    x, y, z, w = quaternion_from_yaw(math.pi / 2)
    assert (x, y) == (0.0, 0.0)
    assert (z, w) == pytest.approx((math.sqrt(0.5), math.sqrt(0.5)))


def test_downsample_keeps_spacing_first_and_last():
    points = [(i * 0.01, 0.0) for i in range(101)]     # 0～1 m，每 1 cm 一點
    result = downsample_path(points, spacing=0.1)
    assert result[0] == (0.0, 0.0)
    assert result[-1] == (1.0, 0.0)
    gaps = [b[0] - a[0] for a, b in zip(result, result[1:])]
    assert all(g >= 0.1 - 1e-9 for g in gaps[:-1])
    assert len(result) == 11


def test_downsample_short_paths():
    assert downsample_path([]) == []
    assert downsample_path([(1.0, 2.0)]) == [(1.0, 2.0)]
    # 終點離前一個保留點不到間隔也要保留
    assert downsample_path([(0.0, 0.0), (0.02, 0.0)], spacing=0.1) == [(0.0, 0.0), (0.02, 0.0)]


def test_in_map_bounds():
    info = MapInfo(width=200, height=100, resolution=0.05, origin_x=-1.0, origin_y=-0.5, version=1)
    # 範圍 x ∈ [−1, 9)、y ∈ [−0.5, 4.5)
    assert in_map_bounds(info, -1.0, -0.5)
    assert in_map_bounds(info, 8.99, 4.49)
    assert not in_map_bounds(info, 9.0, 0.0)
    assert not in_map_bounds(info, 0.0, -0.51)
    assert not in_map_bounds(info, 999.0, 1.0)
