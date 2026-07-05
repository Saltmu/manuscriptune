#!/usr/bin/env bash
set -euo pipefail

# Move to the project root directory
cd "$(dirname "$0")/.."

# Parse options
FORCE_FULL=false
RUN_FIX=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix)
      RUN_FIX=true
      shift
      ;;
    --force-full|-f)
      FORCE_FULL=true
      shift
      ;;
    -h|--help)
      echo "Usage: ./scripts/local-ci.sh [options]"
      echo "Options:"
      echo "  --fix            Auto-format and fix lint issues"
      echo "  -f, --force-full Force running all steps regardless of git diff"
      echo "  -h, --help       Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

echo "========================================="
echo "Running Local CI Check..."
echo "========================================="

# 変更範囲の判定
check_changes() {
  if [ "$FORCE_FULL" = "true" ]; then
    echo "full"
    return
  fi

  # main (または origin/main) と HEAD のマージベースを取得
  local base_commit
  base_commit=$(git merge-base origin/main HEAD 2>/dev/null || git merge-base main HEAD 2>/dev/null || echo "")

  if [ -z "$base_commit" ]; then
    echo "full"
    return
  fi

  # 変更されたファイルの一覧を取得
  local changed_files
  changed_files=$( {
    git diff --name-only "${base_commit}...HEAD" 2>/dev/null
    git diff --name-only --cached 2>/dev/null
    git diff --name-only 2>/dev/null
  } | sort -u )

  if [ -z "$changed_files" ]; then
    echo "full"
    return
  fi

  local has_frontend=false
  local has_backend=false
  local has_ci=false

  while IFS= read -r file; do
    [ -z "$file" ] && continue
    if [[ "$file" =~ ^frontend/ ]]; then
      has_frontend=true
    elif [[ "$file" =~ ^(src/|tests/|pyproject\.toml|poetry\.lock) ]]; then
      has_backend=true
    elif [[ "$file" =~ ^(scripts/local-ci\.sh|\.github/workflows/) ]]; then
      has_ci=true
    else
      # その他のファイルの変更（docsや設定など）は、念のためバックエンドのテストを走らせる
      has_backend=true
    fi
  done <<< "$changed_files"

  if [ "$has_ci" = "true" ]; then
    echo "full"
  elif [ "$has_frontend" = "true" ] && [ "$has_backend" = "true" ]; then
    echo "both"
  elif [ "$has_frontend" = "true" ]; then
    echo "frontend"
  elif [ "$has_backend" = "true" ]; then
    echo "backend"
  else
    echo "full"
  fi
}

run_frontend_steps() {
  # 1. Build the frontend (tests depend on frontend/dist/index.html existing,
  # mirroring the build step in .github/workflows/ci.yml)
  echo "[1/8] Building frontend (npm ci && npm run build)..."
  (
    cd frontend
    local LOCKFILE_HASH
    LOCKFILE_HASH=$(sha256sum package-lock.json | cut -d" " -f1)
    local CACHE_FILE="node_modules/.ci-lockfile-hash"

    if [ -d "node_modules" ] && [ -f "$CACHE_FILE" ] && [ "$(cat "$CACHE_FILE")" = "$LOCKFILE_HASH" ]; then
      echo "npm ci is cached. Skipping..."
    else
      npm ci
      mkdir -p node_modules
      echo "$LOCKFILE_HASH" > "$CACHE_FILE"
    fi
    npm run build
  )

  # 6. Run frontend tests (vitest)
  echo "[6/8] Running frontend tests (vitest)..."
  (cd frontend && npm run test)
}

run_backend_steps() {
  # 2. Check code format & 3. Run Lint check
  if [ "$RUN_FIX" = "true" ]; then
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
  poetry run pytest -n auto

  # 7. Check code bloat
  echo "[7/8] Checking code bloat (detect-bloat)..."
  poetry run detect-bloat

  # 8. Audit dependencies for known vulnerabilities
  echo "[8/8] Auditing dependencies (pip-audit)..."
  # CVE-2025-71176: pytest's /tmp cache dir naming (local-user-only DoS/privilege
  # issue on shared machines). Fix requires pytest 9 + pytest-asyncio 1.x, a
  # breaking major-version bump for a dev-only test dependency never shipped to
  # production. Accepted as a known risk; revisit when upgrading the test stack.
  local SKIP_AUDIT=false
  local POETRY_LOCK_HASH
  POETRY_LOCK_HASH=$(sha256sum poetry.lock | cut -d" " -f1)
  local AUDIT_CACHE_FILE=".pip-audit-last-run"

  if [ "${GITHUB_ACTIONS:-false}" != "true" ]; then
    if [ -f "$AUDIT_CACHE_FILE" ]; then
      read -r PREV_HASH PREV_TIME < "$AUDIT_CACHE_FILE"
      local CURRENT_TIME
      CURRENT_TIME=$(date +%s)
      local TIME_DIFF
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
}

# Determine change type and run steps
CHANGE_TYPE=$(check_changes)
echo "Detected change scope: $CHANGE_TYPE"

LOG_DIR=".local_ci_logs"
mkdir -p "$LOG_DIR"

cleanup() {
  rm -rf "$LOG_DIR"
}
trap cleanup EXIT

FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_LOG="$LOG_DIR/backend.log"

FE_EXIT=0
BE_EXIT=0

if [ "$CHANGE_TYPE" = "full" ] || [ "$CHANGE_TYPE" = "both" ]; then
  echo "Running frontend and backend CI steps in parallel..."
  
  # Run in background
  run_frontend_steps > "$FRONTEND_LOG" 2>&1 &
  FE_PID=$!
  
  run_backend_steps > "$BACKEND_LOG" 2>&1 &
  BE_PID=$!
  
  # Wait for both to finish
  wait $FE_PID || FE_EXIT=$?
  wait $BE_PID || BE_EXIT=$?

  # Output logs sequentially to avoid mixing output
  echo ""
  echo "========================================="
  echo "=== Frontend Task Logs ==="
  echo "========================================="
  if [ -f "$FRONTEND_LOG" ]; then
    cat "$FRONTEND_LOG"
  else
    echo "No frontend logs found."
  fi
  echo ""

  echo "========================================="
  echo "=== Backend Task Logs ==="
  echo "========================================="
  if [ -f "$BACKEND_LOG" ]; then
    cat "$BACKEND_LOG"
  else
    echo "No backend logs found."
  fi
  echo ""

elif [ "$CHANGE_TYPE" = "frontend" ]; then
  echo "Running frontend CI steps only (backend steps skipped)..."
  run_frontend_steps || FE_EXIT=$?

elif [ "$CHANGE_TYPE" = "backend" ]; then
  echo "Running backend CI steps only (frontend steps skipped)..."
  run_backend_steps || BE_EXIT=$?
fi

# Print final result and exit
if [ $FE_EXIT -ne 0 ] || [ $BE_EXIT -ne 0 ]; then
  echo "========================================="
  echo "❌ Local CI Check Failed!"
  [ $FE_EXIT -ne 0 ] && echo "  - Frontend steps failed (exit code: $FE_EXIT)"
  [ $BE_EXIT -ne 0 ] && echo "  - Backend steps failed (exit code: $BE_EXIT)"
  echo "========================================="
  exit 1
fi

echo "========================================="
echo "✨ Local CI passed successfully!"
echo "========================================="
