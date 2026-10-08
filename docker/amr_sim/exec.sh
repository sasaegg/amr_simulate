#!/bin/bash
# 進入指定的容器開互動式 bash：sim（世界）或 robot（車子系統）
# 必須指定，不做預設，避免進錯容器
set -euo pipefail
cd "$(dirname "$0")"

usage() {
    echo "用法：$0 <sim|robot>" >&2
    echo "  sim    世界：ros2 launch amr_worlds world.launch.xml" >&2
    echo "  robot  車子系統：ros2 launch amr_bringup robot.launch.xml hardware:=sim x:=1 y:=1" >&2
    exit 2
}

[ $# -eq 1 ] || usage
case "$1" in
    sim|robot) exec docker compose exec "$1" bash ;;
    *) usage ;;
esac
