#!/usr/bin/env python3
"""Generate a failure taxonomy report from existing validation artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.failure_taxonomy import FailureTaxonomyConfig, run_failure_taxonomy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--report", action="append", dest="reports", required=True, help="Validation report path.")
    parser.add_argument("--label", action="append", dest="labels", default=[], help="Optional label for each report.")
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_paths = tuple(Path(item) for item in args.reports)
    labels = tuple(args.labels or ())
    if labels and len(labels) != len(report_paths):
        print(
            "FAILURE TAXONOMY FAILURES "
            + json.dumps(["--label count must match --report count when labels are provided"], ensure_ascii=True),
        )
        return 2
    report = run_failure_taxonomy(
        FailureTaxonomyConfig(
            config_root=Path(args.config_root),
            report_paths=report_paths,
            labels=labels,
            output_path=Path(args.output_path) if args.output_path else None,
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    summary = {
        "status": report["status"],
        "finding_count": report.get("summary", {}).get("finding_count"),
        "highest_severity": report.get("summary", {}).get("highest_severity"),
        "category_counts": {
            key: value for key, value in report.get("summary", {}).get("category_counts", {}).items() if value
        },
        "markdown_report_path": report.get("markdown_report_path"),
    }
    print(f"FAILURE TAXONOMY REPORT {report['report_path']}")
    print("FAILURE TAXONOMY SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("FAILURE TAXONOMY FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("FAILURE TAXONOMY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
