#!/usr/bin/env python3
"""Validate the Phase 115 incremental implementation prompt and audit case catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.task_decomposition_quality import (  # noqa: E402
    DEFAULT_PHASE115_CASE_CATALOG,
    build_phase115_recursive_blind_testing_report,
    load_json_object,
    validate_phase115_case_catalog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--catalog-path", default=str(DEFAULT_PHASE115_CASE_CATALOG))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--recursive-report-output-path", default=None)
    parser.add_argument(
        "--live-report-path",
        default="runtime-state/task-decomposition/phase115-incremental-implementation-live.json",
        help="Evidence reference for the Phase 115 live validation report.",
    )
    parser.add_argument(
        "--engineering-tenet-report-path",
        default="runtime-state/engineering-tenet-coverage/phase115-current.json",
        help="Evidence reference for the engineering-tenet coverage report.",
    )
    parser.add_argument(
        "--focused-regression-ref",
        default="python -m pytest tests/regression/test_task_decomposition.py -q -> 43 passed",
    )
    parser.add_argument(
        "--adjacent-regression-ref",
        default=(
            "python -m pytest tests/regression/test_task_decomposition.py "
            "tests/regression/test_chat_response_contract.py tests/regression/test_v1_acceptance.py "
            "tests/regression/test_engineering_tenet_coverage.py -q -> 66 passed"
        ),
    )
    parser.add_argument("--full-regression-ref", default="")
    parser.add_argument(
        "--recursive-validation-ref",
        default="runtime-state/recursive-blind-testing/phase115-incremental-implementation-recursive-validation.json",
    )
    parser.add_argument("--final-audit-ref", default="contextless subagent final audit -> score pending")
    parser.add_argument("--final-audit-score", type=int, default=85)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    catalog_path = Path(args.catalog_path)
    if not catalog_path.is_absolute():
        catalog_path = config_root / catalog_path
    catalog = load_json_object(catalog_path)
    report = validate_phase115_case_catalog(catalog)
    report["catalog_path"] = str(catalog_path)
    if args.output_path:
        output_path = Path(args.output_path)
        if not output_path.is_absolute():
            output_path = config_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.recursive_report_output_path:
        recursive_output_path = Path(args.recursive_report_output_path)
        if not recursive_output_path.is_absolute():
            recursive_output_path = config_root / recursive_output_path
        full_regression_ref = args.full_regression_ref.strip()
        if not full_regression_ref:
            raise RuntimeError("--full-regression-ref is required when --recursive-report-output-path is supplied")
        recursive_report = build_phase115_recursive_blind_testing_report(
            catalog,
            catalog_report_path=str(Path(args.output_path or "").as_posix()) if args.output_path else str(catalog_path),
            live_report_path=args.live_report_path,
            engineering_tenet_report_path=args.engineering_tenet_report_path,
            focused_regression_ref=args.focused_regression_ref,
            adjacent_regression_ref=args.adjacent_regression_ref,
            full_regression_ref=full_regression_ref,
            recursive_validation_ref=args.recursive_validation_ref,
            final_audit_ref=args.final_audit_ref,
            final_audit_score=args.final_audit_score,
        )
        recursive_output_path.parent.mkdir(parents=True, exist_ok=True)
        recursive_output_path.write_text(
            json.dumps(recursive_report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print("INCREMENTAL IMPLEMENTATION PHASE115 CASES " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
