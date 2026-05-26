#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${AGENTIC_AGENTS_ROOT:-$SCRIPT_DIR}"
ROOT_PARENT="$(dirname "$ROOT")"
PRIVATE_ROOT="${PRIVATE_AGENTIC_AGENTS_ROOT:-$ROOT_PARENT/private_agentic_agents}"
STATE_ROOT="${AGENTIC_AGENTS_STATE_ROOT:-$PRIVATE_ROOT/runtime-state}"

url_host_for_bind_host() {
    local bind_host="$1"
    case "$bind_host" in
        "" | "0.0.0.0" | "::")
            printf "127.0.0.1"
            ;;
        *)
            printf "%s" "$bind_host"
            ;;
    esac
}

print_role_endpoints() {
    local connect_host="$1"
    python3 - "$connect_host" <<'PY'
import json
import sys
from pathlib import Path

connect_host = sys.argv[1]
roles = json.loads(Path("runtime/roles.json").read_text(encoding="utf-8"))["roles"]
for role in roles:
    print(f"{role['id']}: http://{connect_host}:{role['port']}/v1")
PY
}

VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000}"
GATEWAY_BIND_HOST="${GATEWAY_BIND_HOST:-127.0.0.1}"
GATEWAY_PORT="${GATEWAY_PORT:-8300}"
GATEWAY_CONNECT_HOST="${GATEWAY_CONNECT_HOST:-$(url_host_for_bind_host "$GATEWAY_BIND_HOST")}"
GATEWAY_BASE_URL="${GATEWAY_BASE_URL:-http://${GATEWAY_CONNECT_HOST}:${GATEWAY_PORT}}"
TARGET_BASE_URL="${TARGET_BASE_URL:-$GATEWAY_BASE_URL}"
HOST_ADDRESS="${HOST_ADDRESS:-0.0.0.0}"
ROLE_CONNECT_HOST="${ROLE_CONNECT_HOST:-$(url_host_for_bind_host "$HOST_ADDRESS")}"
MODEL_LIMIT="${MODEL_LIMIT:-65536}"
TARGET_INPUT_LIMIT="${TARGET_INPUT_LIMIT:-24000}"
SAFETY_BUFFER="${SAFETY_BUFFER:-1000}"
DEFAULT_MAX_OUTPUT="${DEFAULT_MAX_OUTPUT:-4000}"
MIN_AVAILABLE_OUTPUT="${MIN_AVAILABLE_OUTPUT:-512}"
GATEWAY_PID_FILE="$STATE_ROOT/llm-gateway.pid"
GATEWAY_LOG_FILE="$STATE_ROOT/llm-gateway.log"
GATEWAY_ERR_FILE="$STATE_ROOT/llm-gateway.err.log"
PID_FILE="$STATE_ROOT/agent-prompt-proxy.pid"
LOG_FILE="$STATE_ROOT/agent-prompt-proxy.log"
ERR_FILE="$STATE_ROOT/agent-prompt-proxy.err.log"
STATE_DISPLAY_ROOT="${AGENTIC_AGENTS_STATE_DISPLAY_ROOT:-private_agentic_agents/runtime-state}"

mkdir -p "$STATE_ROOT"
cd "$ROOT"

if [[ -f "$GATEWAY_PID_FILE" ]]; then
    existing_gateway_pid="$(cat "$GATEWAY_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_gateway_pid" ]] && kill -0 "$existing_gateway_pid" 2>/dev/null; then
        echo "LLM gateway is already running as PID $existing_gateway_pid"
    else
        rm -f "$GATEWAY_PID_FILE"
    fi
fi

if [[ ! -f "$GATEWAY_PID_FILE" ]]; then
    nohup python3 -u -m vllm_agent_gateway.gateway.server \
        --target-base-url "$VLLM_BASE_URL" \
        --host "$GATEWAY_BIND_HOST" \
        --port "$GATEWAY_PORT" \
        --model-limit "$MODEL_LIMIT" \
        --target-input-limit "$TARGET_INPUT_LIMIT" \
        --safety-buffer "$SAFETY_BUFFER" \
        --default-max-output "$DEFAULT_MAX_OUTPUT" \
        --min-available-output "$MIN_AVAILABLE_OUTPUT" \
        >"$GATEWAY_LOG_FILE" 2>"$GATEWAY_ERR_FILE" &

    gateway_pid="$!"
    echo "$gateway_pid" > "$GATEWAY_PID_FILE"
    sleep 2

    if ! kill -0 "$gateway_pid" 2>/dev/null; then
        rm -f "$GATEWAY_PID_FILE"
        echo "LLM gateway exited during startup." >&2
        echo "stderr:" >&2
        cat "$GATEWAY_ERR_FILE" >&2 || true
        exit 1
    fi
    echo "Started LLM gateway PID $gateway_pid"
fi

if [[ -f "$PID_FILE" ]]; then
    existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
        echo "Agent prompt proxy is already running as PID $existing_pid"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

AGENT_PROMPT_PROXY_DEBUG_LOG="${AGENT_PROMPT_PROXY_DEBUG_LOG:-$STATE_ROOT/agent-prompt-proxy.debug.jsonl}" \
nohup python3 -u -m vllm_agent_gateway.gateway.prompt_proxy \
    --target-base-url "$TARGET_BASE_URL" \
    --host "$HOST_ADDRESS" \
    >"$LOG_FILE" 2>"$ERR_FILE" &

proxy_pid="$!"
echo "$proxy_pid" > "$PID_FILE"
sleep 2

if ! kill -0 "$proxy_pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Agent prompt proxy exited during startup." >&2
    echo "stderr:" >&2
    cat "$ERR_FILE" >&2 || true
    exit 1
fi

echo "Started agent prompt proxy PID $proxy_pid"
echo "llm gateway: ${GATEWAY_BASE_URL} -> ${VLLM_BASE_URL}"
echo "local role endpoints:"
print_role_endpoints "$ROLE_CONNECT_HOST"

if command -v hostname >/dev/null 2>&1; then
    host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ -n "$host_ip" ]]; then
        echo "network role endpoints:"
        print_role_endpoints "$host_ip"
    fi
fi
echo "Gateway logs: ${STATE_DISPLAY_ROOT}/$(basename "$GATEWAY_LOG_FILE")"
echo "Logs: ${STATE_DISPLAY_ROOT}/$(basename "$LOG_FILE")"
