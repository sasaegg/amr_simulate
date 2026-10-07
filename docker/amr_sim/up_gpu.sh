#!/bin/bash
# 在背景啟動 sim、robot 兩個長駐容器（GPU 繪圖，不啟動任何程序）；額外參數轉給 docker compose up，例如 --build
set -euo pipefail
cd "$(dirname "$0")"

exec docker compose up -d "$@"
