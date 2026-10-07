"""場景描述 YAML → Gazebo Fortress SDF world 產生器。"""

import argparse
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

import yaml

DEFAULT_WALL_THICKNESS = 0.2
DEFAULT_WALL_HEIGHT = 2.0
OUTER_WALL_THICKNESS = 0.2
OUTER_WALL_HEIGHT = 2.0
FLOOR_THICKNESS = 0.1
NAME_PATTERN = re.compile(r'[A-Za-z0-9_-]+')

COLORS = {
    'floor': '0.6 0.6 0.6 1',
    'wall': '0.85 0.85 0.8 1',
    'shelf': '0.8 0.5 0.2 1',
    'obstacle': '0.2 0.4 0.8 1',
}

SYSTEM_PLUGINS = [
    ('ignition-gazebo-physics-system', 'ignition::gazebo::systems::Physics'),
    ('ignition-gazebo-user-commands-system', 'ignition::gazebo::systems::UserCommands'),
    ('ignition-gazebo-scene-broadcaster-system', 'ignition::gazebo::systems::SceneBroadcaster'),
    ('ignition-gazebo-sensors-system', 'ignition::gazebo::systems::Sensors'),
    ('ignition-gazebo-imu-system', 'ignition::gazebo::systems::Imu'),
]


class SceneError(Exception):
    """場景描述不合法。"""


# ---------- 驗證 ----------

def _number(value, where, positive=False):
    # bool 是 int 的子類別（isinstance(True, int) 為 True），必須明確排除
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SceneError(f'{where}: 必須是數字，收到 {value!r}')
    if positive and value <= 0:
        raise SceneError(f'{where}: 必須 > 0，收到 {value}')
    return float(value)


def _vector(value, length, where, positive=False):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise SceneError(f'{where}: 必須是 {length} 個數字的清單，收到 {value!r}')
    return [_number(v, f'{where}[{i}]', positive) for i, v in enumerate(value)]


def _field(element, key, where):
    if key not in element:
        raise SceneError(f'{where}.{key}: 缺少必要欄位')
    return element[key]


def _element_list(scene, key):
    items = scene.get(key, [])
    if not isinstance(items, list):
        raise SceneError(f'{key}: 必須是清單')
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise SceneError(f'{key}[{i}]: 必須是 mapping')
    return items


def _rect(cx, cy, length, width, yaw):
    return ('rect', cx, cy, length / 2, width / 2, yaw)


def _footprints(scene):
    """檢查各元素欄位，回傳 [(位置名稱, 佔地形狀, 牆的兩端點或 None), ...] 供邊界與出生點檢查。"""
    shapes = []
    for i, wall in enumerate(_element_list(scene, 'walls')):
        where = f'walls[{i}]'
        start = _vector(_field(wall, 'from', where), 2, f'{where}.from')
        end = _vector(_field(wall, 'to', where), 2, f'{where}.to')
        thickness = _number(wall.get('thickness', DEFAULT_WALL_THICKNESS),
                            f'{where}.thickness', positive=True)
        _number(wall.get('height', DEFAULT_WALL_HEIGHT), f'{where}.height', positive=True)
        cx, cy, length, yaw = wall_pose(start, end)
        if length == 0:
            raise SceneError(f'{where}: from 與 to 不能是同一點')
        shapes.append((where, _rect(cx, cy, length, thickness, yaw), [start, end]))

    for i, shelf in enumerate(_element_list(scene, 'shelves')):
        where = f'shelves[{i}]'
        x, y = _vector(_field(shelf, 'pos', where), 2, f'{where}.pos')
        length, width, _ = _vector(_field(shelf, 'size', where), 3, f'{where}.size', positive=True)
        yaw = _number(shelf.get('yaw', 0), f'{where}.yaw')
        shapes.append((where, _rect(x, y, length, width, yaw), None))

    for i, obstacle in enumerate(_element_list(scene, 'obstacles')):
        where = f'obstacles[{i}]'
        kind = _field(obstacle, 'type', where)
        x, y = _vector(_field(obstacle, 'pos', where), 2, f'{where}.pos')
        if kind == 'box':
            length, width, _ = _vector(_field(obstacle, 'size', where), 3, f'{where}.size',
                                       positive=True)
            yaw = _number(obstacle.get('yaw', 0), f'{where}.yaw')
            shapes.append((where, _rect(x, y, length, width, yaw), None))
        elif kind == 'cylinder':
            radius = _number(_field(obstacle, 'radius', where), f'{where}.radius', positive=True)
            _number(_field(obstacle, 'height', where), f'{where}.height', positive=True)
            shapes.append((where, ('circle', x, y, radius), None))
        else:
            raise SceneError(f'{where}.type: 必須是 box 或 cylinder，收到 {kind!r}')
    return shapes


def _corners(shape):
    _, cx, cy, hl, hw, yaw = shape
    c, s = math.cos(yaw), math.sin(yaw)
    return [(cx + c * dx - s * dy, cy + s * dx + c * dy)
            for dx, dy in ((hl, hw), (hl, -hw), (-hl, hw), (-hl, -hw))]


def _inside(points, width, length, eps=1e-9):
    return all(-eps <= x <= width + eps and -eps <= y <= length + eps for x, y in points)


def validate(scene):
    """檢查場景 dict；不合法時拋出 SceneError，訊息指出出錯的位置。"""
    if not isinstance(scene, dict):
        raise SceneError('場景必須是 mapping（YAML 的 key: value 結構）')

    if 'name' not in scene:
        raise SceneError('name: 缺少必要欄位')
    name = scene['name']
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise SceneError(f'name: 只能包含英數字、底線與連字號（會用來當檔名），收到 {name!r}')

    if 'spawn' in scene:
        # 世界不知道有哪些車：出生點屬於車子系統的設定
        raise SceneError('spawn: 場景不再定義出生點，請改在車子系統的 robot.yaml（sim.spawn）設定')

    if 'size' not in scene:
        raise SceneError('size: 缺少必要欄位')
    width, length = _vector(scene['size'], 2, 'size', positive=True)

    shapes = _footprints(scene)
    for where, shape, endpoints in shapes:
        if shape[0] == 'circle':
            _, x, y, r = shape
            points = [(x - r, y - r), (x + r, y + r)]
        else:
            points = endpoints if endpoints else _corners(shape)
        if not _inside(points, width, length):
            raise SceneError(f'{where}: 超出場景範圍 [0, {width:g}] x [0, {length:g}]')

# ---------- 產生 SDF ----------

def _fmt(*values):
    """數字 → 固定格式字串（最多 6 位小數、去掉多餘的 0），確保輸出可重現。"""
    out = []
    for v in values:
        text = f'{float(v):.6f}'.rstrip('0').rstrip('.')
        out.append('0' if text in ('-0', '') else text)
    return ' '.join(out)


def _sub(parent, tag, text=None, **attrs):
    element = ET.SubElement(parent, tag, attrs)
    if text is not None:
        element.text = text
    return element


def _link(model, name, pose, geometry, color):
    """一個 link = 一塊剛體：同一份幾何同時用於 collision（物理／光達）與 visual（外觀）。"""
    link = _sub(model, 'link', name=name)
    _sub(link, 'pose', _fmt(*pose))
    for tag in ('collision', 'visual'):
        part = _sub(link, tag, name=tag)
        shape_parent = _sub(part, 'geometry')
        kind, params = geometry
        shape = _sub(shape_parent, kind)
        for key, value in params:
            _sub(shape, key, value)
        if tag == 'visual':
            material = _sub(part, 'material')
            _sub(material, 'ambient', color)
            _sub(material, 'diffuse', color)


def _box(size):
    return ('box', [('size', _fmt(*size))])


def generate(scene):
    """已驗證的場景 dict → SDF 字串（純函式，同樣輸入一定得到同樣輸出）。"""
    width, length = scene['size']
    sdf = ET.Element('sdf', version='1.9')
    world = _sub(sdf, 'world', name=scene['name'])

    physics = _sub(world, 'physics', name='1ms', type='ignored')
    _sub(physics, 'max_step_size', '0.001')
    _sub(physics, 'real_time_factor', '1.0')
    for filename, plugin_name in SYSTEM_PLUGINS:
        plugin = _sub(world, 'plugin', filename=filename, name=plugin_name)
        if plugin_name.endswith('Sensors'):
            _sub(plugin, 'render_engine', 'ogre2')

    light = _sub(world, 'light', type='directional', name='sun')
    _sub(light, 'cast_shadows', 'true')
    _sub(light, 'pose', '0 0 10 0 0 0')
    _sub(light, 'diffuse', '0.8 0.8 0.8 1')
    _sub(light, 'specular', '0.2 0.2 0.2 1')
    _sub(light, 'direction', '-0.5 0.1 -0.9')

    model = _sub(world, 'model', name='warehouse')
    _sub(model, 'static', 'true')

    # 地板：頂面在 z = 0
    _link(model, 'floor', (width / 2, length / 2, -FLOOR_THICKNESS / 2, 0, 0, 0),
          _box((width, length, FLOOR_THICKNESS)), COLORS['floor'])

    # 外牆放在地板外側、內側牆面貼齊邊界 → 可用空間剛好是 size
    t, h = OUTER_WALL_THICKNESS, OUTER_WALL_HEIGHT
    outer = [
        ((width / 2, -t / 2), width + 2 * t, 0),            # 南
        ((width + t / 2, length / 2), length, math.pi / 2),  # 東
        ((width / 2, length + t / 2), width + 2 * t, 0),    # 北
        ((-t / 2, length / 2), length, math.pi / 2),        # 西
    ]
    for i, ((x, y), wall_length, yaw) in enumerate(outer):
        _link(model, f'outer_wall_{i}', (x, y, h / 2, 0, 0, yaw),
              _box((wall_length, t, h)), COLORS['wall'])

    for i, wall in enumerate(scene.get('walls', [])):
        thickness = wall.get('thickness', DEFAULT_WALL_THICKNESS)
        height = wall.get('height', DEFAULT_WALL_HEIGHT)
        cx, cy, wall_length, yaw = wall_pose(wall['from'], wall['to'])
        _link(model, f'wall_{i}', (cx, cy, height / 2, 0, 0, yaw),
              _box((wall_length, thickness, height)), COLORS['wall'])

    for i, shelf in enumerate(scene.get('shelves', [])):
        x, y = shelf['pos']
        size = shelf['size']
        _link(model, f'shelf_{i}', (x, y, size[2] / 2, 0, 0, shelf.get('yaw', 0)),
              _box(size), COLORS['shelf'])

    for i, obstacle in enumerate(scene.get('obstacles', [])):
        x, y = obstacle['pos']
        if obstacle['type'] == 'box':
            size = obstacle['size']
            _link(model, f'obstacle_{i}', (x, y, size[2] / 2, 0, 0, obstacle.get('yaw', 0)),
                  _box(size), COLORS['obstacle'])
        else:
            height = obstacle['height']
            geometry = ('cylinder', [('radius', _fmt(obstacle['radius'])),
                                     ('length', _fmt(height))])
            _link(model, f'obstacle_{i}', (x, y, height / 2, 0, 0, 0),
                  geometry, COLORS['obstacle'])

    ET.indent(sdf, space='  ')
    return '<?xml version="1.0" ?>\n' + ET.tostring(sdf, encoding='unicode') + '\n'


def wall_pose(start, end):
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    length = math.hypot(dx, dy)
    yaw = math.atan2(dy, dx)
    return cx, cy, length, yaw


def main(argv=None):
    parser = argparse.ArgumentParser(description='由場景 YAML 產生 Gazebo Fortress SDF world')
    parser.add_argument('scene', help='場景 YAML 檔')
    parser.add_argument('--out-dir', help='輸出資料夾（預設：場景檔上一層的 worlds/）')
    args = parser.parse_args(argv)

    scene_path = Path(args.scene)
    try:
        scene = yaml.safe_load(scene_path.read_text(encoding='utf-8'))
        validate(scene)
        sdf_text = generate(scene)
    except (OSError, yaml.YAMLError, SceneError) as e:
        print(f'gen_world: {e}', file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else scene_path.resolve().parent.parent / 'worlds'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{scene['name']}.sdf"

    # 先寫到同資料夾的暫存檔，完整寫好後才以 os.replace 一次換上：
    # 寫到一半出錯時，舊的 .sdf 不會變成半截檔案
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=f".{scene['name']}.", suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(sdf_text)
        os.chmod(tmp, 0o644)   # mkstemp 建立的檔案權限是 600（只有自己可讀），改成一般檔案的 644
        os.replace(tmp, out_path)
    except OSError as e:
        Path(tmp).unlink(missing_ok=True)
        print(f'gen_world: {e}', file=sys.stderr)
        return 1

    print(f'gen_world: 已寫入 {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
