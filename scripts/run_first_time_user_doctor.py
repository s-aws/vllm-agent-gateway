#!/usr/bin/env python3
"""Run the first-time user setup doctor before AnythingLLM prompt testing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.first_time_user_doctor import (  # noqa: E402
    DEFAULT_LLM_GATEWAY_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    FirstTimeUserDoctorConfig,
    run_first_time_user_doctor,
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
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_first_time_user_doctor(
        FirstTimeUserDoctorConfig(
            config_root=Path(args.config_root),
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
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    summary = {
        "status": report["status"],
        "check_count": report.get("summary", {}).get("check_count"),
        "status_counts": report.get("summary", {}).get("status_counts"),
        "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
        "warning_check_ids": report.get("summary", {}).get("warning_check_ids"),
    }
    print(f"FIRST TIME USER DOCTOR REPORT {report['report_path']}")
    print("FIRST TIME USER DOCTOR SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("FIRST TIME USER DOCTOR FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("FIRST TIME USER DOCTOR PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
