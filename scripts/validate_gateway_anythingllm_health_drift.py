#!/usr/bin/env python3
"""Validate gateway and AnythingLLM health drift diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.gateway_anythingllm_health_drift import (  # noqa: E402
    GatewayAnythingLLMHealthDriftConfig,
    run_gateway_anythingllm_health_drift_guard,
)
from vllm_agent_gateway.acceptance.first_time_user_doctor import (  # noqa: E402
    DEFAULT_LLM_GATEWAY_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
)
from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--llm-gateway-base-url", default=DEFAULT_LLM_GATEWAY_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--expected-anythingllm-llm-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--manifest", default="runtime/fixtures.json")
    parser.add_argument("--roles", default="runtime/roles.json")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument(
        "--output-path",
        default="runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json",
    )
    parser.add_argument(
        "--doctor-output-path",
        default="runtime-state/gateway-anythingllm-health-drift/phase141/phase141-first-time-user-doctor.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_gateway_anythingllm_health_drift_guard(
        GatewayAnythingLLMHealthDriftConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path),
            doctor_output_path=Path(args.doctor_output_path),
            model_base_url=args.model_base_url,
            llm_gateway_base_url=args.llm_gateway_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            expected_anythingllm_llm_base_url=args.expected_anythingllm_llm_base_url,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            manifest_path=Path(args.manifest),
            roles_path=Path(args.roles),
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("GATEWAY ANYTHINGLLM HEALTH DRIFT " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("GATEWAY ANYTHINGLLM HEALTH DRIFT FINDINGS " + json.dumps(report["findings"], ensure_ascii=True, sort_keys=True))
        print("GATEWAY ANYTHINGLLM HEALTH DRIFT ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("GATEWAY ANYTHINGLLM HEALTH DRIFT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
