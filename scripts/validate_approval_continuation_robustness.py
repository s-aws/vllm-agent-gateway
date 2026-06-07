#!/usr/bin/env python3
"""Validate Phase 97 approval continuation robustness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.approval_continuation_robustness import (
    ApprovalContinuationRobustnessConfig,
    run_approval_continuation_robustness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, default=Path.cwd())
    parser.add_argument("--cases-path", type=Path, default=Path("runtime") / "approval_continuation_robustness_cases.json")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-direct", action="store_true")
    parser.add_argument("--live-gateway", action="store_true")
    parser.add_argument("--live-anythingllm", action="store_true")
    parser.add_argument("--port-health", action="store_true")
    parser.add_argument("--model-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--workflow-router-gateway-base-url", default="http://127.0.0.1:8500/v1")
    parser.add_argument("--controller-base-url", default="http://127.0.0.1:8400")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default="my-workspace")
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = ApprovalContinuationRobustnessConfig(
        config_root=args.config_root.resolve(),
        cases_path=args.cases_path,
        output_path=args.output_path,
        target_roots=tuple(args.target_roots)
        if args.target_roots
        else (
            "/mnt/c/coinbase_testing_repo_frozen_tmp",
            "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        ),
        include_direct=not args.skip_direct,
        include_gateway=args.live_gateway,
        include_anythingllm=args.live_anythingllm,
        include_port_health=args.port_health,
        model_base_url=args.model_base_url,
        workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
        controller_base_url=args.controller_base_url,
        anythingllm_api_base_url=args.anythingllm_api_base_url,
        workspace=args.workspace,
        api_key_env=args.api_key_env,
        timeout_seconds=args.timeout_seconds,
    )
    report = run_approval_continuation_robustness(config)
    print(json.dumps({"status": report["status"], "summary": report["summary"], "report_path": report["report_path"]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
