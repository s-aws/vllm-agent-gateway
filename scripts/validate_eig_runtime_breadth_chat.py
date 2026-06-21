#!/usr/bin/env python3
"""Run Phase 295 EIG runtime breadth chat validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_runtime_breadth_chat import (
    DEFAULT_CASES_PATH,
    DEFAULT_OUTPUT_PATH,
    EIGRuntimeBreadthChatConfig,
    run_eig_runtime_breadth_chat_validation,
)  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, default=REPO_ROOT, help="Repository/config root.")
    parser.add_argument("--cases-path", type=Path, default=DEFAULT_CASES_PATH, help="Prompt case pack path.")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH, help="Report output path.")
    parser.add_argument(
        "--controller-output-root",
        type=Path,
        default=Path("runtime-state/controller-artifacts/eig-runtime-breadth-chat"),
        help="Controller artifact root for direct validation mode.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional OpenAI-compatible workflow-router base URL, for example http://127.0.0.1:8500/v1.",
    )
    parser.add_argument("--anythingllm-api-base-url", default=None, help="Optional AnythingLLM API base URL.")
    parser.add_argument("--anythingllm-workspace", default="my-workspace", help="AnythingLLM workspace slug.")
    parser.add_argument("--anythingllm-api-key-env", default="ANYTHINGLLM_API_KEY", help="Environment variable containing the AnythingLLM API key.")
    parser.add_argument("--controller-base-url", default="http://127.0.0.1:8400", help="Controller API base URL for run-record lookup in AnythingLLM mode.")
    parser.add_argument("--model", default="agentic-workflow-router", help="Model name to send to chat completions.")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="Live HTTP timeout.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = EIGRuntimeBreadthChatConfig(
        config_root=args.config_root.resolve(),
        cases_path=args.cases_path,
        output_path=args.output_path,
        controller_output_root=args.controller_output_root,
        base_url=args.base_url,
        anythingllm_api_base_url=args.anythingllm_api_base_url,
        anythingllm_workspace=args.anythingllm_workspace,
        anythingllm_api_key_env=args.anythingllm_api_key_env,
        controller_base_url=args.controller_base_url,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )
    report = run_eig_runtime_breadth_chat_validation(config)
    summary = report["summary"]
    print("EIG RUNTIME BREADTH CHAT", report["status"].upper())
    print(f"mode={report['mode']}")
    print(f"case_count={summary['case_count']}")
    print(f"passed_case_count={summary['passed_case_count']}")
    print(f"failed_case_count={summary['failed_case_count']}")
    print(f"source_connector_registry_changed={summary['source_connector_registry_changed']}")
    print(f"phase296_ready={summary['phase296_ready']}")
    print(f"report={args.output_path}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
