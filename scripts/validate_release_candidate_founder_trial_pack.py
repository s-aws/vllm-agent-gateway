#!/usr/bin/env python3
"""Validate the Phase 195 release-candidate founder trial pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.release_candidate_founder_trial_pack import (  # noqa: E402
    FounderTrialPackConfig,
    resolve_path,
    run_founder_trial_pack,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=None)
    parser.add_argument("--pack-path", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    parser.add_argument(
        "--require-proof-artifacts",
        dest="require_proof_artifacts",
        action="store_true",
        default=True,
        help="Require Phase 191-194 proof artifacts to exist and pass. Enabled by default.",
    )
    parser.add_argument(
        "--skip-proof-artifacts",
        dest="require_proof_artifacts",
        action="store_false",
        help="Developer-only inspection mode. The report will fail the release policy when proof artifacts are required.",
    )
    parser.add_argument(
        "--validate-fixture-state",
        action="store_true",
        help="Check live frozen fixture roots for release-trial readiness.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = FounderTrialPackConfig(
        config_root=Path(args.config_root),
        policy_path=Path(args.policy_path) if args.policy_path else FounderTrialPackConfig.policy_path,
        pack_path=Path(args.pack_path) if args.pack_path else FounderTrialPackConfig.pack_path,
        output_path=Path(args.output_path) if args.output_path else FounderTrialPackConfig.output_path,
        markdown_output_path=Path(args.markdown_output_path)
        if args.markdown_output_path
        else FounderTrialPackConfig.markdown_output_path,
        require_proof_artifacts=args.require_proof_artifacts,
        validate_fixture_state=args.validate_fixture_state,
    )
    report = run_founder_trial_pack(config)
    print(f"PHASE195 RELEASE CANDIDATE FOUNDER TRIAL PACK REPORT {resolve_path(Path(config.config_root), config.output_path).resolve()}")
    print(
        "PHASE195 RELEASE CANDIDATE FOUNDER TRIAL PACK SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != "passed":
        print("PHASE195 RELEASE CANDIDATE FOUNDER TRIAL PACK FAIL " + json.dumps(report["validation_errors"], ensure_ascii=True))
        return 1
    print("PHASE195 RELEASE CANDIDATE FOUNDER TRIAL PACK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
