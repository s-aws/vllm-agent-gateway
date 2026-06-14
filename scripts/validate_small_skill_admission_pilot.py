#!/usr/bin/env python3
"""Validate Phase 230 small skill admission pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.small_skill_admission_pilot import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    SmallSkillAdmissionPilotConfig,
    validate_small_skill_admission_pilot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--live-report-path", default=None)
    parser.add_argument("--allow-missing-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_small_skill_admission_pilot(
        SmallSkillAdmissionPilotConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            require_artifacts=not args.allow_missing_artifacts,
            live_report_path=Path(args.live_report_path) if args.live_report_path else None,
        )
    )
    print("PHASE230 SMALL SKILL ADMISSION PILOT SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PHASE230 SMALL SKILL ADMISSION PILOT FAIL")
        return 1
    print("PHASE230 SMALL SKILL ADMISSION PILOT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
