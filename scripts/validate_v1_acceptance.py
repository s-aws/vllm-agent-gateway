#!/usr/bin/env python3
"""Run the V1 founder acceptance suite through gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    V1AcceptanceConfig,
    acceptance_failure_guidance,
    run_v1_acceptance,
)
from vllm_agent_gateway.acceptance.profiles import ReleaseGateProfile  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
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
    parser.add_argument(
        "--profile",
        choices=[ReleaseGateProfile.RELEASE_CANDIDATE.value],
        default=ReleaseGateProfile.RELEASE_CANDIDATE.value,
        help="V1 acceptance is the full product release-candidate profile.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_v1_acceptance(
        V1AcceptanceConfig(
            config_root=Path(args.config_root),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            timeout_seconds=args.timeout_seconds,
            command_timeout_seconds=args.command_timeout_seconds,
            output_path=Path(args.output_path) if args.output_path else None,
            python_executable=args.python_executable,
            profile=ReleaseGateProfile(args.profile),
        )
    )
    print(f"V1 ACCEPTANCE REPORT {report['report_path']}")
    print(
        "V1 ACCEPTANCE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "profile": report["profile"],
                "target_roots": report["target_roots"],
                "suite_count": len(report["suite_runs"]),
                "json_output_count": len(report["json_output"]),
                "feedback_count": len(report["feedback"]),
                "error_count": len(report["errors"]),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("V1 ACCEPTANCE FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        print(
            "V1 ACCEPTANCE NEXT ACTION "
            + json.dumps(acceptance_failure_guidance(report["errors"]), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("V1 ACCEPTANCE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
