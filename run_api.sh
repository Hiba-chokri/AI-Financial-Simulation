#!/usr/bin/env bash
# Start the Daba.Dar API and open the interactive docs.
#   ./run_api.sh
set -euo pipefail

PORT="${PORT:-8000}"
cd "$(dirname "$0")"

# Free the port if a previous run is still holding it.
if lsof -ti "tcp:${PORT}" >/dev/null 2>&1; then
  echo "Port ${PORT} in use — stopping the old server."
  lsof -ti "tcp:${PORT}" | xargs -r kill
  sleep 1
fi

echo "Daba.Dar API  ->  http://localhost:${PORT}/docs"
echo "Press Ctrl+C to stop."
echo

# Open the docs page once the server is actually accepting connections.
(
  for _ in $(seq 1 40); do
    if curl -sf "http://localhost:${PORT}/api/v1/health" >/dev/null 2>&1; then
      xdg-open "http://localhost:${PORT}/docs" >/dev/null 2>&1 || true
      break
    fi
    sleep 0.5
  done
) &

exec uvicorn main:app --reload --host 127.0.0.1 --port "${PORT}"
