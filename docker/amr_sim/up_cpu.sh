#!/bin/bash
# 在背景啟動長駐的 sim 容器（軟體渲染 llvmpipe，不啟動模擬）；給沒有 NVIDIA GPU 的主機或排查 GPU 問題
set -euo pipefail
cd "$(dirname "$0")"

exec docker compose -f compose.yaml -f compose.software.yaml up -d sim "$@"
