#!/usr/bin/env python3
"""Validate the local-model engineering tenet coverage matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.engineering_tenet_coverage import (  # noqa: E402
    DEFAULT_MATRIX_PATH,
    EngineeringTenetCoverageConfig,
    run_engineering_tenet_coverage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--matrix-path", default=str(DEFAULT_MATRIX_PATH))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_engineering_tenet_coverage(
        EngineeringTenetCoverageConfig(
            config_root=Path(args.config_root),
            matrix_path=Path(args.matrix_path),
            output_path=Path(args.output_path) if args.output_path else None,
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    summary = {
        "status": report["status"],
        "tenet_count": report.get("summary", {}).get("tenet_count"),
        "expected_tenet_count": report.get("summary", {}).get("expected_tenet_count"),
        "status_counts": report.get("summary", {}).get("status_counts"),
        "error_count": len(report.get("errors", [])),
        "markdown_report_path": report.get("markdown_report_path"),
    }
    print(f"ENGINEERING TENET COVERAGE REPORT {report['report_path']}")
    print("ENGINEERING TENET COVERAGE SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("ENGINEERING TENET COVERAGE FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("ENGINEERING TENET COVERAGE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
