#!/usr/bin/env python3
"""Validate Phase 264 clean-clone replay for the 384k large-context target."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.large_context_384k_clean_clone_replay import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    LargeContext384kCleanCloneReplayConfig,
    LargeContext384kCleanCloneReplayStatus,
    validate_large_context_384k_clean_clone_replay,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--model-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--workflow-router-gateway-base-url", default="http://127.0.0.1:8500/v1")
    parser.add_argument("--anythingllm-workflow-router-base-url")
    parser.add_argument("--controller-base-url", default="http://127.0.0.1:8400")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default="my-workspace")
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_large_context_384k_clean_clone_replay(
        LargeContext384kCleanCloneReplayConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            live=args.live,
            model_base_url=args.model_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_workflow_router_base_url=args.anythingllm_workflow_router_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(
        "PHASE264 LARGE CONTEXT 384K CLEAN CLONE REPLAY SUMMARY "
        + json.dumps(report.get("summary", {}), ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != LargeContext384kCleanCloneReplayStatus.PASSED.value:
        print("PHASE264 LARGE CONTEXT 384K CLEAN CLONE REPLAY FAIL")
        print("PHASE264 ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE264 LARGE CONTEXT 384K CLEAN CLONE REPLAY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
