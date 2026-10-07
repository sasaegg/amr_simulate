#!/bin/bash

set -euo pipefail
cd "$(dirname "$0")"

export USER_UID="$(id -u)" USER_GID="$(id -g)"
exec docker compose build "$@"
