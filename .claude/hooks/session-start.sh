#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

poetry env use /usr/bin/python3.12
poetry install --no-interaction

(
  cd tools/orchestune
  poetry env use /usr/bin/python3.12
  poetry install --no-interaction
)
