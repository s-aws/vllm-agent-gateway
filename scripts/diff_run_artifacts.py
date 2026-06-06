#!/usr/bin/env python3
"""Compare two V1, founder-field, or model-portability run artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.run_artifact_diff import RunArtifactDiffConfig, run_artifact_diff  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--left-report", required=True)
    parser.add_argument("--right-report", required=True)
    parser.add_argument("--left-label", default="left")
    parser.add_argument("--right-label", default="right")
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_artifact_diff(
        RunArtifactDiffConfig(
            config_root=Path(args.config_root),
            left_report_path=Path(args.left_report),
            right_report_path=Path(args.right_report),
            left_label=args.left_label,
            right_label=args.right_label,
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    diff = report.get("diff", {})
    summary = {
        "status": report["status"],
        "left_label": report["left"]["label"],
        "right_label": report["right"]["label"],
        "left_kind": report["left"].get("summary", {}).get("kind"),
        "right_kind": report["right"].get("summary", {}).get("kind"),
        "status_changed": diff.get("status_changed"),
        "semantic_misses_added": diff.get("semantic_miss_changes", {}).get("added", []),
        "suite_status_change_count": diff.get("suite_status_changes", {}).get("changed_count", 0),
        "fixture_state_change_count": len(diff.get("fixture_state_changes", [])),
    }
    print(f"RUN ARTIFACT DIFF REPORT {report['report_path']}")
    print("RUN ARTIFACT DIFF SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("RUN ARTIFACT DIFF FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("RUN ARTIFACT DIFF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
