"""中控後端的進入點（console script `server`）：一個程序同時是 ROS 節點與 HTTP 伺服器。

  背景執行緒：rclpy 的 executor（收地圖、TF、action 回覆）
  主執行緒：  uvicorn（FastAPI 的 HTTP／WebSocket）

Ctrl+C（ros2 launch 送 SIGINT）由 uvicorn 處理：它停止後再關掉 executor 與 rclpy。
rclpy 不安裝自己的訊號處理，否則它會先把 ROS 關掉，uvicorn 還在服務卻已經沒有資料。
"""

import threading

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions
import uvicorn

from amr_server.api import create_app
from amr_server.ros_bridge import FleetNode


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = FleetNode()
    host = node.declare_parameter('host', '127.0.0.1').value
    port = node.declare_parameter('port', 8000).value
    web_dir = node.declare_parameter('web_dir', '/web/dist').value

    executor = SingleThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    node.get_logger().info(
        f'車輛 {", ".join(node.bridges)}；網頁與 API：http://{host}:{port}/（API 文件 /docs）')
    app = create_app(node.bridges, web_dir=web_dir)
    try:
        # timeout_graceful_shutdown：WebSocket 不會自己結束，關閉時最多等 1 秒
        uvicorn.run(app, host=host, port=port, log_level='warning', timeout_graceful_shutdown=1)
    except KeyboardInterrupt:
        pass                                  # uvicorn 結束後會把 SIGINT 再送一次給預設處理
    finally:
        executor.shutdown()
        # 等 spin 執行緒真的結束再往下：daemon 執行緒還在 rclpy 的 C++ 程式碼裡時程序就結束，
        # 會以「terminate called without an active exception」崩潰
        spin_thread.join(timeout=2.0)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
