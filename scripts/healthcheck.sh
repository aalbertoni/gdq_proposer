#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8501}"

curl -fsS "http://localhost:${PORT}/_stcore/health"
