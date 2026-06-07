#!/usr/bin/env python3
"""Plan or run productized local harness setup commands."""

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
from vllm_agent_gateway.acceptance.productized_setup import (  # noqa: E402
    ProductizedSetupAction,
    ProductizedSetupConfig,
    run_productized_setup,
)
from vllm_agent_gateway.acceptance.stable_handoff import DEFAULT_RELEASE_CANDIDATE_REPORT_PATH  # noqa: E402
from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[item.value for item in ProductizedSetupAction],
        help="Command group to plan or execute.",
    )
    parser.add_argument("--execute", action="store_true", help="Run the planned commands. Default only writes a plan.")
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--llm-gateway-base-url", default=DEFAULT_LLM_GATEWAY_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--release-candidate-report", default=str(DEFAULT_RELEASE_CANDIDATE_REPORT_PATH))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    parser.add_argument("--python-executable", default=None)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_productized_setup(
        ProductizedSetupConfig(
            config_root=Path(args.config_root),
            action=ProductizedSetupAction(args.action),
            output_path=Path(args.output_path) if args.output_path else None,
            model_base_url=args.model_base_url,
            llm_gateway_base_url=args.llm_gateway_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            release_candidate_report_path=Path(args.release_candidate_report)
            if args.release_candidate_report
            else None,
            timeout_seconds=args.timeout_seconds,
            command_timeout_seconds=args.command_timeout_seconds,
            python_executable=args.python_executable,
        ),
        execute=args.execute,
    )
    summary = {
        "status": report["status"],
        "action": report["action"],
        "execute": report["execute"],
        "command_count": report.get("summary", {}).get("command_count"),
        "executed_command_count": report.get("summary", {}).get("executed_command_count"),
        "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
    }
    print(f"PRODUCTIZED SETUP REPORT {report['report_path']}")
    print("PRODUCTIZED SETUP SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print(
            "PRODUCTIZED SETUP FAILURES "
            + json.dumps(
                {
                    "checks": report.get("checks", []),
                    "execution_results": [
                        item for item in report.get("execution_results", []) if item.get("status") == "failed"
                    ],
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 1
    print("PRODUCTIZED SETUP PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
