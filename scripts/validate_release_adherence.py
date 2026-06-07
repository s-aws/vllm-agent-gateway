#!/usr/bin/env python3
"""Run the consolidated current-local-model release-adherence gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.release_adherence import (  # noqa: E402
    ReleaseAdherenceConfig,
    ReleaseAdherenceStatus,
    run_release_adherence,
)
from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--candidate-id", default="current-localhost-model")
    parser.add_argument("--candidate-description", default="Current localhost model behind the workflow-router gateway")
    parser.add_argument("--candidate-model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--command-timeout-seconds", type=int, default=3600)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    parser.add_argument("--python-executable", default=None)
    parser.add_argument("--ui-dist-root", default=None)
    parser.add_argument("--app-asar-path", default=None)
    parser.add_argument("--extract-root", default=None)
    parser.add_argument("--refresh-extract", action="store_true")
    parser.add_argument("--npx-command", default=None)
    parser.add_argument("--browser-channel", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_release_adherence(
        ReleaseAdherenceConfig(
            config_root=Path(args.config_root),
            candidate_id=args.candidate_id,
            candidate_description=args.candidate_description,
            candidate_model_base_url=args.candidate_model_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            timeout_seconds=args.timeout_seconds,
            command_timeout_seconds=args.command_timeout_seconds,
            output_path=Path(args.output_path) if args.output_path else None,
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            python_executable=args.python_executable,
            ui_dist_root=Path(args.ui_dist_root) if args.ui_dist_root else None,
            app_asar_path=Path(args.app_asar_path) if args.app_asar_path else None,
            extract_root=Path(args.extract_root) if args.extract_root else None,
            refresh_extract=args.refresh_extract,
            npx_command=args.npx_command,
            browser_channel=args.browser_channel,
        )
    )
    print(f"RELEASE ADHERENCE REPORT {report['report_path']}")
    print(f"RELEASE ADHERENCE MARKDOWN {report['markdown_report_path']}")
    print(
        "RELEASE ADHERENCE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "readiness_status": report["readiness_status"],
                "candidate_id": report.get("candidate", {}).get("candidate_id"),
                "model_ids": report.get("summary", {}).get("acceptance", {}).get("model_ids"),
                "blocker_count": report.get("summary", {}).get("finding_counts", {}).get("by_severity", {}).get("blocker"),
                "warning_count": report.get("summary", {}).get("finding_counts", {}).get("by_severity", {}).get("warning"),
                "latency_measured": report.get("summary", {}).get("latency", {}).get("latency_measured"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != ReleaseAdherenceStatus.PASSED.value:
        print("RELEASE ADHERENCE FINDINGS " + json.dumps(report.get("findings", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("RELEASE ADHERENCE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
