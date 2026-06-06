#!/usr/bin/env python3
"""Validate the external tester onboarding prompt pack."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.onboarding import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_ONBOARDING_PACK_PATH,
    DEFAULT_WORKSPACE,
    OnboardingValidationConfig,
    validate_external_tester_onboarding,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--pack-path", default=str(DEFAULT_ONBOARDING_PACK_PATH))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--live-anythingllm", action="store_true")
    parser.add_argument("--include-feedback", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get(args.api_key_env)
    report = validate_external_tester_onboarding(
        OnboardingValidationConfig(
            config_root=Path(args.config_root),
            pack_path=Path(args.pack_path),
            output_path=Path(args.output_path) if args.output_path else None,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            live_anythingllm=args.live_anythingllm,
            include_feedback=args.include_feedback,
            case_ids=tuple(args.case_ids or ()),
        ),
        api_key=api_key,
    )
    print(f"EXTERNAL TESTER ONBOARDING REPORT {report['report_path']}")
    print(
        "EXTERNAL TESTER ONBOARDING SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "case_count": report.get("summary", {}).get("case_count"),
                "live_status": report.get("summary", {}).get("live_status"),
                "live_case_count": report.get("summary", {}).get("live_case_count"),
                "feedback_count": report.get("summary", {}).get("feedback_count"),
                "live_error_count": report.get("summary", {}).get("live_error_count"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print(
            "EXTERNAL TESTER ONBOARDING FAILURES "
            + json.dumps(
                {
                    "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                    "live_errors": report.get("live", {}).get("errors"),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 1
    print("EXTERNAL TESTER ONBOARDING PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
