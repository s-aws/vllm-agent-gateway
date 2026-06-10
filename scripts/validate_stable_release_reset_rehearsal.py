#!/usr/bin/env python3
"""Validate Phase 153 stable release reset and recovery rehearsal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.stable_handoff import DEFAULT_RELEASE_CANDIDATE_REPORT_PATH  # noqa: E402
from vllm_agent_gateway.acceptance.stable_release_reset_rehearsal import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    StableReleaseResetRehearsalConfig,
    run_stable_release_reset_rehearsal,
)
from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--release-candidate-report", default=str(DEFAULT_RELEASE_CANDIDATE_REPORT_PATH))
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--llm-gateway-base-url", default="http://127.0.0.1:8300/v1")
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    parser.add_argument("--python-executable", default=None)
    parser.add_argument("--execute-reset-start", action="store_true")
    parser.add_argument("--execute-recovery", action="store_true")
    parser.add_argument(
        "--output-path",
        default="runtime-state/stable-release-reset-rehearsal/phase153/phase153-stable-release-reset-rehearsal-report.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_stable_release_reset_rehearsal(
        StableReleaseResetRehearsalConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            release_candidate_report_path=Path(args.release_candidate_report)
            if args.release_candidate_report
            else None,
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
            execute_reset_start=args.execute_reset_start,
            execute_recovery=args.execute_recovery,
        )
    )
    print(f"STABLE RELEASE RESET REHEARSAL REPORT {report['report_path']}")
    print(
        "STABLE RELEASE RESET REHEARSAL SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "execute_reset_start": report.get("execute_reset_start"),
                "execute_recovery": report.get("execute_recovery"),
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("STABLE RELEASE RESET REHEARSAL FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("STABLE RELEASE RESET REHEARSAL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
