"""佔據格地圖（nav_msgs/OccupancyGrid 的資料）→ PNG。

顏色與 Nav2 map_saver 存的 trinary .pgm 相同，網頁看到的就和 docker/amr_sim/data/maps/ 裡的圖一樣：
值 ≤ 25（空曠門檻 0.25）→ 白，≥ 65（佔據門檻 0.65）→ 黑，其他（含 −1 未知）→ 灰。
"""

import io

import numpy as np
from PIL import Image

FREE = 254
OCCUPIED = 0
UNKNOWN = 205

FREE_THRESH = 25
OCCUPIED_THRESH = 65


def occupancy_to_png(width, height, data):
    """回傳 PNG bytes（8-bit 灰階）。data 是 OccupancyGrid.data：逐列、第 0 列是地圖 y 最小的一側。"""
    grid = np.asarray(data, dtype=np.int16)
    if grid.size != width * height:
        raise ValueError(f'地圖資料有 {grid.size} 格，和 {width}×{height} 不符')
    grid = grid.reshape(height, width)

    pixels = np.full(grid.shape, UNKNOWN, dtype=np.uint8)
    pixels[(grid >= 0) & (grid <= FREE_THRESH)] = FREE
    pixels[grid >= OCCUPIED_THRESH] = OCCUPIED

    # 圖片的第 0 列在最上面＝地圖 y 最大，所以上下翻轉
    buffer = io.BytesIO()
    Image.fromarray(np.flipud(pixels), mode='L').save(buffer, format='PNG')
    return buffer.getvalue()
