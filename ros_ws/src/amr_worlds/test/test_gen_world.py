import math
import xml.etree.ElementTree as ET

import pytest
import yaml

from amr_worlds.gen_world import SceneError, generate, main, validate, wall_pose

@pytest.fixture
def scene():
    return {
        'name': 'test_scene',
        'size': [20, 15],
        'walls': [
            {'from': [5, 0], 'to': [5, 6]},
            {'from': [10, 9], 'to': [15, 9], 'thickness': 0.3, 'height': 1.5},
        ],
        'shelves': [{'pos': [3, 8], 'yaw': 0, 'size': [2.0, 0.6, 1.8]}],
        'obstacles': [
            {'type': 'box', 'pos': [12, 4], 'size': [1, 1, 1]},
            {'type': 'cylinder', 'pos': [16, 11], 'radius': 0.4, 'height': 1.0},
        ],
    }

def test_wall_pose_horizontal():
    cx, cy, length, yaw = wall_pose([0, 0], [4, 0])
    assert (cx, cy) == pytest.approx((2.0, 0.0))
    assert length == pytest.approx(4.0)
    assert yaw == pytest.approx(0.0)

def test_wall_pose_vertical():
    cx, cy, length, yaw = wall_pose([5, 0], [5, 6])
    assert (cx, cy) == pytest.approx((5.0, 3.0))
    assert length == pytest.approx(6.0)
    assert yaw == pytest.approx(math.pi / 2)

def test_wall_pose_diagonal():
    cx, cy, length, yaw = wall_pose([0, 0], [3, 4])
    assert length == pytest.approx(5.0)
    assert yaw == pytest.approx(math.atan2(4, 3))

def links_of(sdf_text):
    root = ET.fromstring(sdf_text)
    return {link.get('name'): link for link in root.iter('link')}

def test_generate_world_named_after_scene(scene):
    root = ET.fromstring(generate(scene))
    assert root.tag == 'sdf'
    assert root.find('world').get('name') == 'test_scene'

def test_generate_has_floor_and_four_outer_walls(scene):
    links = links_of(generate(scene))
    assert 'floor' in links
    for i in range(4):
        assert f'outer_wall_{i}' in links

def test_generate_every_link_has_visual_and_collision(scene):
    links = links_of(generate(scene))
    expected = ['floor', 'wall_0', 'wall_1', 'shelf_0', 'obstacle_0', 'obstacle_1']
    for name in expected:
        assert links[name].find('visual') is not None, name
        assert links[name].find('collision') is not None, name

def pose_of(link):
    return [float(v) for v in link.find('pose').text.split()]

def box_size_of(link):
    return [float(v) for v in link.find('collision/geometry/box/size').text.split()]

def test_generate_is_deterministic(scene):
    assert generate(scene) == generate(scene)

def test_generate_wall_pose_and_default_size(scene):
    link = links_of(generate(scene))['wall_0']
    x, y, z, roll, pitch, yaw = pose_of(link)
    assert (x, y, z) == pytest.approx((5.0, 3.0, 1.0))
    assert yaw == pytest.approx(math.pi / 2)
    assert box_size_of(link) == pytest.approx([6.0, 0.2, 2.0])

def test_generate_wall_custom_thickness_and_height(scene):
    link = links_of(generate(scene))['wall_1']
    assert box_size_of(link) == pytest.approx([5.0, 0.3, 1.5])

def test_main_writes_sdf_named_after_scene(tmp_path, scene):
    scene_file = tmp_path / 'any_file_name.yaml'
    scene_file.write_text(yaml.safe_dump(scene))
    rc = main([str(scene_file), '--out-dir', str(tmp_path / 'out')])
    assert rc == 0
    assert (tmp_path / 'out' / 'test_scene.sdf').exists()

def test_validate_accepts_sample_scene(scene):
    validate(scene)

def test_validate_missing_size(scene):
    del scene['size']
    with pytest.raises(SceneError) as excinfo:
        validate(scene)
    assert 'size' in str(excinfo.value)


def assert_scene_error(scene, *fragments):
    with pytest.raises(SceneError) as excinfo:
        validate(scene)
    for fragment in fragments:
        assert fragment in str(excinfo.value)

def test_validate_accepts_minimal_scene():
    validate({'name': 'empty', 'size': [10, 10]})

@pytest.mark.parametrize('size', [[0, 15], [20, -1], [20], [20, 15, 3], 'big', [True, 15]])
def test_validate_bad_size(scene, size):
    scene['size'] = size
    assert_scene_error(scene, 'size')

@pytest.mark.parametrize('name', [None, '', '../evil', 'has space'])
def test_validate_bad_name(scene, name):
    scene['name'] = name
    assert_scene_error(scene, 'name')

def test_validate_missing_name(scene):
    del scene['name']
    assert_scene_error(scene, 'name')

def test_validate_element_list_must_be_list(scene):
    scene['walls'] = 'not a list'
    assert_scene_error(scene, 'walls')

@pytest.mark.parametrize('modify, where', [
    (lambda s: s['walls'][0].pop('from'), 'walls[0].from'),
    (lambda s: s['walls'][0].update({'to': [5]}), 'walls[0].to'),
    (lambda s: s['walls'][1].update({'thickness': 0}), 'walls[1].thickness'),
    (lambda s: s['walls'][1].update({'height': 'tall'}), 'walls[1].height'),
    (lambda s: s['shelves'][0].pop('size'), 'shelves[0].size'),
    (lambda s: s['shelves'][0].update({'size': [2.0, -0.6, 1.8]}), 'shelves[0].size'),
    (lambda s: s['shelves'][0].update({'yaw': 'north'}), 'shelves[0].yaw'),
    (lambda s: s['obstacles'][0].update({'type': 'cone'}), 'obstacles[0].type'),
    (lambda s: s['obstacles'][0].pop('size'), 'obstacles[0].size'),
    (lambda s: s['obstacles'][1].pop('radius'), 'obstacles[1].radius'),
    (lambda s: s['obstacles'][1].update({'height': 0}), 'obstacles[1].height'),
])
def test_validate_bad_element_field(scene, modify, where):
    modify(scene)
    assert_scene_error(scene, where)

@pytest.mark.parametrize('modify, where', [
    (lambda s: s['shelves'][0].update({'pos': [25, 8]}), 'shelves[0]'),
    (lambda s: s['walls'][0].update({'to': [5, 20]}), 'walls[0]'),
    (lambda s: s['obstacles'][0].update({'pos': [19.8, 4]}), 'obstacles[0]'),
    (lambda s: s['obstacles'][1].update({'pos': [19.8, 11]}), 'obstacles[1]'),
])
def test_validate_element_out_of_bounds(scene, modify, where):
    modify(scene)
    assert_scene_error(scene, where)

def test_validate_rejects_spawn_field(scene):
    # 出生點改由啟動車子系統時指定；場景還寫著 spawn 時要明確報錯，不能默默忽略
    scene['spawn'] = {'amr1': [1, 1, 0]}
    assert_scene_error(scene, 'spawn', 'robot.launch.xml')

def write_scene(path, scene):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(scene))
    return path

def test_main_default_out_dir_is_sibling_worlds(tmp_path, scene):
    scene_file = write_scene(tmp_path / 'scenes' / 'test_scene.yaml', scene)
    assert main([str(scene_file)]) == 0
    assert (tmp_path / 'worlds' / 'test_scene.sdf').exists()

def test_main_invalid_scene_returns_nonzero_and_writes_nothing(tmp_path, scene, capsys):
    del scene['size']
    scene_file = write_scene(tmp_path / 'scene.yaml', scene)
    out = tmp_path / 'out'
    assert main([str(scene_file), '--out-dir', str(out)]) != 0
    assert not out.exists() or not list(out.glob('*.sdf'))
    assert 'size' in capsys.readouterr().err

def test_main_invalid_scene_keeps_existing_sdf(tmp_path, scene):
    out = tmp_path / 'out'
    out.mkdir()
    existing = out / 'test_scene.sdf'
    existing.write_text('OLD')
    scene['shelves'][0]['pos'] = [99, 99]
    scene_file = write_scene(tmp_path / 'scene.yaml', scene)
    assert main([str(scene_file), '--out-dir', str(out)]) != 0
    assert existing.read_text() == 'OLD'

def test_main_never_touches_edited_world(tmp_path, scene):
    out = tmp_path / 'out'
    out.mkdir()
    edited = out / 'test_scene_edited.sdf'
    edited.write_text('MANUAL')
    scene_file = write_scene(tmp_path / 'scene.yaml', scene)
    assert main([str(scene_file), '--out-dir', str(out)]) == 0
    assert edited.read_text() == 'MANUAL'

def test_main_output_is_identical_across_runs(tmp_path, scene):
    scene_file = write_scene(tmp_path / 'scene.yaml', scene)
    out = tmp_path / 'out'
    main([str(scene_file), '--out-dir', str(out)])
    first = (out / 'test_scene.sdf').read_bytes()
    main([str(scene_file), '--out-dir', str(out)])
    assert (out / 'test_scene.sdf').read_bytes() == first

def test_main_yaml_syntax_error_returns_nonzero(tmp_path, capsys):
    scene_file = tmp_path / 'broken.yaml'
    scene_file.write_text('name: [unclosed')
    assert main([str(scene_file), '--out-dir', str(tmp_path)]) != 0
    assert capsys.readouterr().err

def test_main_missing_file_returns_nonzero(tmp_path, capsys):
    assert main([str(tmp_path / 'nope.yaml'), '--out-dir', str(tmp_path)]) != 0
    assert capsys.readouterr().err

def test_main_output_file_is_readable_by_others(tmp_path, scene):
    scene_file = write_scene(tmp_path / 'scene.yaml', scene)
    main([str(scene_file), '--out-dir', str(tmp_path)])
    mode = (tmp_path / 'test_scene.sdf').stat().st_mode & 0o777
    assert mode & 0o044 == 0o044, oct(mode)
