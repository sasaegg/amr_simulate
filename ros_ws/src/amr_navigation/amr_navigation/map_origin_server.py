"""標地圖原點的服務節點：/<id>/map_origin/set（amr_interfaces/srv/SetMapOrigin）。

改寫邏輯都在 map_origin.py（純 Python、有測試）；這裡只是 ROS 外殼。
放在車上：地圖檔在車上的 /data/maps，RViz 面板在哪台電腦都只是呼叫這個服務。

    ros2 run amr_navigation map_origin_server --ros-args -r __ns:=/amr1 -p maps_dir:=/data/maps
"""

import math

from amr_interfaces.srv import SetMapOrigin
import rclpy
from rclpy.node import Node

from amr_navigation.map_origin import MapOriginError, set_map_origin


class MapOriginServer(Node):

    def __init__(self):
        super().__init__('map_origin_server')
        self.declare_parameter('maps_dir', '/data/maps')
        # 相對名稱：在 namespace amr1 下是 /amr1/map_origin/set
        self.create_service(SetMapOrigin, 'map_origin/set', self.on_set_origin)

    # 注意：不能命名為 handle——會蓋掉 rclpy Node 內建的 handle 屬性（底層節點物件）
    def on_set_origin(self, request, response):
        maps_dir = self.get_parameter('maps_dir').value
        try:
            nx, ny, width, height = set_map_origin(
                maps_dir, request.map_name, request.x, request.y, request.yaw)
        except MapOriginError as e:
            response.success = False
            response.message = str(e)
            self.get_logger().warn(f'標地圖原點失敗：{e}')
            return response
        response.success = True
        response.message = (
            f'{request.map_name}：原點改到 ({request.x:.3f}, {request.y:.3f})、'
            f'{math.degrees(request.yaw):.1f}°；圖片 {width}×{height}，'
            f'yaml origin ({nx:.3f}, {ny:.3f})；備份 {request.map_name}.bak.*')
        self.get_logger().info(response.message)
        return response


def main(args=None):
    rclpy.init(args=args)
    node = MapOriginServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
