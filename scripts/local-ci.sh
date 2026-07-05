#!/usr/bin/env bash
set -euo pipefail

# Move to the project root directory
cd "$(dirname "$0")/.."

echo "========================================="
echo "Running Local CI Check..."
echo "========================================="

# 1. Build the frontend (tests depend on frontend/dist/index.html existing,
# mirroring the build step in .github/workflows/ci.yml)
echo "[1/8] Building frontend (npm ci && npm run build)..."
(
  cd frontend
  LOCKFILE_HASH=$(sha256sum package-lock.json | cut -d" " -f1)
  CACHE_FILE="node_modules/.ci-lockfile-hash"

  if [ -d "node_modules" ] && [ -f "$CACHE_FILE" ] && [ "$(cat "$CACHE_FILE")" = "$LOCKFILE_HASH" ]; then
    echo "npm ci is cached. Skipping..."
  else
    npm ci
    mkdir -p node_modules
    echo "$LOCKFILE_HASH" > "$CACHE_FILE"
  fi
  npm run build
)

# 2. Check code format & 3. Run Lint check
if [[ " $* " == *" --fix "* ]]; then
  echo "[2/8] Formatting code (ruff format)..."
  poetry run ruff format
  echo "[3/8] Fixing lint issues (ruff check --fix)..."
  poetry run ruff check --fix
else
  echo "[2/8] Checking code format (ruff format)..."
  poetry run ruff format --check
  echo "[3/8] Running lint (ruff check)..."
  poetry run ruff check
fi


# 4. Type check
echo "[4/8] Checking types (mypy)..."
poetry run mypy src tests

# 5. Run backend tests with coverage fail-under check (defined in pyproject.toml)
echo "[5/8] Running backend tests (pytest)..."
poetry run pytest

# 6. Run frontend tests (vitest)
echo "[6/8] Running frontend tests (vitest)..."
(cd frontend && npm run test)

# 7. Check code bloat
echo "[7/8] Checking code bloat (detect-bloat)..."
poetry run detect-bloat

# 8. Audit dependencies for known vulnerabilities
echo "[8/8] Auditing dependencies (pip-audit)..."
# CVE-2025-71176: pytest's /tmp cache dir naming (local-user-only DoS/privilege
# issue on shared machines). Fix requires pytest 9 + pytest-asyncio 1.x, a
# breaking major-version bump for a dev-only test dependency never shipped to
# production. Accepted as a known risk; revisit when upgrading the test stack.
SKIP_AUDIT=false
POETRY_LOCK_HASH=$(sha256sum poetry.lock | cut -d" " -f1)
AUDIT_CACHE_FILE=".pip-audit-last-run"

if [ "${GITHUB_ACTIONS:-false}" != "true" ]; then
  if [ -f "$AUDIT_CACHE_FILE" ]; then
    read -r PREV_HASH PREV_TIME < "$AUDIT_CACHE_FILE"
    CURRENT_TIME=$(date +%s)
    TIME_DIFF=$((CURRENT_TIME - PREV_TIME))
    if [ "$PREV_HASH" = "$POETRY_LOCK_HASH" ] && [ "$TIME_DIFF" -ge 0 ] && [ "$TIME_DIFF" -lt 86400 ]; then
      SKIP_AUDIT=true
    fi
  fi
fi

if [ "$SKIP_AUDIT" = "true" ]; then
  echo "pip-audit is cached. Skipping..."
else
  poetry run pip-audit --ignore-vuln CVE-2025-71176
  echo "$POETRY_LOCK_HASH $(date +%s)" > "$AUDIT_CACHE_FILE"
fi

echo "========================================="
echo "✨ Local CI passed successfully!"
echo "========================================="
