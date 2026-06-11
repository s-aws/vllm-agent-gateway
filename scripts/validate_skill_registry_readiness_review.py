#!/usr/bin/env python3
"""Build and validate the Phase 193 skill registry readiness review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.skill_registry_readiness_review import (  # noqa: E402
    DEFAULT_COVERAGE_REPORT_PATH,
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_SCALE_REPORT_PATH,
    SkillRegistryReadinessConfig,
    run_skill_registry_readiness_review,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--scale-report-path", default=str(DEFAULT_SCALE_REPORT_PATH))
    parser.add_argument("--coverage-report-path", default=str(DEFAULT_COVERAGE_REPORT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_skill_registry_readiness_review(
        SkillRegistryReadinessConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            scale_report_path=Path(args.scale_report_path),
            coverage_report_path=Path(args.coverage_report_path),
        )
    )
    print(f"PHASE193 SKILL REGISTRY READINESS REVIEW REPORT {report['report_path']}")
    print("PHASE193 SKILL REGISTRY READINESS REVIEW SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PHASE193 SKILL REGISTRY READINESS REVIEW ERRORS " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE193 SKILL REGISTRY READINESS REVIEW PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
