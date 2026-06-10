#!/usr/bin/env python3
"""Validate Phase 111 closed-loop eval repair execution proof."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eval_repair_execution_gate import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_HOLDOUT_CASE_ID,
    DEFAULT_TARGET_CASE_ID,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    EvalRepairExecutionGateConfig,
    run_closed_loop_eval_repair_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--target-case-id", default=DEFAULT_TARGET_CASE_ID)
    parser.add_argument("--holdout-case-id", default=DEFAULT_HOLDOUT_CASE_ID)
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--include-port-health", action="store_true")
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_closed_loop_eval_repair_gate(
        EvalRepairExecutionGateConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path) if args.output_path else None,
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            target_case_id=args.target_case_id,
            holdout_case_id=args.holdout_case_id,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            execute_live=args.execute_live,
            include_port_health=args.include_port_health,
        )
    )
    summary = {
        "status": report["status"],
        "target_prompt_case_id": report["target_prompt_case_id"],
        "holdout_prompt_case_id": report["holdout_prompt_case_id"],
        "target_result_status": report.get("execution", {}).get("target_result_status"),
        "holdout_result_status": report.get("execution", {}).get("holdout_result_status"),
        "port_health_status": report.get("execution", {}).get("port_health_status"),
        "validation_error_count": len(report.get("validation_errors", [])),
        "markdown_report_path": report.get("markdown_report_path"),
    }
    print(f"CLOSED LOOP EVAL REPAIR REPORT {report['report_path']}")
    print("CLOSED LOOP EVAL REPAIR SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print(
            "CLOSED LOOP EVAL REPAIR FAILURES "
            + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("CLOSED LOOP EVAL REPAIR PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
