#!/usr/bin/env python3
"""Validate Phase 238 release-candidate PR/readiness packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.release_candidate_pr_readiness import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    ReleaseCandidatePrReadinessConfig,
    ReleaseCandidateReadinessStatus,
    run_release_candidate_pr_readiness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-report.json",
    )
    parser.add_argument(
        "--markdown-output-path",
        default="runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-packet.md",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_release_candidate_pr_readiness(
        ReleaseCandidatePrReadinessConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            policy_path=Path(args.policy_path),
        )
    )
    print(
        "RELEASE CANDIDATE PR READINESS "
        + json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"],
                "source": report["source"],
                "summary": report["summary"],
                "markdown_output_path": report["markdown_output_path"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != ReleaseCandidateReadinessStatus.PASSED.value:
        print("RELEASE CANDIDATE PR READINESS ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True))
        return 1
    print("RELEASE CANDIDATE PR READINESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
