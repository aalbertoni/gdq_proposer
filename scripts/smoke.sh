#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-http://localhost:${PORT:-8501}}"

if [[ -z "$TARGET" || "$TARGET" == '""' ]]; then
  echo "Skipping smoke: no target configured"
  exit 0
fi

curl -kfsS "${TARGET%/}/_stcore/health"
