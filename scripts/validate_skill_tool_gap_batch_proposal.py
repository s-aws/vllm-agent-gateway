#!/usr/bin/env python3
"""Build and validate the Phase 161 skill/tool gap batch proposal report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.skill_tool_gap_batch_proposal import (  # noqa: E402
    DEFAULT_MARKDOWN_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_REPORT_PATH,
    SkillToolGapBatchProposalConfig,
    run_skill_tool_gap_batch_proposal,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_skill_tool_gap_batch_proposal(
        SkillToolGapBatchProposalConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    print("PHASE161 SKILL TOOL GAP BATCH PROPOSAL REPORT " + str(report.get("report_path")))
    print("PHASE161 SKILL TOOL GAP BATCH PROPOSAL SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("PHASE161 SKILL TOOL GAP BATCH PROPOSAL ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("PHASE161 SKILL TOOL GAP BATCH PROPOSAL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
