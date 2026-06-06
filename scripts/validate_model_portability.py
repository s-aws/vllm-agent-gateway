#!/usr/bin/env python3
"""Run or classify the Phase 72 model portability gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.model_portability import (  # noqa: E402
    DEFAULT_MODEL_BASE_URL,
    ModelPortabilityConfig,
    run_model_portability,
)
from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--candidate-id", required=True, help="Stable label for the model candidate being evaluated.")
    parser.add_argument("--candidate-description", default="")
    parser.add_argument("--candidate-model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--acceptance-output-path", default=None)
    parser.add_argument("--acceptance-report-path", default=None)
    parser.add_argument("--python-executable", default=None)
    parser.add_argument("--skip-live-acceptance", action="store_true")
    parser.add_argument("--skip-model-probe", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_model_portability(
        ModelPortabilityConfig(
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
            acceptance_output_path=Path(args.acceptance_output_path) if args.acceptance_output_path else None,
            acceptance_report_path=Path(args.acceptance_report_path) if args.acceptance_report_path else None,
            python_executable=args.python_executable,
            skip_live_acceptance=args.skip_live_acceptance,
            skip_model_probe=args.skip_model_probe,
        )
    )
    print(f"MODEL PORTABILITY REPORT {report['report_path']}")
    print(
        "MODEL PORTABILITY SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "candidate_id": report["candidate"]["candidate_id"],
                "candidate_model_ids": report.get("candidate_model_probe", {}).get("model_ids", []),
                "acceptance_status": report.get("acceptance_report", {}).get("status"),
                "classification_summary": report.get("classification_summary", {}),
                "failure_count": len(report.get("classified_failures", [])),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print(
            "MODEL PORTABILITY FAILURES "
            + json.dumps(report.get("classified_failures", []), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("MODEL PORTABILITY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
