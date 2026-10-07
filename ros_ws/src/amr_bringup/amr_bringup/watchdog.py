"""速度指令逾時判斷（純邏輯，不依賴 ROS）。

時間由呼叫端傳入，所以測試不用真的等待，也不用啟動 ROS；
rclpy 節點（cmd_vel_watchdog.py）只負責收發訊息與計時器，判斷交給這個類別。
"""


class Watchdog:
    """最後一次收到指令後超過 timeout 秒，就要求送出「一次」停車指令。"""

    def __init__(self, timeout):
        raise NotImplementedError

    def on_command(self, now):
        """收到一筆速度指令（指令本身由節點直接轉發）。"""
        raise NotImplementedError

    def check(self, now):
        """定期呼叫；回傳 True 表示現在應該送出一次零速度。"""
        raise NotImplementedError
