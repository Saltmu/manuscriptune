#!/usr/bin/env bash
set -euo pipefail

# Move to the project root directory
cd "$(dirname "$0")/.."

echo "========================================="
echo "Running Local CI Check..."
echo "========================================="

# 1. Check code format
echo "[1/5] Checking code format (ruff format)..."
poetry run ruff format --check

# 2. Run Lint check
echo "[2/5] Running lint (ruff check)..."
poetry run ruff check

# 3. Type check
echo "[3/5] Checking types (mypy)..."
poetry run mypy src tests

# 4. Run tests with coverage fail-under check (defined in pyproject.toml)
echo "[4/5] Running tests (pytest)..."
poetry run pytest

# 5. Check code bloat
echo "[5/5] Checking code bloat (detect-bloat)..."
poetry run detect-bloat

echo "========================================="
echo "✨ Local CI passed successfully!"
echo "========================================="
