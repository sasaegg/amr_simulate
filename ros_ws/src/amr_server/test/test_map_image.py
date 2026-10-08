"""佔據格 → PNG：顏色與存圖的 .pgm 相同（白＝空曠、黑＝障礙、灰＝未知），圖片上方＝地圖 y 最大。"""

import io

from PIL import Image
import pytest

from amr_server.map_image import FREE, OCCUPIED, UNKNOWN, occupancy_to_png


def decode(png):
    image = Image.open(io.BytesIO(png))
    assert image.format == 'PNG'
    return image


def test_colors_match_map_saver():
    assert (FREE, OCCUPIED, UNKNOWN) == (254, 0, 205)


@pytest.mark.parametrize('value, expected', [
    (-1, UNKNOWN),
    (0, FREE),
    (25, FREE),        # 空曠門檻 0.25（含）
    (26, UNKNOWN),     # 兩個門檻之間 → 未知（trinary）
    (64, UNKNOWN),
    (65, OCCUPIED),    # 佔據門檻 0.65（含）
    (100, OCCUPIED),
])
def test_thresholds(value, expected):
    image = decode(occupancy_to_png(1, 1, [value]))
    assert image.getpixel((0, 0)) == expected


def test_rows_are_flipped():
    # OccupancyGrid 的第 0 列是 y 最小（地圖下方）；圖片的第 0 列是上方
    width, height = 3, 2
    data = [100, 0, 0,     # y 小（下）
            -1, -1, -1]    # y 大（上）
    image = decode(occupancy_to_png(width, height, data))
    assert image.size == (3, 2)
    assert image.mode == 'L'
    assert [image.getpixel((x, 0)) for x in range(3)] == [UNKNOWN] * 3
    assert [image.getpixel((x, 1)) for x in range(3)] == [OCCUPIED, FREE, FREE]


def test_size_mismatch_is_rejected():
    with pytest.raises(ValueError):
        occupancy_to_png(2, 2, [0, 0, 0])
