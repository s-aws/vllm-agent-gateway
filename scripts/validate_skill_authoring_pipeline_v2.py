#!/usr/bin/env python3
"""Validate the Phase 194 skill authoring pipeline V2 candidate gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.skill_authoring_pipeline_v2 import (  # noqa: E402
    SkillAuthoringPipelineV2Config,
    run_skill_authoring_pipeline_v2,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=None)
    parser.add_argument("--candidate-root", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    parser.add_argument("--batch-report-path", default=None)
    parser.add_argument("--phase193-report-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = SkillAuthoringPipelineV2Config(
        config_root=Path(args.config_root),
        policy_path=Path(args.policy_path) if args.policy_path else SkillAuthoringPipelineV2Config.policy_path,
        candidate_root=Path(args.candidate_root) if args.candidate_root else SkillAuthoringPipelineV2Config.candidate_root,
        output_path=Path(args.output_path) if args.output_path else SkillAuthoringPipelineV2Config.output_path,
        markdown_output_path=Path(args.markdown_output_path)
        if args.markdown_output_path
        else SkillAuthoringPipelineV2Config.markdown_output_path,
        batch_report_path=Path(args.batch_report_path) if args.batch_report_path else SkillAuthoringPipelineV2Config.batch_report_path,
        phase193_report_path=Path(args.phase193_report_path) if args.phase193_report_path else SkillAuthoringPipelineV2Config.phase193_report_path,
    )
    report = run_skill_authoring_pipeline_v2(config)
    print(f"PHASE194 SKILL AUTHORING PIPELINE V2 REPORT {Path(config.output_path).resolve()}")
    print(
        "PHASE194 SKILL AUTHORING PIPELINE V2 SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != "passed":
        print("PHASE194 SKILL AUTHORING PIPELINE V2 FAIL " + json.dumps(report["validation_errors"], ensure_ascii=True))
        return 1
    print("PHASE194 SKILL AUTHORING PIPELINE V2 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
