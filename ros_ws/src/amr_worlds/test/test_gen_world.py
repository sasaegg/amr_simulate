import math
import xml.etree.ElementTree as ET

import pytest
import yaml

from amr_worlds.gen_world import generate, wall_pose, main

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
        'spawn': {'amr1': [1, 1, 0]},
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
