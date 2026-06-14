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

openai_base_url() {
    local base="${1%/}"
    case "$base" in
        */v1)
            printf "%s" "$base"
            ;;
        *)
            printf "%s/v1" "$base"
            ;;
    esac
}

openai_models_url() {
    printf "%s/models" "$(openai_base_url "$1")"
}

print_health_status() {
    local label="$1"
    local url="$2"

    if ! command -v curl >/dev/null 2>&1; then
        echo "${label}: not checked; curl is unavailable (${url})"
        return
    fi

    if curl -fsS --max-time 10 "$url" >/dev/null 2>&1; then
        echo "${label}: ok (${url})"
    else
        echo "${label}: not ready (${url})"
    fi
}

print_allowed_target_roots() {
    local roots="$1"
    local root

    IFS=':' read -r -a allowed_roots <<< "$roots"
    for root in "${allowed_roots[@]}"; do
        if [[ -n "$root" ]]; then
            echo "- $root"
        fi
    done
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
CONTROLLER_BIND_HOST="${CONTROLLER_BIND_HOST:-127.0.0.1}"
CONTROLLER_PORT="${CONTROLLER_PORT:-8400}"
CONTROLLER_CONNECT_HOST="${CONTROLLER_CONNECT_HOST:-$(url_host_for_bind_host "$CONTROLLER_BIND_HOST")}"
CONTROLLER_BASE_URL="${CONTROLLER_BASE_URL:-http://${CONTROLLER_CONNECT_HOST}:${CONTROLLER_PORT}}"
GATEWAY_CONTROLLER_ROUTING="${GATEWAY_CONTROLLER_ROUTING:-explicit_envelope}"
GATEWAY_CONTROLLER_HARNESS_URL="${GATEWAY_CONTROLLER_HARNESS_URL:-${CONTROLLER_BASE_URL}/v1/controller/harness/chat/completions}"
WORKFLOW_ROUTER_GATEWAY_ENABLED="${WORKFLOW_ROUTER_GATEWAY_ENABLED:-1}"
WORKFLOW_ROUTER_GATEWAY_BIND_HOST="${WORKFLOW_ROUTER_GATEWAY_BIND_HOST:-127.0.0.1}"
WORKFLOW_ROUTER_GATEWAY_PORT="${WORKFLOW_ROUTER_GATEWAY_PORT:-8500}"
WORKFLOW_ROUTER_GATEWAY_CONNECT_HOST="${WORKFLOW_ROUTER_GATEWAY_CONNECT_HOST:-$(url_host_for_bind_host "$WORKFLOW_ROUTER_GATEWAY_BIND_HOST")}"
WORKFLOW_ROUTER_GATEWAY_BASE_URL="${WORKFLOW_ROUTER_GATEWAY_BASE_URL:-http://${WORKFLOW_ROUTER_GATEWAY_CONNECT_HOST}:${WORKFLOW_ROUTER_GATEWAY_PORT}}"
WORKFLOW_ROUTER_GATEWAY_OPENAI_BASE_URL="$(openai_base_url "$WORKFLOW_ROUTER_GATEWAY_BASE_URL")"
GATEWAY_OPENAI_BASE_URL="$(openai_base_url "$GATEWAY_BASE_URL")"
WORKFLOW_ROUTER_CONTROLLER_URL="${WORKFLOW_ROUTER_CONTROLLER_URL:-${CONTROLLER_BASE_URL}/v1/controller/workflow-router/chat/completions}"
CONTROLLER_OUTPUT_ROOT="${CONTROLLER_OUTPUT_ROOT:-$STATE_ROOT/controller-artifacts}"
DEFAULT_CONTROLLER_ALLOWED_TARGET_ROOTS="$ROOT"
for fixture_root in /mnt/c/coinbase_testing_repo_frozen_tmp /mnt/c/coinbase_testing_repo_frozen_tmp.github /mnt/c/staterail_testing_repo_frozen_tmp.github; do
    if [[ -d "$fixture_root" ]]; then
        DEFAULT_CONTROLLER_ALLOWED_TARGET_ROOTS="${DEFAULT_CONTROLLER_ALLOWED_TARGET_ROOTS}:$fixture_root"
    fi
done
CONTROLLER_ALLOWED_TARGET_ROOTS="${CONTROLLER_ALLOWED_TARGET_ROOTS:-$DEFAULT_CONTROLLER_ALLOWED_TARGET_ROOTS}"
CONTROLLER_DEFAULT_ROLE_BASE_URL="${CONTROLLER_DEFAULT_ROLE_BASE_URL:-$(openai_base_url "$VLLM_BASE_URL")}"
MODEL_LIMIT="${MODEL_LIMIT:-65536}"
TARGET_INPUT_LIMIT="${TARGET_INPUT_LIMIT:-24000}"
SAFETY_BUFFER="${SAFETY_BUFFER:-1000}"
DEFAULT_MAX_OUTPUT="${DEFAULT_MAX_OUTPUT:-4000}"
MIN_AVAILABLE_OUTPUT="${MIN_AVAILABLE_OUTPUT:-512}"
GATEWAY_PID_FILE="$STATE_ROOT/llm-gateway.pid"
GATEWAY_LOG_FILE="$STATE_ROOT/llm-gateway.log"
GATEWAY_ERR_FILE="$STATE_ROOT/llm-gateway.err.log"
WORKFLOW_ROUTER_GATEWAY_PID_FILE="$STATE_ROOT/workflow-router-gateway.pid"
WORKFLOW_ROUTER_GATEWAY_LOG_FILE="$STATE_ROOT/workflow-router-gateway.log"
WORKFLOW_ROUTER_GATEWAY_ERR_FILE="$STATE_ROOT/workflow-router-gateway.err.log"
CONTROLLER_PID_FILE="$STATE_ROOT/controller-service.pid"
CONTROLLER_LOG_FILE="$STATE_ROOT/controller-service.log"
CONTROLLER_ERR_FILE="$STATE_ROOT/controller-service.err.log"
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
        --controller-routing "$GATEWAY_CONTROLLER_ROUTING" \
        --controller-harness-url "$GATEWAY_CONTROLLER_HARNESS_URL" \
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

if [[ "$WORKFLOW_ROUTER_GATEWAY_ENABLED" == "1" ]]; then
    if [[ -f "$WORKFLOW_ROUTER_GATEWAY_PID_FILE" ]]; then
        existing_workflow_router_gateway_pid="$(cat "$WORKFLOW_ROUTER_GATEWAY_PID_FILE" 2>/dev/null || true)"
        if [[ -n "$existing_workflow_router_gateway_pid" ]] && kill -0 "$existing_workflow_router_gateway_pid" 2>/dev/null; then
            echo "Workflow router gateway is already running as PID $existing_workflow_router_gateway_pid"
        else
            rm -f "$WORKFLOW_ROUTER_GATEWAY_PID_FILE"
        fi
    fi

    if [[ ! -f "$WORKFLOW_ROUTER_GATEWAY_PID_FILE" ]]; then
        nohup python3 -u -m vllm_agent_gateway.gateway.server \
            --target-base-url "$VLLM_BASE_URL" \
            --host "$WORKFLOW_ROUTER_GATEWAY_BIND_HOST" \
            --port "$WORKFLOW_ROUTER_GATEWAY_PORT" \
            --controller-routing workflow_router \
            --controller-harness-url "$WORKFLOW_ROUTER_CONTROLLER_URL" \
            --model-limit "$MODEL_LIMIT" \
            --target-input-limit "$TARGET_INPUT_LIMIT" \
            --safety-buffer "$SAFETY_BUFFER" \
            --default-max-output "$DEFAULT_MAX_OUTPUT" \
            --min-available-output "$MIN_AVAILABLE_OUTPUT" \
            >"$WORKFLOW_ROUTER_GATEWAY_LOG_FILE" 2>"$WORKFLOW_ROUTER_GATEWAY_ERR_FILE" &

        workflow_router_gateway_pid="$!"
        echo "$workflow_router_gateway_pid" > "$WORKFLOW_ROUTER_GATEWAY_PID_FILE"
        sleep 2

        if ! kill -0 "$workflow_router_gateway_pid" 2>/dev/null; then
            rm -f "$WORKFLOW_ROUTER_GATEWAY_PID_FILE"
            echo "Workflow router gateway exited during startup." >&2
            echo "stderr:" >&2
            cat "$WORKFLOW_ROUTER_GATEWAY_ERR_FILE" >&2 || true
            exit 1
        fi
        echo "Started workflow router gateway PID $workflow_router_gateway_pid"
    fi
fi

proxy_running=0
if [[ -f "$PID_FILE" ]]; then
    existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
        echo "Agent prompt proxy is already running as PID $existing_pid"
        proxy_running=1
    else
        rm -f "$PID_FILE"
    fi
fi

if [[ "$proxy_running" != "1" ]]; then
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
fi

controller_running=0
if [[ -f "$CONTROLLER_PID_FILE" ]]; then
    existing_controller_pid="$(cat "$CONTROLLER_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_controller_pid" ]] && kill -0 "$existing_controller_pid" 2>/dev/null; then
        echo "Controller service is already running as PID $existing_controller_pid"
        controller_running=1
    else
        rm -f "$CONTROLLER_PID_FILE"
    fi
fi

if [[ "$controller_running" != "1" ]]; then
    IFS=':' read -r -a controller_allowed_roots <<< "$CONTROLLER_ALLOWED_TARGET_ROOTS"
    controller_allowed_args=()
    for allowed_root in "${controller_allowed_roots[@]}"; do
        if [[ -n "$allowed_root" ]]; then
            controller_allowed_args+=(--allowed-target-root "$allowed_root")
        fi
    done
    controller_role_args=()
    if [[ -n "${CONTROLLER_DEFAULT_ROLE_BASE_URL:-}" ]]; then
        controller_role_args+=(--default-role-base-url "$CONTROLLER_DEFAULT_ROLE_BASE_URL")
    fi

    nohup python3 -u -m vllm_agent_gateway.controller_service.server \
        --config-root "$ROOT" \
        --output-root "$CONTROLLER_OUTPUT_ROOT" \
        --host "$CONTROLLER_BIND_HOST" \
        --port "$CONTROLLER_PORT" \
        "${controller_allowed_args[@]}" \
        "${controller_role_args[@]}" \
        >"$CONTROLLER_LOG_FILE" 2>"$CONTROLLER_ERR_FILE" &

    controller_pid="$!"
    echo "$controller_pid" > "$CONTROLLER_PID_FILE"
    sleep 2

    if ! kill -0 "$controller_pid" 2>/dev/null; then
        rm -f "$CONTROLLER_PID_FILE"
        echo "Controller service exited during startup." >&2
        echo "stderr:" >&2
        cat "$CONTROLLER_ERR_FILE" >&2 || true
        exit 1
    fi

    echo "Started controller service PID $controller_pid"
fi

echo "llm gateway: ${GATEWAY_BASE_URL} -> ${VLLM_BASE_URL}"
echo "llm gateway OpenAI base URL: ${GATEWAY_OPENAI_BASE_URL}"
echo "gateway controller routing: ${GATEWAY_CONTROLLER_ROUTING} -> ${GATEWAY_CONTROLLER_HARNESS_URL}"
if [[ "$WORKFLOW_ROUTER_GATEWAY_ENABLED" == "1" ]]; then
    echo "workflow router gateway: ${WORKFLOW_ROUTER_GATEWAY_BASE_URL} -> ${WORKFLOW_ROUTER_CONTROLLER_URL}"
    echo "AnythingLLM target URL: ${WORKFLOW_ROUTER_GATEWAY_OPENAI_BASE_URL}"
fi
echo "controller service: ${CONTROLLER_BASE_URL}"
echo "controller default role base URL: ${CONTROLLER_DEFAULT_ROLE_BASE_URL}"
echo "controller allowed target roots:"
print_allowed_target_roots "$CONTROLLER_ALLOWED_TARGET_ROOTS"
echo "controller artifact root: ${CONTROLLER_OUTPUT_ROOT}"
echo "local role endpoints:"
print_role_endpoints "$ROLE_CONNECT_HOST"

if command -v hostname >/dev/null 2>&1; then
    host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ -n "$host_ip" ]]; then
        echo "network role endpoints:"
        print_role_endpoints "$host_ip"
    fi
fi
echo "port status:"
print_health_status "model 8000" "$(openai_models_url "$VLLM_BASE_URL")"
print_health_status "llm gateway ${GATEWAY_PORT}" "$(openai_models_url "$GATEWAY_BASE_URL")"
if [[ "$WORKFLOW_ROUTER_GATEWAY_ENABLED" == "1" ]]; then
    print_health_status "workflow router gateway ${WORKFLOW_ROUTER_GATEWAY_PORT}" "$(openai_models_url "$WORKFLOW_ROUTER_GATEWAY_BASE_URL")"
fi
print_health_status "controller ${CONTROLLER_PORT}" "${CONTROLLER_BASE_URL}/health"
echo "client targets:"
echo "- AnythingLLM natural workflow testing: ${WORKFLOW_ROUTER_GATEWAY_OPENAI_BASE_URL}"
echo "- ordinary OpenAI-compatible model/gateway chat: ${GATEWAY_OPENAI_BASE_URL}"
echo "- controller HTTP API only, not an OpenAI model endpoint: ${CONTROLLER_BASE_URL}"
echo "validation note: run live validators from Bash if Windows clients receive headers but time out waiting for body bytes."
echo "Gateway logs: ${STATE_DISPLAY_ROOT}/$(basename "$GATEWAY_LOG_FILE")"
if [[ "$WORKFLOW_ROUTER_GATEWAY_ENABLED" == "1" ]]; then
    echo "Workflow router gateway logs: ${STATE_DISPLAY_ROOT}/$(basename "$WORKFLOW_ROUTER_GATEWAY_LOG_FILE")"
fi
echo "Controller logs: ${STATE_DISPLAY_ROOT}/$(basename "$CONTROLLER_LOG_FILE")"
echo "Logs: ${STATE_DISPLAY_ROOT}/$(basename "$LOG_FILE")"
