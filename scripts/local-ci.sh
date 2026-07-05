#!/usr/bin/env bash
set -euo pipefail

# Move to the project root directory
cd "$(dirname "$0")/.."

echo "========================================="
echo "Running Local CI Check..."
echo "========================================="

# 1. Check code format & 2. Run Lint check
if [[ " $* " == *" --fix "* ]]; then
  echo "[1/2] Formatting code (ruff format)..."
  poetry run ruff format
  echo "[2/2] Fixing lint issues (ruff check --fix)..."
  poetry run ruff check --fix
else
  echo "[1/6] Checking code format (ruff format)..."
  poetry run ruff format --check
  echo "[2/6] Running lint (ruff check)..."
  poetry run ruff check
fi


# 3. Type check
echo "[3/6] Checking types (mypy)..."
poetry run mypy src tests

# 4. Run tests with coverage fail-under check (defined in pyproject.toml)
echo "[4/6] Running tests (pytest)..."
poetry run pytest

# 5. Check code bloat
echo "[5/6] Checking code bloat (detect-bloat)..."
poetry run detect-bloat

# 6. Audit dependencies for known vulnerabilities
echo "[6/6] Auditing dependencies (pip-audit)..."
# CVE-2025-71176: pytest's /tmp cache dir naming (local-user-only DoS/privilege
# issue on shared machines). Fix requires pytest 9 + pytest-asyncio 1.x, a
# breaking major-version bump for a dev-only test dependency never shipped to
# production. Accepted as a known risk; revisit when upgrading the test stack.
poetry run pip-audit --ignore-vuln CVE-2025-71176

echo "========================================="
echo "✨ Local CI passed successfully!"
echo "========================================="
