#!/usr/bin/env python3
"""Validate EIG-2 actor and scope breadth fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig2_actor_scope_breadth import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIG2ActorScopeBreadthConfig,
    run_eig2_actor_scope_breadth_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig2_actor_scope_breadth_validation(
        EIG2ActorScopeBreadthConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"EIG2 ACTOR SCOPE BREADTH REPORT {report['report_path']}")
    print(
        "EIG2 ACTOR SCOPE BREADTH SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "operation_scope_assignment_count": report.get("summary", {}).get("operation_scope_assignment_count"),
                "actor_scope_case_count": report.get("summary", {}).get("actor_scope_case_count"),
                "actor_context_negative_case_count": report.get("summary", {}).get("actor_context_negative_case_count"),
                "read_without_write_allowed": report.get("summary", {}).get("read_without_write_allowed"),
                "write_without_read_allowed": report.get("summary", {}).get("write_without_read_allowed"),
                "cross_connector_scope_denied": report.get("summary", {}).get("cross_connector_scope_denied"),
                "scope_denials_have_recovery": report.get("summary", {}).get("scope_denials_have_recovery"),
                "validation_error_count": report.get("summary", {}).get("validation_error_count"),
                "phase294_ready": report.get("summary", {}).get("phase294_ready"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EIG2 ACTOR SCOPE BREADTH FAILURES " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG2 ACTOR SCOPE BREADTH PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
