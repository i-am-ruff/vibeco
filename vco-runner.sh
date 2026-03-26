#!/usr/bin/env bash
# vco-runner.sh — Wrapper that auto-restarts vco up on exit.
# Use this instead of running vco up directly.
# Workflow-master triggers restarts via `vco restart`.

set -euo pipefail

PIDFILE="$HOME/.vco-runner.pid"
RESTART_DELAY=5

# Single-instance guard
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ERROR: vco-runner is already running (PID $OLD_PID)"
        echo "Kill it first: kill $OLD_PID"
        exit 1
    fi
    rm -f "$PIDFILE"
fi

# Write our PID
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

echo "[vco-runner] Starting. PID=$$, pidfile=$PIDFILE"

while true; do
    echo "[vco-runner] Launching vco up..."
    uv run vco up "$@" || true
    echo "[vco-runner] vco up exited. Restarting in ${RESTART_DELAY}s..."
    sleep "$RESTART_DELAY"
done
