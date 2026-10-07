#!/bin/bash

set -e # 任何一步失敗就停止

source "/opt/ros/${ROS_DISTRO}/setup.bash" --

# 工作區有原始碼，且尚未建置過或要求強制重建（BUILD=1）時才 colcon build
if [ -d /ros_ws/src ] && { [ ! -f /ros_ws/install/setup.bash ] || [ "${BUILD:-0}" = "1" ]; }; then
    echo "[entrypoint] colcon build --symlink-install"
    (cd /ros_ws && colcon build --symlink-install)
fi

if [ -f /ros_ws/install/setup.bash ]; then
    source /ros_ws/install/setup.bash --
fi

# 用目標程式取代這個 shell，讓它直接接收 docker stop / Ctrl+C 的訊號
exec "$@"
