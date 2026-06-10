#!/usr/bin/env python3
"""Validate the Phase 147 external tester dry-run path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.external_tester_dry_run import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    ExternalTesterDryRunConfig,
    run_external_tester_dry_run,
)
from vllm_agent_gateway.acceptance.first_time_user_doctor import (  # noqa: E402
    DEFAULT_LLM_GATEWAY_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
)
from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json",
    )
    parser.add_argument("--live-runtime", action="store_true")
    parser.add_argument("--include-feedback", action="store_true")
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--llm-gateway-base-url", default=DEFAULT_LLM_GATEWAY_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_external_tester_dry_run(
        ExternalTesterDryRunConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            live_runtime=args.live_runtime,
            include_feedback=args.include_feedback,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            model_base_url=args.model_base_url,
            llm_gateway_base_url=args.llm_gateway_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(f"EXTERNAL TESTER DRY RUN REPORT {report['report_path']}")
    print(
        "EXTERNAL TESTER DRY RUN SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "channel_under_test": report.get("channel_under_test"),
                "live_runtime": report.get("summary", {}).get("live_runtime"),
                "doc_blocker_count": report.get("summary", {}).get("doc_blocker_count"),
                "doc_ambiguity_count": report.get("summary", {}).get("doc_ambiguity_count"),
                "doctor_failed_check_count": report.get("summary", {}).get("doctor_failed_check_count"),
                "onboarding_live_status": report.get("summary", {}).get("onboarding_live_status"),
                "onboarding_live_case_count": report.get("summary", {}).get("onboarding_live_case_count"),
                "feedback_count": report.get("summary", {}).get("feedback_count"),
                "error_count": report.get("summary", {}).get("error_count"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EXTERNAL TESTER DRY RUN ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("EXTERNAL TESTER DRY RUN PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
