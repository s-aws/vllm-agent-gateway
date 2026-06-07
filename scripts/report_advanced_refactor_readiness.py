#!/usr/bin/env python3
"""Generate the Phase 105 advanced-refactor readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.advanced_refactor_readiness import (  # noqa: E402
    DEFAULT_GATE_REPORT_PATH,
    AdvancedRefactorReadinessConfig,
    run_advanced_refactor_readiness,
)


def parse_path_list(values: list[str]) -> tuple[Path, ...]:
    return tuple(Path(item) for item in values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument(
        "--implementation-prep-report",
        action="append",
        default=[],
        help="Phase 96 implementation-prep report. May be passed multiple times.",
    )
    parser.add_argument(
        "--approval-continuation-report",
        action="append",
        default=[],
        help="Phase 97 approval-continuation report. May be passed multiple times.",
    )
    parser.add_argument(
        "--disposable-apply-report",
        action="append",
        default=[],
        help="Phase 98 disposable-apply report. May be passed multiple times.",
    )
    parser.add_argument("--multi-repo-report", default=None)
    parser.add_argument("--task-decomposition-report", default=None)
    parser.add_argument("--eval-repair-loop-report", default=None)
    parser.add_argument("--model-policy-path", default=None)
    parser.add_argument(
        "--advanced-refactor-deferred-plan",
        action="append",
        default=[],
        help="Optional deferred advanced-refactor task-decomposition artifact. May be passed multiple times.",
    )
    parser.add_argument(
        "--controller-artifact-root",
        action="append",
        default=[],
        help="Optional controller artifact root to search for deferred advanced-refactor task-decomposition artifacts.",
    )
    parser.add_argument(
        "--target-root",
        action="append",
        default=[],
        help="Expected frozen target root. Defaults to both frozen Coinbase fixtures.",
    )
    parser.add_argument("--output-path", default=str(DEFAULT_GATE_REPORT_PATH))
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_kwargs: dict[str, object] = {
        "config_root": Path(args.config_root),
        "output_path": Path(args.output_path) if args.output_path else None,
        "markdown_output_path": Path(args.markdown_output_path) if args.markdown_output_path else None,
    }
    if args.implementation_prep_report:
        config_kwargs["implementation_prep_reports"] = parse_path_list(args.implementation_prep_report)
    if args.approval_continuation_report:
        config_kwargs["approval_continuation_reports"] = parse_path_list(args.approval_continuation_report)
    if args.disposable_apply_report:
        config_kwargs["disposable_apply_reports"] = parse_path_list(args.disposable_apply_report)
    if args.multi_repo_report:
        config_kwargs["multi_repo_report"] = Path(args.multi_repo_report)
    if args.task_decomposition_report:
        config_kwargs["task_decomposition_report"] = Path(args.task_decomposition_report)
    if args.eval_repair_loop_report:
        config_kwargs["eval_repair_loop_report"] = Path(args.eval_repair_loop_report)
    if args.model_policy_path:
        config_kwargs["model_policy_path"] = Path(args.model_policy_path)
    if args.advanced_refactor_deferred_plan:
        config_kwargs["advanced_refactor_deferred_plan_paths"] = parse_path_list(args.advanced_refactor_deferred_plan)
    if args.controller_artifact_root:
        config_kwargs["controller_artifact_roots"] = parse_path_list(args.controller_artifact_root)
    if args.target_root:
        config_kwargs["target_roots"] = tuple(args.target_root)

    report = run_advanced_refactor_readiness(AdvancedRefactorReadinessConfig(**config_kwargs))
    summary = {
        "status": report.get("status"),
        "readiness_status": report.get("readiness_status"),
        "passed_prerequisite_count": report.get("summary", {}).get("passed_prerequisite_count"),
        "failed_prerequisite_count": report.get("summary", {}).get("failed_prerequisite_count"),
        "missing_prerequisite_count": report.get("summary", {}).get("missing_prerequisite_count"),
        "pilot_prompt_set_status": report.get("pilot_prompt_set", {}).get("status"),
        "stable_promotion_status": report.get("stable_promotion", {}).get("status"),
        "validation_error_count": len(report.get("validation_errors", [])),
        "markdown_report_path": report.get("markdown_report_path"),
    }
    print(f"ADVANCED REFACTOR READINESS REPORT {report['report_path']}")
    print("ADVANCED REFACTOR READINESS SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print(
            "ADVANCED REFACTOR READINESS FAILURES "
            + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("ADVANCED REFACTOR READINESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
