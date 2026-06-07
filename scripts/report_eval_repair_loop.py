#!/usr/bin/env python3
"""Generate Phase 104 eval-driven repair recommendations from failed artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eval_repair_loop import EvalRepairLoopConfig, run_eval_repair_loop  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument(
        "--failure-taxonomy-report",
        action="append",
        dest="failure_taxonomy_reports",
        default=[],
        help="failure_taxonomy_report path to convert into repair recommendations.",
    )
    parser.add_argument(
        "--recursive-report",
        action="append",
        dest="recursive_reports",
        default=[],
        help="recursive_blind_testing_report path to convert into repair recommendations.",
    )
    parser.add_argument("--target-prompt-case-id", default="")
    parser.add_argument("--holdout-prompt-case-id", default="")
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eval_repair_loop(
        EvalRepairLoopConfig(
            config_root=Path(args.config_root),
            failure_taxonomy_report_paths=tuple(Path(item) for item in args.failure_taxonomy_reports),
            recursive_report_paths=tuple(Path(item) for item in args.recursive_reports),
            target_prompt_case_id=args.target_prompt_case_id,
            holdout_prompt_case_id=args.holdout_prompt_case_id,
            output_path=Path(args.output_path) if args.output_path else None,
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    summary = {
        "status": report["status"],
        "source_finding_count": report.get("summary", {}).get("source_finding_count"),
        "recommendation_count": report.get("summary", {}).get("recommendation_count"),
        "repair_category_counts": {
            key: value for key, value in report.get("summary", {}).get("repair_category_counts", {}).items() if value
        },
        "blocking_error_count": len(report.get("blocking_errors", [])),
        "validation_error_count": len(report.get("validation_errors", [])),
        "markdown_report_path": report.get("markdown_report_path"),
    }
    print(f"EVAL REPAIR LOOP REPORT {report['report_path']}")
    print("EVAL REPAIR LOOP SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print(
            "EVAL REPAIR LOOP FAILURES "
            + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("EVAL REPAIR LOOP PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
