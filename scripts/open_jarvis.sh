#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
APP_PATH="${PROJECT_ROOT}/output/Jarvis.app"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Jarvis app bundle not found: ${APP_PATH}" >&2
  exit 1
fi

open "${APP_PATH}"
