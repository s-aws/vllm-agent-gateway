#!/usr/bin/env python3
"""Validate Phase 129 skill/tool coverage gap governance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.skill_tool_coverage_gap import (  # noqa: E402
    DEFAULT_CAPABILITY_BACKLOG_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_PRIORITY0_GAP_TAXONOMY_PATH,
    DEFAULT_PROMPT_COVERAGE_PATH,
    DEFAULT_PROMPT_TIGHTENING_REPORT_PATH,
    SkillToolCoverageGapConfig,
    run_skill_tool_coverage_gap_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--priority0-gap-taxonomy-path", default=str(DEFAULT_PRIORITY0_GAP_TAXONOMY_PATH))
    parser.add_argument("--prompt-tightening-report-path", default=str(DEFAULT_PROMPT_TIGHTENING_REPORT_PATH))
    parser.add_argument("--capability-backlog-path", default=str(DEFAULT_CAPABILITY_BACKLOG_PATH))
    parser.add_argument("--prompt-coverage-path", default=str(DEFAULT_PROMPT_COVERAGE_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/skill-tool-coverage-gap/phase129/skill-tool-coverage-gap-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_skill_tool_coverage_gap_gate(
        SkillToolCoverageGapConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            priority0_gap_taxonomy_path=Path(args.priority0_gap_taxonomy_path),
            prompt_tightening_report_path=Path(args.prompt_tightening_report_path),
            capability_backlog_path=Path(args.capability_backlog_path),
            prompt_coverage_path=Path(args.prompt_coverage_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("SKILL TOOL COVERAGE GAP " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("SKILL TOOL COVERAGE GAP ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL TOOL COVERAGE GAP PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
