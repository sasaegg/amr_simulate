"""標地圖原點的核心（amr_navigation/map_origin.py）：純 Python + numpy，不需要 ROS。

座標慣例：圖片第 0 列在最上面；`.yaml` 的 origin 是圖片「左下角」在地圖座標的位置。
選取位姿 P=(px, py, θ) 後，任一點 q 的新座標是 q' = R(−θ)(q − P)。
"""

import math
import os
from pathlib import Path

import numpy as np
import pytest
import yaml

from amr_navigation.map_origin import (
    FREE, MapOriginError, OCCUPIED, read_pgm, set_map_origin, UNKNOWN, write_pgm)

RES = 0.1
ORIGIN = (-1.0, -0.5)


def make_map(directory, name='m', width=20, height=10, origin=ORIGIN):
    """空曠的地圖，(0.5, 0.0) 那一格是牆。回傳圖片陣列。"""
    image = np.full((height, width), FREE, dtype=np.uint8)
    r, c = pixel_of(0.5, 0.0, height, origin)
    image[r, c] = OCCUPIED
    image[0, :3] = UNKNOWN                      # 左上角一小段未知
    write_pgm(Path(directory) / f'{name}.pgm', image)
    meta = {'image': f'{name}.pgm', 'mode': 'trinary', 'resolution': RES,
            'origin': [origin[0], origin[1], 0], 'negate': 0,
            'occupied_thresh': 0.65, 'free_thresh': 0.25}
    (Path(directory) / f'{name}.yaml').write_text(yaml.safe_dump(meta, sort_keys=False))
    return image


def pixel_of(x, y, height, origin):
    """地圖座標 → 圖片的 (列, 行)。"""
    c = int(math.floor((x - origin[0]) / RES))
    r = height - 1 - int(math.floor((y - origin[1]) / RES))
    return r, c


def center_of(r, c, height, origin):
    """圖片的 (列, 行) → 該格中心的地圖座標。"""
    return origin[0] + (c + 0.5) * RES, origin[1] + (height - 1 - r + 0.5) * RES


def load(directory, name='m'):
    meta = yaml.safe_load((Path(directory) / f'{name}.yaml').read_text())
    return read_pgm(Path(directory) / meta['image']), meta


def wall_position(image, meta):
    rows, cols = np.nonzero(image == OCCUPIED)
    assert len(rows) == 1
    return center_of(rows[0], cols[0], image.shape[0], meta['origin'][:2])


def expected(q, pose):
    px, py, yaw = pose
    dx, dy = q[0] - px, q[1] - py
    return (math.cos(yaw) * dx + math.sin(yaw) * dy, -math.sin(yaw) * dx + math.cos(yaw) * dy)


WALL = (0.55, 0.05)                              # 牆那一格的中心


def counts(image):
    return {v: int((image == v).sum()) for v in (FREE, OCCUPIED, UNKNOWN)}


# ---------- PGM 讀寫 ----------

def test_pgm_round_trip(tmp_path):
    image = np.arange(12, dtype=np.uint8).reshape(3, 4)
    write_pgm(tmp_path / 'a.pgm', image)
    assert (tmp_path / 'a.pgm').read_bytes()[:11] == b'P5\n4 3\n255\n'
    assert np.array_equal(read_pgm(tmp_path / 'a.pgm'), image)


def test_pgm_with_comment_header(tmp_path):
    (tmp_path / 'c.pgm').write_bytes(b'P5\n# CREATOR: test\n2 1\n255\n' + bytes([0, 254]))
    assert read_pgm(tmp_path / 'c.pgm').tolist() == [[0, 254]]


def test_rejects_unsupported_pgm(tmp_path):
    (tmp_path / 'p2.pgm').write_text('P2\n2 1\n255\n0 254\n')
    with pytest.raises(MapOriginError, match='P5'):
        read_pgm(tmp_path / 'p2.pgm')


# ---------- 平移 ----------

def test_translation_keeps_image_and_moves_origin(tmp_path):
    original = make_map(tmp_path)
    set_map_origin(tmp_path, 'm', 2.0, 3.0, 0.0)
    image, meta = load(tmp_path)
    assert np.array_equal(image, original)                       # 圖片逐格不變
    assert meta['origin'] == pytest.approx([ORIGIN[0] - 2.0, ORIGIN[1] - 3.0, 0.0])
    assert wall_position(image, meta) == pytest.approx(expected(WALL, (2.0, 3.0, 0.0)))


def test_selected_point_becomes_origin(tmp_path):
    make_map(tmp_path)
    set_map_origin(tmp_path, 'm', 0.55, 0.05, 0.0)               # 選牆那一格的中心
    image, meta = load(tmp_path)
    assert wall_position(image, meta) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_other_yaml_fields_are_kept(tmp_path):
    make_map(tmp_path)
    set_map_origin(tmp_path, 'm', 0.3, 0.2, 0.0)
    _, meta = load(tmp_path)
    assert list(meta) == ['image', 'mode', 'resolution', 'origin', 'negate',
                          'occupied_thresh', 'free_thresh']
    assert (meta['image'], meta['mode'], meta['resolution']) == ('m.pgm', 'trinary', RES)
    assert meta['origin'][2] == 0                               # 角度一律 0（Nav2 多數元件忽略它）


# ---------- 旋轉 ----------

@pytest.mark.parametrize('degrees', [90, 180, 270, -90])
def test_right_angle_rotation_is_lossless(tmp_path, degrees):
    original = make_map(tmp_path)
    yaw = math.radians(degrees)
    set_map_origin(tmp_path, 'm', 0.5, -0.2, yaw)
    image, meta = load(tmp_path)
    assert counts(image) == counts(original)                    # 格數完全相同
    assert np.array_equal(image, np.rot90(original, k=-round(degrees / 90)))
    assert wall_position(image, meta) == pytest.approx(expected(WALL, (0.5, -0.2, yaw)), abs=1e-9)
    assert meta['origin'][2] == 0


def test_arbitrary_angle_resamples(tmp_path):
    original = make_map(tmp_path, width=40, height=30)
    yaw = math.radians(30)
    set_map_origin(tmp_path, 'm', 0.2, 0.1, yaw)
    image, meta = load(tmp_path)
    assert set(np.unique(image)) <= {FREE, OCCUPIED, UNKNOWN}   # 只有三種值
    assert image.size > original.size                           # 轉 30° 後外接框變大
    assert image[0, 0] == UNKNOWN and image[-1, -1] == UNKNOWN  # 新增的角落是未知
    rows, cols = np.nonzero(image == OCCUPIED)
    assert len(rows) == 1                                        # 一格的牆不會被取樣跳過、也不會變多格
    wx, wy = center_of(rows[0], cols[0], image.shape[0], meta['origin'][:2])
    ex, ey = expected(WALL, (0.2, 0.1, yaw))
    assert math.hypot(wx - ex, wy - ey) < RES                    # 最近鄰：誤差在一格內


# ---------- 備份與失敗 ----------

def test_backup_holds_previous_version(tmp_path):
    original = make_map(tmp_path)
    before_yaml = (tmp_path / 'm.yaml').read_text()
    set_map_origin(tmp_path, 'm', 1.0, 1.0, 0.0)
    assert np.array_equal(read_pgm(tmp_path / 'm.bak.pgm'), original)
    assert (tmp_path / 'm.bak.yaml').read_text() == before_yaml
    after_first = (tmp_path / 'm.yaml').read_text()
    set_map_origin(tmp_path, 'm', 1.0, 1.0, 0.0)                # 第二次：備份換成上一版
    assert (tmp_path / 'm.bak.yaml').read_text() == after_first


def test_missing_map_creates_nothing(tmp_path):
    with pytest.raises(MapOriginError, match='nope.yaml'):
        set_map_origin(tmp_path, 'nope', 0.0, 0.0, 0.0)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('name', ['', '../etc', 'a/b', 'my map', '地圖', '.hidden'])
def test_rejects_invalid_names(tmp_path, name):
    with pytest.raises(MapOriginError, match='名稱'):
        set_map_origin(tmp_path, name, 0.0, 0.0, 0.0)
    assert list(tmp_path.iterdir()) == []


def test_unsupported_image_leaves_files_untouched(tmp_path):
    make_map(tmp_path)
    (tmp_path / 'm.pgm').write_text('P2\n2 1\n255\n0 254\n')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(MapOriginError):
        set_map_origin(tmp_path, 'm', 1.0, 0.0, 0.0)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.skipif(os.geteuid() == 0, reason='root 不受檔案權限限制')
def test_write_failure_leaves_files_untouched(tmp_path):
    make_map(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    tmp_path.chmod(0o555)                                       # 資料夾唯讀：暫存檔與備份都建不了
    try:
        with pytest.raises(MapOriginError):
            set_map_origin(tmp_path, 'm', 1.0, 0.0, 0.0)
    finally:
        tmp_path.chmod(0o755)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_written_files_are_world_readable(tmp_path):
    make_map(tmp_path)
    set_map_origin(tmp_path, 'm', 1.0, 0.0, math.pi / 2)
    for name in ('m.pgm', 'm.yaml'):
        assert (tmp_path / name).stat().st_mode & 0o777 == 0o644


def test_arbitrary_angle_keeps_thin_walls_continuous(tmp_path):
    # 一格寬的直牆轉 30° 後不能出現缺口：每個舊的牆格轉過去都要是佔據
    image = np.full((40, 60), FREE, dtype=np.uint8)
    image[20, 5:55] = OCCUPIED                                   # 水平的一格寬牆，50 格
    write_pgm(tmp_path / 'w.pgm', image)
    meta = {'image': 'w.pgm', 'mode': 'trinary', 'resolution': RES, 'origin': [0.0, 0.0, 0],
            'negate': 0, 'occupied_thresh': 0.65, 'free_thresh': 0.25}
    (tmp_path / 'w.yaml').write_text(yaml.safe_dump(meta, sort_keys=False))
    yaw = math.radians(30)
    set_map_origin(tmp_path, 'w', 0.0, 0.0, yaw)
    new, new_meta = load(tmp_path, 'w')
    for c in range(5, 55):
        q = center_of(20, c, 40, (0.0, 0.0))
        x, y = expected(q, (0.0, 0.0, yaw))
        r2, c2 = pixel_of(x, y, new.shape[0], new_meta['origin'][:2])
        assert new[r2, c2] == OCCUPIED, (c, r2, c2)
