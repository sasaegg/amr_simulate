"""標地圖原點：改寫 Nav2 地圖檔（.pgm + .yaml），讓選取的位姿成為新地圖的原點與 +x 方向。

純 Python + numpy，不依賴 ROS（服務節點 map_origin_server 只是外殼）。

座標慣例（與 Nav2 map_server 相同）：
- 圖片第 0 列在最上面；`.yaml` 的 origin 是圖片「左下角」在地圖座標的位置 [x, y, yaw]。
- 選取位姿 P=(px, py, θ) 以目前的地圖座標表示；任一點 q 的新座標 q' = R(−θ)(q − P)。

改寫方式（design D1）：
- θ = 0：圖片不變，只改 origin。
- θ 為 90° 倍數：numpy.rot90 旋轉陣列（無損）。
- 其他角度：最近鄰重新取樣，新增區域補未知（只會出現佔據／空曠／未知三種值）；
  再把每個舊的佔據格轉過去標成佔據，避免取樣跳過一格寬的牆而出現缺口。
origin 的角度一律寫 0——Nav2 的 costmap、AMCL 等多數元件忽略它，地圖要靠圖片本身轉正。
"""

import math
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np
import yaml

FREE = 254
OCCUPIED = 0
UNKNOWN = 205

NAME_PATTERN = re.compile(r'[A-Za-z0-9_-]+')
RIGHT_ANGLE_TOLERANCE = 1e-6        # 弧度；在這範圍內視為剛好是 90° 倍數


class MapOriginError(Exception):
    """改寫失敗；原檔不會被改動。"""


# ---------- PGM（P5，8 位元灰階）----------

def read_pgm(path):
    """讀 P5 PGM，回傳 (高, 寬) 的 uint8 陣列；第 0 列是圖片最上面。"""
    data = Path(path).read_bytes()
    tokens, pos = [], 0
    while len(tokens) < 4:                       # 檔頭：P5、寬、高、最大值；# 開頭是註解
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':
            pos = data.index(b'\n', pos) + 1
            continue
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        tokens.append(data[start:pos])
    magic, width, height, maxval = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
    if magic != b'P5' or maxval != 255:
        raise MapOriginError(f'{path}: 只支援 P5、最大值 255 的 PGM（map_saver 存出的格式）')
    pixels = data[pos + 1:pos + 1 + width * height]     # 最大值之後恰好一個空白字元
    if len(pixels) != width * height:
        raise MapOriginError(f'{path}: 圖片資料長度不符')
    return np.frombuffer(pixels, dtype=np.uint8).reshape(height, width).copy()


def write_pgm(path, image):
    image = np.ascontiguousarray(image, dtype=np.uint8)
    height, width = image.shape
    Path(path).write_bytes(f'P5\n{width} {height}\n255\n'.encode() + image.tobytes())


# ---------- 座標轉換 ----------

def _rotate(x, y, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return c * x - s * y, s * x + c * y


def _right_angle_steps(yaw):
    """yaw 是 90° 倍數時回傳逆時針轉了幾個 90°（0–3），否則 None。"""
    steps = yaw / (math.pi / 2)
    nearest = round(steps)
    if abs(steps - nearest) * (math.pi / 2) < RIGHT_ANGLE_TOLERANCE:
        return nearest % 4
    return None


def transform(image, resolution, origin, pose):
    """回傳 (新圖片, 新 origin (x, y))。pose = (px, py, yaw)，以目前地圖座標表示。"""
    px, py, yaw = pose
    height, width = image.shape
    ox, oy = origin

    steps = _right_angle_steps(yaw)
    if steps is not None:                         # 90° 倍數：用精確的 cos／sin，避免浮點誤差
        yaw = steps * math.pi / 2
        c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][steps]
    else:
        c, s = math.cos(yaw), math.sin(yaw)

    def to_new(x, y):                             # q' = R(−θ)(q − P)
        dx, dy = x - px, y - py
        return c * dx + s * dy, -s * dx + c * dy

    corners = [to_new(ox + i * width * resolution, oy + j * height * resolution)
               for i in (0, 1) for j in (0, 1)]
    min_x, min_y = min(p[0] for p in corners), min(p[1] for p in corners)

    if steps is not None:
        # 新座標系轉了 +θ，地圖內容相對轉了 −θ：順時針 steps 個 90°（圖片陣列與俯視圖方向一致）
        return np.rot90(image, k=-steps).copy(), (min_x, min_y)

    max_x, max_y = max(p[0] for p in corners), max(p[1] for p in corners)
    new_w = int(math.ceil((max_x - min_x) / resolution - 1e-9))
    new_h = int(math.ceil((max_y - min_y) / resolution - 1e-9))
    # 新圖片每一格的中心（新座標）→ 舊座標 q = P + R(θ) q' → 舊圖片的格子（最近鄰）
    cols, rows = np.meshgrid(np.arange(new_w), np.arange(new_h))
    xn = min_x + (cols + 0.5) * resolution
    yn = min_y + (new_h - 1 - rows + 0.5) * resolution
    xo = px + c * xn - s * yn
    yo = py + s * xn + c * yn
    old_c = np.floor((xo - ox) / resolution).astype(int)
    old_r = height - 1 - np.floor((yo - oy) / resolution).astype(int)
    inside = (old_c >= 0) & (old_c < width) & (old_r >= 0) & (old_r < height)
    result = np.full((new_h, new_w), UNKNOWN, dtype=np.uint8)
    result[inside] = image[old_r[inside], old_c[inside]]

    # 最近鄰取樣可能跳過某些舊格子：一格寬的牆會出現缺口。導航上「牆有缺口」比「牆多一格」危險，
    # 所以再把每個舊的佔據格中心轉到新座標、標成佔據——障礙物一格都不漏
    occ_r, occ_c = np.nonzero(image == OCCUPIED)
    xq = ox + (occ_c + 0.5) * resolution - px
    yq = oy + (height - 1 - occ_r + 0.5) * resolution - py
    new_c = np.floor((c * xq + s * yq - min_x) / resolution).astype(int)
    new_r = new_h - 1 - np.floor((-s * xq + c * yq - min_y) / resolution).astype(int)
    keep = (new_c >= 0) & (new_c < new_w) & (new_r >= 0) & (new_r < new_h)
    result[new_r[keep], new_c[keep]] = OCCUPIED
    return result, (min_x, min_y)


# ---------- 改寫地圖檔 ----------

def _atomic_write(directory, target, write):
    """先寫到同資料夾的暫存檔，回傳暫存檔路徑（之後由呼叫端 os.replace）。"""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f'.{target.name}.', suffix='.tmp')
    os.close(fd)
    try:
        write(Path(tmp))
        os.chmod(tmp, 0o644)                      # mkstemp 建的檔案是 600，改成一般檔案的 644
    except BaseException:
        os.unlink(tmp)
        raise
    return Path(tmp)


def set_map_origin(maps_dir, name, x, y, yaw):
    """把地圖 <maps_dir>/<name> 的原點改到 (x, y, yaw)。失敗時丟 MapOriginError，原檔不變。

    回傳 (新 origin x, 新 origin y, 圖片寬, 圖片高)。
    """
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise MapOriginError(f'地圖名稱只能包含英數字、底線、連字號，收到 {name!r}')
    maps_dir = Path(maps_dir)
    yaml_path = maps_dir / f'{name}.yaml'
    if not yaml_path.is_file():
        raise MapOriginError(f'找不到地圖：{yaml_path}')
    try:
        meta = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
        image_path = maps_dir / meta['image']
        resolution = float(meta['resolution'])
        origin = (float(meta['origin'][0]), float(meta['origin'][1]))
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError, IndexError) as e:
        raise MapOriginError(f'{yaml_path}: 讀不了地圖描述檔（{e}）') from None
    if not image_path.is_file():
        raise MapOriginError(f'找不到地圖圖片：{image_path}')
    image = read_pgm(image_path)

    new_image, (nx, ny) = transform(image, resolution, origin, (x, y, yaw))
    new_meta = dict(meta)
    new_meta['origin'] = [round(nx, 6), round(ny, 6), 0]

    temps = []
    try:
        # 1. 新內容寫到暫存檔（資料夾不可寫時在這裡就失敗，什麼都沒動）
        temps.append((_atomic_write(maps_dir, image_path, lambda p: write_pgm(p, new_image)), image_path))
        temps.append((_atomic_write(
            maps_dir, yaml_path,
            lambda p: p.write_text(yaml.safe_dump(new_meta, sort_keys=False, default_flow_style=None,
                                                  allow_unicode=True), encoding='utf-8')), yaml_path))
        # 2. 備份目前版本（只保留最近一次）
        for src in (image_path, yaml_path):
            backup = src.with_name(f'{name}.bak{src.suffix}')
            tmp = _atomic_write(maps_dir, backup, lambda p, s=src: shutil.copyfile(s, p))
            os.replace(tmp, backup)
        # 3. 換上新內容
        for tmp, target in temps:
            os.replace(tmp, target)
        temps = []
    except OSError as e:
        raise MapOriginError(f'寫入 {maps_dir} 失敗：{e}') from None
    finally:
        for tmp, _ in temps:
            if tmp.exists():
                tmp.unlink()
    return nx, ny, new_image.shape[1], new_image.shape[0]
