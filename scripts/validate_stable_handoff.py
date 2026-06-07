#!/usr/bin/env python3
"""Run the stable-channel handoff smoke validation."""

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
)
from vllm_agent_gateway.acceptance.stable_handoff import (  # noqa: E402
    DEFAULT_RELEASE_CANDIDATE_REPORT_PATH,
    StableHandoffConfig,
    validate_stable_handoff,
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
    parser.add_argument("--release-candidate-report", default=str(DEFAULT_RELEASE_CANDIDATE_REPORT_PATH))
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--llm-gateway-base-url", default=DEFAULT_LLM_GATEWAY_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--python-executable", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_stable_handoff(
        StableHandoffConfig(
            config_root=Path(args.config_root),
            release_candidate_report_path=Path(args.release_candidate_report) if args.release_candidate_report else None,
            output_path=Path(args.output_path) if args.output_path else None,
            model_base_url=args.model_base_url,
            llm_gateway_base_url=args.llm_gateway_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            timeout_seconds=args.timeout_seconds,
            command_timeout_seconds=args.command_timeout_seconds,
            python_executable=args.python_executable,
        )
    )
    print(f"STABLE HANDOFF REPORT {report['report_path']}")
    print(
        "STABLE HANDOFF SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "release_candidate_report_path": report.get("release_candidate_report_path"),
                "target_roots": report.get("target_roots"),
                "check_count": report.get("summary", {}).get("check_count"),
                "command_count": report.get("summary", {}).get("command_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "child_report_paths": report.get("summary", {}).get("child_report_paths"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("STABLE HANDOFF FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("STABLE HANDOFF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
