#!/usr/bin/env python3
"""Validate the project skill eval catalog and optionally run mapped live suites."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.batches import build_skill_batch_report  # noqa: E402
from vllm_agent_gateway.skills.evals import run_skill_eval_catalog  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--batch-file", default=None, help="Validate a proposed skill batch manifest instead of the catalog.")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument(
        "--live-target",
        choices=["metadata", "gateway", "gateway_and_anythingllm"],
        default="metadata",
        help="metadata validates offline; gateway modes execute only when --execute-live is passed.",
    )
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--workflow-router-gateway-base-url", default="http://127.0.0.1:8500/v1")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default="my-workspace")
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_file:
        report = build_skill_batch_report(
            Path(args.config_root),
            Path(args.batch_file),
            output_path=Path(args.output_path) if args.output_path else None,
        )
        print(f"SKILL BATCH REPORT {report['report_path']}")
        print(
            "SKILL BATCH SUMMARY "
            + json.dumps(
                {
                    "status": report["status"],
                    "batch_id": report["batch_id"],
                    "skill_count": report["summary"]["skill_count"],
                    "eval_case_count": report["summary"]["eval_case_count"],
                    "route_key_count": report["summary"]["route_key_count"],
                    "error_count": len(report["errors"]),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        if report["status"] != "passed":
            print("SKILL BATCH FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
            return 1
        print("SKILL BATCH PASS")
        return 0

    report = run_skill_eval_catalog(
        Path(args.config_root),
        output_path=Path(args.output_path) if args.output_path else None,
        case_ids=args.case_ids,
        live_target=args.live_target,
        execute_live=args.execute_live,
        target_roots=args.target_roots,
        workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
        anythingllm_api_base_url=args.anythingllm_api_base_url,
        workspace=args.workspace,
        api_key_env=args.api_key_env,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"SKILL EVAL REPORT {report['report_path']}")
    print("SKILL EVAL SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report.get("live_suite_runs"):
        print("SKILL EVAL LIVE SUITES " + json.dumps(report["live_suite_runs"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("SKILL EVAL FAILURES " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL EVAL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
