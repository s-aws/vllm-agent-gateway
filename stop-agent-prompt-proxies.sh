#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${AGENTIC_AGENTS_ROOT:-$SCRIPT_DIR}"
ROOT_PARENT="$(dirname "$ROOT")"
PRIVATE_ROOT="${PRIVATE_AGENTIC_AGENTS_ROOT:-$ROOT_PARENT/private_agentic_agents}"
STATE_ROOT="${AGENTIC_AGENTS_STATE_ROOT:-$PRIVATE_ROOT/runtime-state}"
PID_FILE="$STATE_ROOT/agent-prompt-proxy.pid"
GATEWAY_PID_FILE="$STATE_ROOT/llm-gateway.pid"

stop_pid_file() {
    local label="$1"
    local pid_file="$2"

    if [[ ! -f "$pid_file" ]]; then
        echo "No $label PID file found."
        return
    fi

    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -z "$pid" ]]; then
        rm -f "$pid_file"
        echo "Removed empty $label PID file."
        return
    fi

    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid"
        fi
        echo "Stopped $label PID $pid"
    else
        echo "$label PID $pid was not running."
    fi

    rm -f "$pid_file"
}

stop_pid_file "agent prompt proxy" "$PID_FILE"
stop_pid_file "LLM gateway" "$GATEWAY_PID_FILE"
