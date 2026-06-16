#!/usr/bin/env python3
"""Validate Phase 274 targeted 500k answer-quality repair closure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.large_context_500k_answer_quality_repair import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    LargeContext500kAnswerQualityRepairConfig,
    LargeContext500kAnswerQualityRepairStatus,
    validate_large_context_500k_answer_quality_repair,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_large_context_500k_answer_quality_repair(
        LargeContext500kAnswerQualityRepairConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
        )
    )
    print(
        "PHASE274 LARGE CONTEXT 500K ANSWER QUALITY REPAIR SUMMARY "
        + json.dumps(report.get("summary", {}), ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != LargeContext500kAnswerQualityRepairStatus.PASSED.value:
        print("PHASE274 LARGE CONTEXT 500K ANSWER QUALITY REPAIR FAIL")
        print("PHASE274 ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE274 LARGE CONTEXT 500K ANSWER QUALITY REPAIR PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
