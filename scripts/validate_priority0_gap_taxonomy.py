#!/usr/bin/env python3
"""Validate Priority 0 comparison misses through the shared failure taxonomy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.baseline_corpus import DEFAULT_CORPUS_PATH  # noqa: E402
from vllm_agent_gateway.acceptance.priority0_gap_taxonomy import (  # noqa: E402
    Priority0GapTaxonomyConfig,
    run_priority0_gap_taxonomy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--corpus-path", default=str(DEFAULT_CORPUS_PATH))
    parser.add_argument("--output-path", default="runtime-state/priority0-gap-taxonomy/priority0-gap-taxonomy-report.json")
    parser.add_argument("--markdown-output-path", default=None)
    parser.set_defaults(require_artifacts=True)
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Require comparison artifacts. This is the default for stable Priority 0 proof.",
    )
    parser.add_argument(
        "--allow-missing-artifacts",
        action="store_false",
        dest="require_artifacts",
        help="Allow missing local runtime-state artifacts for clean-clone shape inspection only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_priority0_gap_taxonomy(
        Priority0GapTaxonomyConfig(
            config_root=Path(args.config_root),
            corpus_path=Path(args.corpus_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            require_artifacts=args.require_artifacts,
        )
    )
    summary = {
        "status": report["status"],
        "comparison_count": report.get("summary", {}).get("comparison_count"),
        "finding_count": report.get("summary", {}).get("finding_count"),
        "highest_severity": report.get("summary", {}).get("highest_severity"),
        "gap_class_counts": {
            key: value for key, value in report.get("summary", {}).get("gap_class_counts", {}).items() if value
        },
        "error_count": report.get("summary", {}).get("error_count"),
        "markdown_report_path": report.get("markdown_report_path"),
    }
    print(f"PRIORITY0 GAP TAXONOMY REPORT {report['report_path']}")
    print("PRIORITY0 GAP TAXONOMY SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PRIORITY0 GAP TAXONOMY FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PRIORITY0 GAP TAXONOMY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
