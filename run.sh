#!/usr/bin/env bash
# run.sh — wrapper for cleanup.py
# Designed to be called directly or from cron.
# Loads config from .env file, runs cleanup, logs output with timestamps.
#
# Usage:
#   ./run.sh              → live run
#   ./run.sh --dry-run    → preview only, nothing deleted

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/cleanup-$(date +%Y%m%d-%H%M%S).log"
PYTHON="${PYTHON:-python3}"

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[ERROR] Config file not found: ${ENV_FILE}"
  echo "        Copy config.env.example to .env and fill in your values."
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
mkdir -p "${LOG_DIR}"

echo "Starting Nexus Docker cleanup — $(date)"
echo "Log: ${LOG_FILE}"

# ---------------------------------------------------------------------------
# Build args
# ---------------------------------------------------------------------------
ARGS=(
  "--url"      "${NEXUS_URL}"
  "--repo"     "${NEXUS_REPO}"
  "--user"     "${NEXUS_USER}"
  "--password" "${NEXUS_PASS}"
  "--keep"     "${KEEP_LAST:-2}"
)

# Append --dry-run if passed or if FILTER has a value
if [[ "${1:-}" == "--dry-run" ]]; then
  ARGS+=("--dry-run")
fi

if [[ -n "${FILTER:-}" ]]; then
  ARGS+=("--filter" "${FILTER}")
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
"${PYTHON}" "${SCRIPT_DIR}/cleanup.py" "${ARGS[@]}" 2>&1 | tee "${LOG_FILE}"

# Keep only last 30 log files
find "${LOG_DIR}" -name "cleanup-*.log" -type f | sort | head -n -30 | xargs -r rm --

echo "Done — $(date)"
