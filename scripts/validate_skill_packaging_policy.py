#!/usr/bin/env python3
"""Validate the project skill-pack packaging policy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.packaging_policy import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    SkillPackPolicyConfig,
    run_skill_packaging_policy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_skill_packaging_policy(
        SkillPackPolicyConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"SKILL PACKAGING POLICY REPORT {report['report_path']}")
    print(
        "SKILL PACKAGING POLICY SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "policy_id": report.get("policy_id"),
                "policy_version": report.get("policy_version"),
                "error_count": len(report.get("errors", [])),
                "summary": report.get("summary", {}),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("SKILL PACKAGING POLICY FAILURES " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL PACKAGING POLICY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
