#!/usr/bin/env python3
"""Validate Phase 210 multi-repo baseline comparison dry run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    MultiRepoBaselineComparisonConfig,
    validate_multi_repo_baseline_comparison,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_multi_repo_baseline_comparison(
        MultiRepoBaselineComparisonConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            include_gateway=not args.skip_gateway,
            include_anythingllm=not args.skip_anythingllm,
            live=args.live,
            allow_partial=args.allow_partial,
            case_ids=tuple(args.case_ids or ()),
            model_base_url=args.model_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("PHASE210 MULTI REPO BASELINE COMPARISON SUMMARY " + json.dumps(report.get("summary", {}), sort_keys=True))
    if report.get("status") == "preflight_passed":
        print("PHASE210 MULTI REPO BASELINE COMPARISON OFFLINE PREFLIGHT PASS")
        print("PHASE210 closeout requires --live without --allow-partial.")
        return 0
    if report.get("status") != "passed":
        print("PHASE210 MULTI REPO BASELINE COMPARISON FAILURES " + json.dumps(report.get("errors", []), sort_keys=True))
        return 1
    print("PHASE210 MULTI REPO BASELINE COMPARISON PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
