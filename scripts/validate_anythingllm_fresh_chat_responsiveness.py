#!/usr/bin/env python3
"""Validate Phase 237 AnythingLLM fresh chat responsiveness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.anythingllm_fresh_chat_responsiveness import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_POLICY_PATH,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    AnythingLLMFreshChatResponsivenessConfig,
    FreshChatStatus,
    run_anythingllm_fresh_chat_responsiveness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument(
        "--anythingllm-workflow-router-base-url",
        default=None,
        help=(
            "Expected GenericOpenAiBasePath in AnythingLLM. "
            "Defaults to the policy workflow_router_base_url when omitted."
        ),
    )
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--ui-report-path", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--output-path",
        default="runtime-state/anythingllm-fresh-chat-responsiveness/phase237/phase237-anythingllm-fresh-chat-responsiveness-report.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_anythingllm_fresh_chat_responsiveness(
        AnythingLLMFreshChatResponsivenessConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path),
            policy_path=Path(args.policy_path),
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_workflow_router_base_url=args.anythingllm_workflow_router_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots) if args.target_roots else (
                "/mnt/c/coinbase_testing_repo_frozen_tmp",
                "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            ),
            ui_report_path=Path(args.ui_report_path) if args.ui_report_path else None,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(
        "ANYTHINGLLM FRESH CHAT RESPONSIVENESS "
        + json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"],
                "summary": report["summary"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != FreshChatStatus.PASSED.value:
        print("ANYTHINGLLM FRESH CHAT RESPONSIVENESS ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True))
        return 1
    print("ANYTHINGLLM FRESH CHAT RESPONSIVENESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
