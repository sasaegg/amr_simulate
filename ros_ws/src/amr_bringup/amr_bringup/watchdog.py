"""速度指令逾時判斷（純邏輯，不依賴 ROS）。

時間由呼叫端傳入，所以測試不用真的等待，也不用啟動 ROS；
rclpy 節點（cmd_vel_watchdog.py）只負責收發訊息與計時器，判斷交給這個類別。
"""


class Watchdog:
    """最後一次收到指令後超過 timeout 秒，就要求送出「一次」停車指令。"""

    def __init__(self, timeout):
        if timeout <= 0:
            raise ValueError(f'timeout 必須 > 0，收到 {timeout}')
        self._timeout = timeout
        self._last_command = None
        # 還沒收過指令時車子本來就停著，視為「已停車」，不需要送停車指令
        self._stopped = True

    def on_command(self, now):
        """收到一筆速度指令（指令本身由節點直接轉發）。"""
        self._last_command = now
        self._stopped = False

    def check(self, now):
        """定期呼叫；回傳 True 表示現在應該送出一次零速度。"""
        if self._stopped:
            return False
        if now < self._last_command:
            # 時間倒退（模擬時間被重設）：以新的時間重新計時，不誤判逾時
            self._last_command = now
            return False
        if now - self._last_command >= self._timeout:
            self._stopped = True        # 只送一次，直到下一筆指令重新啟動計時
            return True
        return False
