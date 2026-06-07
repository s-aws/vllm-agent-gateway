#!/usr/bin/env python3
"""Validate Phase 94 runtime skill-selection hardening."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.skill_selection_hardening import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    SkillSelectionHardeningConfig,
    validate_skill_selection_hardening,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--cases-path", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--repeat-count", type=int, default=None)
    parser.add_argument("--skip-direct", action="store_true")
    parser.add_argument("--live-gateway", action="store_true")
    parser.add_argument("--live-anythingllm", action="store_true")
    parser.add_argument("--anythingllm-repeat-count", type=int, default=1)
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_skill_selection_hardening(
        SkillSelectionHardeningConfig(
            config_root=Path(args.config_root),
            cases_path=Path(args.cases_path) if args.cases_path else Path("runtime") / "skill_selection_hardening_cases.json",
            output_path=Path(args.output_path) if args.output_path else None,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            repeat_count=args.repeat_count,
            include_direct=not args.skip_direct,
            include_gateway=args.live_gateway,
            include_anythingllm=args.live_anythingllm,
            anythingllm_repeat_count=args.anythingllm_repeat_count,
            model_base_url=args.model_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(f"SKILL SELECTION HARDENING REPORT {report['report_path']}")
    print(
        "SKILL SELECTION HARDENING SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "case_count": report.get("summary", {}).get("case_count"),
                "target_roots": report.get("target_roots"),
                "repeat_count": report.get("summary", {}).get("repeat_count"),
                "direct_enabled": report.get("summary", {}).get("direct_enabled"),
                "gateway_enabled": report.get("summary", {}).get("gateway_enabled"),
                "anythingllm_enabled": report.get("summary", {}).get("anythingllm_enabled"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("SKILL SELECTION HARDENING FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL SELECTION HARDENING PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
