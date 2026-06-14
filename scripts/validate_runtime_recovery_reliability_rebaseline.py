#!/usr/bin/env python3
"""Validate Phase 231 runtime recovery reliability rebaseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.runtime_recovery_reliability_rebaseline import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_DOCTOR_OUTPUT_PATH,
    DEFAULT_HEALTH_DRIFT_OUTPUT_PATH,
    DEFAULT_LARGE_CONTEXT_MARKDOWN_PATH,
    DEFAULT_LARGE_CONTEXT_OUTPUT_PATH,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_POST_RESTART_OUTPUT_PATH,
    DEFAULT_RESTART_EVIDENCE_PATH,
    DEFAULT_SESSION_RECOVERY_OUTPUT_PATH,
    DEFAULT_SMALL_REPO_OUTPUT_PATH,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    RuntimeRecoveryRebaselineConfig,
    run_runtime_recovery_rebaseline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--restart-evidence-path", default=str(DEFAULT_RESTART_EVIDENCE_PATH))
    parser.add_argument("--post-restart-output-path", default=str(DEFAULT_POST_RESTART_OUTPUT_PATH))
    parser.add_argument("--health-drift-output-path", default=str(DEFAULT_HEALTH_DRIFT_OUTPUT_PATH))
    parser.add_argument("--doctor-output-path", default=str(DEFAULT_DOCTOR_OUTPUT_PATH))
    parser.add_argument("--session-recovery-output-path", default=str(DEFAULT_SESSION_RECOVERY_OUTPUT_PATH))
    parser.add_argument("--small-repo-output-path", default=str(DEFAULT_SMALL_REPO_OUTPUT_PATH))
    parser.add_argument("--large-context-output-path", default=str(DEFAULT_LARGE_CONTEXT_OUTPUT_PATH))
    parser.add_argument("--large-context-markdown-path", default=str(DEFAULT_LARGE_CONTEXT_MARKDOWN_PATH))
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--restart-managed-stack", action="store_true")
    parser.add_argument("--restart-vllm-container")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_runtime_recovery_rebaseline(
        RuntimeRecoveryRebaselineConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            restart_evidence_path=Path(args.restart_evidence_path),
            post_restart_output_path=Path(args.post_restart_output_path),
            health_drift_output_path=Path(args.health_drift_output_path),
            doctor_output_path=Path(args.doctor_output_path),
            session_recovery_output_path=Path(args.session_recovery_output_path),
            small_repo_output_path=Path(args.small_repo_output_path),
            large_context_output_path=Path(args.large_context_output_path),
            large_context_markdown_path=Path(args.large_context_markdown_path),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            model_base_url=args.model_base_url,
            timeout_seconds=args.timeout_seconds,
            restart_managed_stack=args.restart_managed_stack,
            restart_vllm_container=args.restart_vllm_container,
        )
    )
    print("PHASE231 RUNTIME RECOVERY RELIABILITY REBASELINE SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print(
            "PHASE231 RUNTIME RECOVERY RELIABILITY REBASELINE ERRORS "
            + json.dumps(report["validation_errors"], sort_keys=True)
        )
        return 1
    print("PHASE231 RUNTIME RECOVERY RELIABILITY REBASELINE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
