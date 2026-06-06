#!/usr/bin/env python3
"""Generate an advisory model capability profile from a model portability report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.model_capability_profile import (  # noqa: E402
    ModelCapabilityProfileConfig,
    run_model_capability_profile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--portability-report-path", required=True)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = run_model_capability_profile(
        ModelCapabilityProfileConfig(
            config_root=Path(args.config_root),
            portability_report_path=Path(args.portability_report_path),
            output_path=Path(args.output_path) if args.output_path else None,
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    print(f"MODEL CAPABILITY PROFILE REPORT {profile['report_path']}")
    print(f"MODEL CAPABILITY PROFILE MARKDOWN {profile['markdown_report_path']}")
    print(
        "MODEL CAPABILITY PROFILE SUMMARY "
        + json.dumps(
            {
                "status": profile["status"],
                "candidate_id": profile.get("candidate", {}).get("candidate_id"),
                "capabilities": {
                    key: value.get("status")
                    for key, value in profile.get("capabilities", {}).items()
                    if isinstance(value, dict)
                },
                "task_policy": {
                    key: value.get("status")
                    for key, value in profile.get("task_policy", {}).items()
                    if isinstance(value, dict)
                },
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    print("MODEL CAPABILITY PROFILE GENERATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
