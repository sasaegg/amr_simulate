#!/bin/bash
# 在背景啟動長駐容器（不啟動任何程序；進容器用 exec.sh）
#   up.sh <gpu|cpu> <sim|robot|server|all> [其餘參數交給 docker compose up，例如 --build]
# 兩個參數都必填、不做預設（和 exec.sh 一樣），避免開錯繪圖模式或重建到另一個容器
set -euo pipefail
cd "$(dirname "$0")"

usage() {
    echo "用法：$0 <gpu|cpu> <sim|robot|server|all> [docker compose up 的參數，例如 --build]" >&2
    echo "  gpu    NVIDIA GPU 繪圖（需要 NVIDIA Container Toolkit）" >&2
    echo "  cpu    軟體渲染 llvmpipe（沒有 NVIDIA GPU 或排查 GPU 問題時）" >&2
    echo "  sim    只啟動／重建世界的容器" >&2
    echo "  robot  只啟動／重建車子系統的容器" >&2
    echo "  server 只啟動／重建中控（後端與網頁）的容器（不用 GPU，gpu／cpu 對它沒有差別）" >&2
    echo "  all    三個都啟動" >&2
    exit 2
}

[ $# -ge 2 ] || usage

# 繪圖方式：cpu 疊加軟體渲染設定（compose.software.yaml 覆寫 GPU 相關設定）
case "$1" in
    gpu) files=(-f compose.yaml) ;;
    cpu) files=(-f compose.yaml -f compose.software.yaml) ;;
    *) usage ;;
esac

# 目標容器：指定服務名稱時 compose 只建立／重建那一個；all 不指定 = 全部
case "$2" in
    sim|robot|server) services=("$2") ;;
    all) services=() ;;
    *) usage ;;
esac

shift 2
exec docker compose "${files[@]}" up -d "$@" "${services[@]}"
