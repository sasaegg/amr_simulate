# 28 RobotBridge：TF 查位置、action client 狀態機

檔案：[`amr_server/ros_bridge.py`](../../ros_ws/src/amr_server/amr_server/ros_bridge.py)、[`test/test_ros_bridge.py`](../../ros_ws/src/amr_server/test/test_ros_bridge.py)

OpenSpec change `add-web-dispatch`，task 3.1。

## 為什麼要做

API（筆記 29）只認識 `RobotBridge` 介面。這一步用 rclpy 實作它：從車子系統拿地圖、位置、路徑，把派車、取消、初始位姿轉成 Nav2／AMCL 的標準介面。全部用「車上本來就有」的東西，車子系統一行都不用改：

| 用途 | ROS 介面 |
|---|---|
| 地圖 | 訂閱 `/<id>/map`（Transient Local） |
| 位置 | TF `map → <id>/base_footprint` |
| 路徑 | 訂閱 `/<id>/plan` |
| 派車／取消 | action client `/<id>/navigate_to_pose` |
| 初始位姿 | 發布 `/<id>/initialpose` |

## 做了什麼

### 1. 位置：查 TF，不訂閱 `/amcl_pose`

```python
t = self._tf.lookup_transform('map', f'{self._id}/base_footprint', Time())   # Time() = 最新一筆
if now - Time.from_msg(t.header.stamp) > pose_timeout:                       # 2 s 沒更新
    return None
```

- **為什麼不用 `/amcl_pose`**：AMCL 只在車移動一段距離後才更新（`update_min_d` 等），停著或慢慢走時很久才一筆；TF `map → odom → base_footprint` 結合了 AMCL 的修正和 odom 的高頻更新（30 Hz），和 RViz 看到的一樣。
- **`Time()`（時間 0）＝要最新的**：tf2 回傳整條鏈上「大家都有資料」的最新時間。
- **過期判斷**：車子系統停了，TF 還留在 buffer 裡（預設保留 10 s），不判斷的話網頁上會一直畫一台「停在最後位置」的車。
- **時鐘一致**：模擬時後端以 `use_sim_time:=true` 執行，`now` 和 TF 的時間戳都是 `/clock`。

### 2. 地圖：Transient Local

map_server 只在載入時發布一次地圖。訂閱 QoS 用 `TRANSIENT_LOCAL`（「晚到的訂閱者也收得到最後一筆」，類似 ROS 1 的 latched），後端晚啟動也拿得到。每收到一則 `map_version += 1`，同時轉好 PNG 快取（地圖很少變，不要每個請求都轉）。

### 3. 派車：action client 的狀態機

```
send_goal ──► navigating ──goal response──► 被拒絕 ──► failed「Nav2 拒絕目標」
                                └► 接受 ──result──► SUCCEEDED → succeeded
                                                    CANCELED  → canceled
                                                    ABORTED   → failed「Nav2 放棄（到不了或卡住）」
```

ROS 2 action 的三段：送目標（server 決定接不接受）→ 執行中的 feedback（`distance_remaining`）→ 結果（狀態碼）。Humble 的 `NavigateToPose.Result` 是空的，沒有錯誤碼，只能從狀態碼知道「放棄了」。

### 4. 兩個執行緒問題

**(a) 舊目標的結果晚到。** 導航中再派一個新目標，Nav2 會接受新的、結束舊的——舊目標的結果（ABORTED）可能在新目標**已經成功之後**才到。如果照單全收，狀態會從 succeeded 被改成 failed。

解法：每送一個目標 `goal_seq += 1`，每個回呼都帶著自己的 `seq`，不是目前的就丟掉：

```python
def _on_result(self, seq, future):
    with self._lock:
        if seq != self._goal_seq:
            return                 # 舊目標的結果晚到，不改寫目前的狀態
```

**(b) 從別的執行緒呼叫 `send_goal_async`。** API 在 FastAPI 的執行緒，ROS 回呼在 executor 的執行緒。Humble 的 `ActionClient.send_goal_async` 是「先送請求、再把 future 登記到字典」，中間沒有鎖：回覆如果剛好在登記前被 executor 處理，就會被當成「不認識的回覆」丟掉，這個目標永遠卡在 navigating。

解法：API 執行緒只做檢查和更新狀態，真正的 `send_goal_async`／`cancel_goal_async` 交給 executor 執行緒：

```python
self._node.executor.create_task(self._send, seq, goal)
```

`create_task` 是執行緒安全的，它把工作排進 executor，並喚醒它。executor 用 **SingleThreadedExecutor**，所有 ROS 回呼和這些工作都在同一個執行緒依序執行，不會互相搶。

其他共享狀態（status、goal、plan……）用一把 `threading.Lock` 保護，`state()` 回傳複本。tf2 的 Buffer 本身是執行緒安全的（C++ 內有 mutex），API 執行緒可以直接查。

### 5. 取消的兩種時機

- 已經拿到 goal handle（Nav2 接受了）→ `handle.cancel_goal_async()`。
- 剛送出、Nav2 還沒回應 → 記下 `_cancel_requested`，接受的那一刻立刻取消。

狀態等 Nav2 回報 CANCELED 才變 `canceled`（而不是一按就改），網頁看到的就是車真正的狀態。

### 6. 初始位姿

發布 `PoseWithCovarianceStamped`，共變異數和 RViz 的 2D Pose Estimate 一樣（x、y 0.25 ＝ 標準差 0.5 m；yaw 0.0685 ≈ 15°）——告訴 AMCL「大概在這裡」，粒子撒在這個範圍內。

## 怎麼驗證（2026-10-08 實測）

`test_ros_bridge.py` 14 項，同一個程序裡放一台假車（`FakeCar`）：假 action server（依目標 x 決定成功／拒絕／放棄／直到取消／等待指示）、20 Hz 的 TF、地圖與路徑發布者、initialpose 訂閱者。不需要 Gazebo 與 Nav2，約 4 秒。

- 位置來自 TF、TF 停止 0.5 s 後變 `None`、恢復後又有。
- 地圖資訊、PNG、版本遞增。
- 成功（含 feedback、路徑降取樣成 11 點、結束後路徑清空）、拒絕、放棄、取消、送出後立刻取消、沒目標時取消丟例外。
- **新目標取代舊目標，舊結果晚到**：舊目標先「暫停」，新目標成功後才讓舊目標 ABORTED，狀態仍是 succeeded、目標是新的。**刻意拿掉 `seq` 比對時這個測試會失敗**，確認它真的抓得到這個 bug。
- 導航不存在時 `send_goal` 在 2 s 內丟 `NavigationUnavailable`、狀態不變。
- 初始位姿的 frame、位置、四元數、共變異數。
- 連跑 3 次全部通過（不是碰巧）。車輛 id 用 `tst1`，不會和使用者正在跑的 `amr1` 撞名。

## 面試追問

**Q：ROS 2 action 和 service 差在哪？**
A：service 是一問一答、應該很快回；action 給長時間任務：可以接受／拒絕、執行中回報 feedback、可以取消、最後回傳結果。導航要幾十秒，所以用 action。

**Q：多執行緒程式裡，非同步回呼「晚到」怎麼處理？**
A：給每個請求一個遞增的序號（或 id），回呼時比對是不是目前的請求，舊的就丟掉。和前端處理「舊的 HTTP 回應晚到」是同一招。

**Q：rclpy 的 executor 有哪些？怎麼選？**
A：SingleThreadedExecutor 所有回呼依序在一個執行緒；MultiThreadedExecutor 可平行，但要搭配 callback group 控制哪些回呼能同時跑，也要自己處理共享狀態。這裡回呼都很短，選單執行緒，換來沒有競爭條件。

**Q：為什麼用 TF 而不是訂閱定位的 topic 取得位置？**
A：TF 結合了定位修正（低頻）與里程計（高頻），是「車現在在哪」的標準答案，也和 RViz、Nav2 用的一致；定位 topic 可能很久才更新一次。

## 踩坑紀錄

- **地圖解析度變成 0.05000000074505806**：`OccupancyGrid.info.resolution` 是 float32，轉成 Python float 後多了尾數。四捨五入到 6 位再給前端。
- **測試的 TF 不能用 static**：static transform 的時間戳不會前進，會被過期判斷當成「車子系統停了」。測試用一般的 TransformBroadcaster 以 20 Hz 發布（真實系統中 AMCL 和 odom 都是動態 TF）。
