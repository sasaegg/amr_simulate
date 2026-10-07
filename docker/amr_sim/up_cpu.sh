#!/bin/bash
# 在背景啟動 sim、robot 兩個長駐容器（軟體渲染 llvmpipe）；給沒有 NVIDIA GPU 的主機或排查 GPU 問題
set -euo pipefail
cd "$(dirname "$0")"

exec docker compose -f compose.yaml -f compose.software.yaml up -d "$@"
