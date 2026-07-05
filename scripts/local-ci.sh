#!/usr/bin/env bash
set -euo pipefail

# Move to the project root directory
cd "$(dirname "$0")/.."

echo "========================================="
echo "Running Local CI Check..."
echo "========================================="

# 1. Build the frontend (tests depend on frontend/dist/index.html existing,
# mirroring the build step in .github/workflows/ci.yml)
echo "[1/7] Building frontend (npm ci && npm run build)..."
(cd frontend && npm ci && npm run build)

# 2. Check code format & 3. Run Lint check
if [[ " $* " == *" --fix "* ]]; then
  echo "[2/7] Formatting code (ruff format)..."
  poetry run ruff format
  echo "[3/7] Fixing lint issues (ruff check --fix)..."
  poetry run ruff check --fix
else
  echo "[2/7] Checking code format (ruff format)..."
  poetry run ruff format --check
  echo "[3/7] Running lint (ruff check)..."
  poetry run ruff check
fi


# 4. Type check
echo "[4/7] Checking types (mypy)..."
poetry run mypy src tests

# 5. Run tests with coverage fail-under check (defined in pyproject.toml)
echo "[5/7] Running tests (pytest)..."
poetry run pytest

# 6. Check code bloat
echo "[6/7] Checking code bloat (detect-bloat)..."
poetry run detect-bloat

# 7. Audit dependencies for known vulnerabilities
echo "[7/7] Auditing dependencies (pip-audit)..."
# CVE-2025-71176: pytest's /tmp cache dir naming (local-user-only DoS/privilege
# issue on shared machines). Fix requires pytest 9 + pytest-asyncio 1.x, a
# breaking major-version bump for a dev-only test dependency never shipped to
# production. Accepted as a known risk; revisit when upgrading the test stack.
poetry run pip-audit --ignore-vuln CVE-2025-71176

echo "========================================="
echo "✨ Local CI passed successfully!"
echo "========================================="
