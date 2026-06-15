#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$PACKAGE_DIR/.." && pwd)"

APP_PATH="${APP_PATH:-$PROJECT_ROOT/output/Jarvis.app}"
APP_EXECUTABLE="$APP_PATH/Contents/MacOS/jarvis-menu-bar"
STATUS_HELPER_EXECUTABLE="$APP_PATH/Contents/MacOS/jarvis-status-helper"
WORKER_SCRIPT="$APP_PATH/Contents/Resources/JarvisWorker/scripts/run_dashboard.py"
PIPER_SCRIPT="$APP_PATH/Contents/Resources/JarvisWorker/jarvis/piper_warm_worker.py"
BASE_URL="${JARVIS_BASE_URL:-${JARVIS_URL:-http://127.0.0.1:8765}}"
HEALTH_FILE="${TMPDIR:-/tmp}/jarvis-build-launch-health.json"

collect_existing_pids() {
  ps -axo pid=,command= | while read -r pid command; do
    [[ -n "${pid:-}" ]] || continue
    case "$command" in
      "$APP_EXECUTABLE"*|*"$STATUS_HELPER_EXECUTABLE"*|*"$WORKER_SCRIPT"*|*"$PIPER_SCRIPT"*)
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
    if curl -fsS "$BASE_URL/api/health" >"$HEALTH_FILE" 2>/dev/null; then
      cat "$HEALTH_FILE"
      return 0
    fi
    sleep 1
  done
  printf 'Jarvis health did not become ready at %s after 30 seconds.\n' "$BASE_URL" >&2
  if [[ -s "$HEALTH_FILE" ]]; then
    printf 'Last health response:\n' >&2
    cat "$HEALTH_FILE" >&2
    printf '\n' >&2
  fi
  return 1
}

refresh_overnight_report() {
  if python3 "$PROJECT_ROOT/scripts/render_overnight_status.py" --base-url "$BASE_URL" >/dev/null; then
    printf 'Refreshed Jarvis report surfaces at %s/overnight-report/ and %s/overnight-workboard/.\n' "$BASE_URL" "$BASE_URL"
    return 0
  fi
  printf 'Warning: Jarvis launched, but report surface refresh failed.\n' >&2
  return 0
}

diagnose_launch_state() {
  printf 'Launch diagnostics:\n'
  printf '  app: %s\n' "$APP_PATH"
  printf '  executable: %s\n' "$APP_EXECUTABLE"
  printf '  status helper: %s\n' "$STATUS_HELPER_EXECUTABLE"
  printf '  health: %s/api/health\n' "$BASE_URL"
  local found=0
  while IFS= read -r pid; do
    found=1
    printf '  existing pid: %s\n' "$pid"
  done < <(collect_existing_pids)
  if [[ "$found" -eq 0 ]]; then
    printf '  existing pid: none\n'
  fi
}

stop_existing
REPLACE_APP="${REPLACE_APP:-1}" "$SCRIPT_DIR/build_app_bundle.sh"
for attempt in 1 2; do
  if ! /usr/bin/open "$APP_PATH"; then
    printf 'open failed for %s on attempt %s\n' "$APP_PATH" "$attempt" >&2
    if [[ "$attempt" -lt 2 ]]; then
      sleep 1
      continue
    fi
    exit 1
  fi
  if wait_for_health; then
    refresh_overnight_report
    exit 0
  fi
  printf 'Jarvis health check failed on launch attempt %s.\n' "$attempt" >&2
  diagnose_launch_state >&2
  if [[ "$attempt" -lt 2 ]]; then
    stop_existing
    sleep 1
  fi
done
printf 'Jarvis launch failed after 2 attempts.\n' >&2
exit 1
