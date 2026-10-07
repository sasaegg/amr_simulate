"""場景描述 YAML → Gazebo Fortress SDF world 產生器。"""


class SceneError(Exception):
    """場景描述不合法。"""


def validate(scene):
    raise NotImplementedError


def generate(scene):
    raise NotImplementedError


def wall_pose(start, end):
    raise NotImplementedError


def main(argv=None):
    raise NotImplementedError
