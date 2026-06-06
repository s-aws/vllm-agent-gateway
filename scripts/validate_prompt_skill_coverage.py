#!/usr/bin/env python3
"""Validate the prompt-to-skill coverage registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.prompt_coverage import PromptCoverageConfig, validate_prompt_coverage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--coverage-path", default=None)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_prompt_coverage(
        PromptCoverageConfig(
            config_root=Path(args.config_root),
            coverage_path=Path(args.coverage_path) if args.coverage_path else None,
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"PROMPT SKILL COVERAGE REPORT {report['report_path']}")
    print(
        "PROMPT SKILL COVERAGE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("PROMPT SKILL COVERAGE FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PROMPT SKILL COVERAGE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
