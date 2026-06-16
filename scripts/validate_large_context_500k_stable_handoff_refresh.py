#!/usr/bin/env python3
"""Validate Phase 277 500k stable handoff refresh."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.large_context_500k_stable_handoff_refresh import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PHASE276_REPORT_PATH,
    DEFAULT_POLICY_PATH,
    LargeContext500kStableHandoffRefreshConfig,
    validate_large_context_500k_stable_handoff_refresh,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--phase276-report-path", default=str(DEFAULT_PHASE276_REPORT_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--allow-missing-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_large_context_500k_stable_handoff_refresh(
        LargeContext500kStableHandoffRefreshConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            phase276_report_path=Path(args.phase276_report_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            require_artifacts=not args.allow_missing_artifacts,
        )
    )
    print(
        "PHASE277 LARGE CONTEXT 500K STABLE HANDOFF REFRESH SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"],
                "blocker_count": report["summary"]["blocker_count"],
                "phase276_status": report["summary"]["phase276_status"],
                "phase276_decision": report["summary"]["phase276_decision"],
                "candidate_estimated_project_tokens": report["summary"]["candidate_estimated_project_tokens"],
                "phase278_ready": report["summary"]["phase278_ready"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        return 1
    print("PHASE277 LARGE CONTEXT 500K STABLE HANDOFF REFRESH PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
