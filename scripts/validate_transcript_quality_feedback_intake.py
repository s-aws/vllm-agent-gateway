#!/usr/bin/env python3
"""Build and validate the Phase 158 transcript quality feedback intake report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.transcript_quality_feedback_intake import (  # noqa: E402
    DEFAULT_MARKDOWN_PATH,
    DEFAULT_PHASE157_REPORT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_REPORT_PATH,
    TranscriptQualityFeedbackIntakeConfig,
    run_transcript_quality_feedback_intake,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--phase157-report-path", default=str(DEFAULT_PHASE157_REPORT_PATH))
    parser.add_argument("--founder-notes-path")
    parser.add_argument("--output-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_transcript_quality_feedback_intake(
        TranscriptQualityFeedbackIntakeConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            phase157_report_path=Path(args.phase157_report_path),
            founder_notes_path=Path(args.founder_notes_path) if args.founder_notes_path else None,
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    print("PHASE158 TRANSCRIPT QUALITY FEEDBACK INTAKE REPORT " + str(report.get("report_path")))
    print("PHASE158 TRANSCRIPT QUALITY FEEDBACK INTAKE SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print(
            "PHASE158 TRANSCRIPT QUALITY FEEDBACK INTAKE ERRORS "
            + json.dumps(report["validation_errors"], sort_keys=True)
        )
        return 1
    print("PHASE158 TRANSCRIPT QUALITY FEEDBACK INTAKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
