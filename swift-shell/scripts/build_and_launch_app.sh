#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$PACKAGE_DIR/.." && pwd)"

APP_PATH="${APP_PATH:-$PROJECT_ROOT/output/Jarvis.app}"
APP_EXECUTABLE="$APP_PATH/Contents/MacOS/jarvis-menu-bar"
WORKER_SCRIPT="$APP_PATH/Contents/Resources/JarvisWorker/scripts/run_dashboard.py"
PIPER_SCRIPT="$APP_PATH/Contents/Resources/JarvisWorker/jarvis/piper_warm_worker.py"
BASE_URL="${JARVIS_BASE_URL:-${JARVIS_URL:-http://127.0.0.1:8765}}"

collect_existing_pids() {
  ps -axo pid=,command= | while read -r pid command; do
    [[ -n "${pid:-}" ]] || continue
    case "$command" in
      "$APP_EXECUTABLE"*|*"$WORKER_SCRIPT"*|*"$PIPER_SCRIPT"*)
        printf '%s\n' "$pid"
        ;;
    esac
  done
}

stop_existing() {
  pids=()
  while IFS= read -r pid; do
    pids+=("$pid")
  done < <(collect_existing_pids)
  if [[ "${#pids[@]}" -eq 0 ]]; then
    return
  fi
  kill "${pids[@]}" 2>/dev/null || true
  for _ in {1..20}; do
    remaining=()
    while IFS= read -r pid; do
      remaining+=("$pid")
    done < <(collect_existing_pids)
    if [[ "${#remaining[@]}" -eq 0 ]]; then
      return
    fi
    sleep 0.1
  done
  remaining=()
  while IFS= read -r pid; do
    remaining+=("$pid")
  done < <(collect_existing_pids)
  if [[ "${#remaining[@]}" -gt 0 ]]; then
    kill -TERM "${remaining[@]}" 2>/dev/null || true
  fi
}

wait_for_health() {
  for _ in {1..30}; do
    if curl -fsS "$BASE_URL/api/health" >/tmp/jarvis-build-launch-health.json 2>/dev/null; then
      cat /tmp/jarvis-build-launch-health.json
      return 0
    fi
    sleep 1
  done
  cat /tmp/jarvis-build-launch-health.json 2>/dev/null || true
  return 1
}

stop_existing
REPLACE_APP="${REPLACE_APP:-1}" "$SCRIPT_DIR/build_app_bundle.sh"
/usr/bin/open -n "$APP_PATH"
wait_for_health
