import math

import pytest

from amr_hw_sim.spawn import (
    choose_world, models_from_list, position_from_pose_output, set_pose_request, worlds_from_services,
    yaw_to_quaternion)

SERVICES = """/gazebo/resource_paths/add
/gazebo/worlds
/world/warehouse_small/control
/world/warehouse_small/create
/world/warehouse_small/create_multiple
/world/warehouse_small/remove
"""


def test_world_found_from_create_service():
    assert worlds_from_services(SERVICES) == ['warehouse_small']


def test_create_multiple_is_not_mistaken_for_a_world():
    # /world/<名稱>/create_multiple 也以 create 開頭，不能被誤判
    assert worlds_from_services('/world/a/create_multiple\n') == []


def test_no_world_yet():
    assert worlds_from_services('/gazebo/worlds\n') == []
    assert choose_world([]) is None           # 繼續等


def test_single_world_is_chosen():
    assert choose_world(['w']) == 'w'


def test_multiple_worlds_are_rejected():
    with pytest.raises(RuntimeError, match='a, b'):
        choose_world(['a', 'b'])


def test_duplicate_service_lines_count_once():
    assert worlds_from_services('/world/w/create\n/world/w/create\n') == ['w']


def test_models_parsed_from_list_output():
    output = """
Requesting state for world [warehouse_small]...

Available models:
    - warehouse
    - amr1
"""
    assert models_from_list(output) == ['warehouse', 'amr1']


def test_empty_model_list():
    assert models_from_list('Requesting state for world [w]...\n\nAvailable models:\n') == []


@pytest.mark.parametrize('yaw, expected', [
    (0.0, (0, 0, 0, 1)),
    (math.pi / 2, (0, 0, math.sqrt(0.5), math.sqrt(0.5))),
    (math.pi, (0, 0, 1, 0)),
])
def test_yaw_to_quaternion(yaw, expected):
    assert yaw_to_quaternion(yaw) == pytest.approx(expected, abs=1e-9)


def test_set_pose_request_contains_name_position_and_orientation():
    req = set_pose_request('amr1', 3, 1, 0)
    assert req.startswith('name: "amr1"')
    assert 'position: {x: 3, y: 1, z: 0}' in req
    assert 'w: 1.0' in req


POSE_OUTPUT = """
Requesting state for world [warehouse_small]...

Model: [10]
  - Name: amr1
  - Pose [ XYZ (m) ] [ RPY (rad) ]:
    [3.000000 1.000000 -0.000000]
    [0.000000 -0.000000 1.570796]
"""


def test_position_parsed_from_pose_output():
    assert position_from_pose_output(POSE_OUTPUT) == pytest.approx((3.0, 1.0, 0.0))


def test_position_missing_when_model_not_found():
    assert position_from_pose_output('No model named [amr9] was found.') is None
