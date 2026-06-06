#!/usr/bin/env python3
"""Validate the skill regression tier catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.regression_tiers import (  # noqa: E402
    SkillRegressionTierConfig,
    validate_skill_regression_tiers,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--tier-path", default=None)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_skill_regression_tiers(
        SkillRegressionTierConfig(
            config_root=Path(args.config_root),
            tier_path=Path(args.tier_path) if args.tier_path else None,
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"SKILL REGRESSION TIERS REPORT {report['report_path']}")
    print(
        "SKILL REGRESSION TIERS SUMMARY "
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
        print("SKILL REGRESSION TIERS FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL REGRESSION TIERS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
