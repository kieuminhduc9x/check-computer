#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 start-project.py "$@"
fi
if command -v py >/dev/null 2>&1; then
  exec py -3 start-project.py "$@"
fi
exec python start-project.py "$@"
