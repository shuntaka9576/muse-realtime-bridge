#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo 'uv is required. See README.md.' >&2; exit 1; }
uv sync --frozen --no-dev --python 3.12
if [[ ! -e .env ]]; then
  (umask 077; cp .env.example .env)
  echo 'Created .env (mode 600). Set OPENAI_API_KEY and a newly generated BRIDGE_TOKEN.'
else
  echo 'Existing .env preserved.'
fi
printf '%s\n' 'Start: .venv/bin/muse-realtime-bridge --env-file .env'
