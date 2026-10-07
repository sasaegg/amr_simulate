#!/bin/bash
# 在背景啟動長駐的 sim 容器（不啟動模擬）；額外參數轉給 docker compose up，例如 --build
set -euo pipefail
cd "$(dirname "$0")"

exec docker compose up -d sim "$@"
