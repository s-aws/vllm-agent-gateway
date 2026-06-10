#!/usr/bin/env python3
"""Run the Phase 127 fresh local-model drift gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_task_decomposition_live import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONFIG_ROOT,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)
from vllm_agent_gateway.acceptance.fresh_local_model_drift import (  # noqa: E402
    DEFAULT_BASELINE_CORPUS_PATH,
    DEFAULT_CATALOG_PATH,
    DEFAULT_OUTPUT_DIR,
    DriftSeverity,
    FreshLocalModelDriftStatus,
    artifact_hash,
    dict_value,
    expected_case_targets_for_family,
    minimum_route_score,
    object_list,
    read_json_object,
    resolve_path,
    source_hashes_for_family,
    stable_baseline_entries,
    string_list,
    utc_timestamp,
    validate_fresh_local_model_drift_catalog,
    validate_fresh_local_model_drift_report,
    write_json,
)


def tail_text(value: str, *, limit: int = 4000) -> str:
    return value[-limit:] if len(value) > limit else value


def run_command(argv: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "argv": argv,
            "returncode": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": tail_text(completed.stdout),
            "stderr_tail": tail_text(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": argv,
            "returncode": -9,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": tail_text(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr_tail": f"command timed out after {timeout_seconds} seconds",
        }


def unlink_existing(path: Path) -> None:
    if path.is_file():
        path.unlink()


def local_eval_command(args: argparse.Namespace, family: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        str(family["run_script"]),
        "--config-root",
        args.config_root,
        "--cases-path",
        str(family["cases_path"]),
        "--baselines-path",
        str(family["baselines_path"]),
        "--workflow-router-gateway-base-url",
        args.workflow_router_gateway_base_url,
        "--anythingllm-api-base-url",
        args.anythingllm_api_base_url,
        "--workspace",
        args.workspace,
        "--api-key-env",
        args.api_key_env,
        "--output-path",
        str(family["fresh_local_eval_path"]),
        "--timeout-seconds",
        str(args.timeout_seconds),
    ]
    for case_id in string_list(family.get("case_ids")):
        command.extend(["--case-id", case_id])
    return command


def comparison_command(family: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        str(family["compare_script"]),
        "--baselines-path",
        str(family["baselines_path"]),
        "--output-path",
        str(family["fresh_comparison_path"]),
    ]
    if str(family.get("family_id")) == "phase119_delivery_mentorship":
        command.extend(["--eval-path", str(family["fresh_local_eval_path"])])
    else:
        command.extend(
            [
                "--cases-path",
                str(family["cases_path"]),
                "--local-eval-path",
                str(family["fresh_local_eval_path"]),
            ]
        )
    return command


def drift_severity_for_family(min_score: int | None, prior_min_score: object, comparison_status: object) -> DriftSeverity:
    if comparison_status != FreshLocalModelDriftStatus.PASSED.value or min_score is None or not isinstance(prior_min_score, int):
        return DriftSeverity.FAILED
    if min_score < prior_min_score:
        return DriftSeverity.WATCH
    return DriftSeverity.NONE


def family_result(
    *,
    args: argparse.Namespace,
    config_root: Path,
    family: dict[str, Any],
    baseline_entry: dict[str, Any],
) -> dict[str, Any]:
    local_eval_path = resolve_path(config_root, str(family["fresh_local_eval_path"]))
    comparison_path = resolve_path(config_root, str(family["fresh_comparison_path"]))
    unlink_existing(local_eval_path)
    unlink_existing(comparison_path)

    expected_count = int(family.get("expected_response_count") or 0)
    command_timeout = max(args.command_timeout_seconds, args.timeout_seconds * max(2, expected_count))
    local_command = local_eval_command(args, family)
    local_command_result = run_command(local_command, cwd=config_root, timeout_seconds=command_timeout)

    if local_command_result["returncode"] == 0 and local_eval_path.is_file():
        compare_command = comparison_command(family)
        comparison_command_result = run_command(compare_command, cwd=config_root, timeout_seconds=args.command_timeout_seconds)
    else:
        compare_command = comparison_command(family)
        comparison_command_result = {
            "argv": compare_command,
            "returncode": -1,
            "duration_seconds": 0,
            "stdout_tail": "",
            "stderr_tail": "comparison skipped because fresh local eval failed or was not written",
        }

    comparison = read_json_object(comparison_path) if comparison_path.is_file() else {}
    local_eval = read_json_object(local_eval_path) if local_eval_path.is_file() else {}
    min_score = minimum_route_score(comparison) if comparison else None
    prior_comparison = dict_value(baseline_entry.get("comparison"))
    drift_severity = drift_severity_for_family(min_score, prior_comparison.get("minimum_route_score"), comparison.get("status"))

    commands_passed = local_command_result["returncode"] == 0 and comparison_command_result["returncode"] == 0
    family_passed = (
        commands_passed
        and comparison.get("status") == FreshLocalModelDriftStatus.PASSED.value
        and comparison.get("response_count") == expected_count
        and comparison.get("passed_response_count") == expected_count
        and comparison.get("critical_finding_count") == 0
        and comparison.get("high_finding_count") == 0
        and not dict_value(comparison.get("gap_categories"))
        and drift_severity == DriftSeverity.NONE
    )

    local_eval_summary = {
        key: value
        for key, value in local_eval.items()
        if key
        in {
            "kind",
            "schema_version",
            "status",
            "created_at",
            "priority_backlog_id",
            "case_count",
            "target_roots",
            "runtime_changed_files",
            "target_changed_files",
            "target_git_changed",
        }
    }

    target_roots = sorted(set(expected_case_targets_for_family(config_root, family).values()))
    return {
        "family_id": family["family_id"],
        "priority_backlog_id": family["priority_backlog_id"],
        "status": FreshLocalModelDriftStatus.PASSED.value if family_passed else FreshLocalModelDriftStatus.FAILED.value,
        "case_ids": string_list(family.get("case_ids")),
        "target_roots": target_roots,
        "required_routes": ["anythingllm", "gateway"],
        "fresh_local_eval_path": family["fresh_local_eval_path"],
        "fresh_local_eval_sha256": artifact_hash(local_eval_path),
        "fresh_comparison_path": family["fresh_comparison_path"],
        "fresh_comparison_sha256": artifact_hash(comparison_path),
        "source_hashes": source_hashes_for_family(config_root, family),
        "commands": {
            "local_eval": local_command_result,
            "comparison": comparison_command_result,
        },
        "comparison": {
            key: value
            for key, value in comparison.items()
            if key
            in {
                "kind",
                "schema_version",
                "status",
                "priority_backlog_id",
                "response_count",
                "passed_response_count",
                "critical_finding_count",
                "high_finding_count",
                "gap_categories",
                "recommended_next_repairs",
            }
        },
        "local_eval_summary": local_eval_summary,
        "minimum_route_score": min_score,
        "prior_minimum_route_score": prior_comparison.get("minimum_route_score"),
        "drift_severity": drift_severity.value,
        "next_action": "none" if family_passed else "inspect fresh comparison and repair the smallest harness gap",
    }


def report_summary(catalog: dict[str, Any], families: list[dict[str, Any]]) -> dict[str, Any]:
    gap_categories: dict[str, int] = {}
    response_count = 0
    passed_response_count = 0
    critical_count = 0
    high_count = 0
    min_scores: dict[str, int] = {}
    for family in families:
        comparison = dict_value(family.get("comparison"))
        response_count += int(comparison.get("response_count") or 0)
        passed_response_count += int(comparison.get("passed_response_count") or 0)
        critical_count += int(comparison.get("critical_finding_count") or 0)
        high_count += int(comparison.get("high_finding_count") or 0)
        for category, count in dict_value(comparison.get("gap_categories")).items():
            if isinstance(count, int):
                gap_categories[str(category)] = gap_categories.get(str(category), 0) + count
        score = family.get("minimum_route_score")
        if isinstance(score, int):
            min_scores[str(family.get("family_id"))] = score
    failed_family_count = sum(1 for family in families if family.get("status") != FreshLocalModelDriftStatus.PASSED.value)
    selected_case_count = sum(len(string_list(family.get("case_ids"))) for family in object_list(catalog.get("families")))
    drift_status = (
        "no_drift_detected"
        if families
        and failed_family_count == 0
        and all(family.get("drift_severity") == DriftSeverity.NONE.value for family in families)
        else "drift_detected"
    )
    return {
        "family_count": len(families),
        "selected_case_count": selected_case_count,
        "response_count": response_count,
        "passed_response_count": passed_response_count,
        "failed_family_count": failed_family_count,
        "critical_finding_count": critical_count,
        "high_finding_count": high_count,
        "gap_categories": dict(sorted(gap_categories.items())),
        "required_routes": ["anythingllm", "gateway"],
        "target_roots": [
            "/mnt/c/coinbase_testing_repo_frozen_tmp",
            "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        ],
        "minimum_route_scores": min_scores,
        "drift_status": drift_status,
        "next_action": "none" if drift_status == "no_drift_detected" else "inspect failed family reports before advancing",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--catalog-path", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--baseline-corpus-path", default=str(DEFAULT_BASELINE_CORPUS_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_DIR / "fresh-local-model-drift-report.json"))
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--command-timeout-seconds", type=int, default=3600)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    catalog_path = resolve_path(config_root, args.catalog_path)
    baseline_corpus_path = resolve_path(config_root, args.baseline_corpus_path)
    output_path = resolve_path(config_root, args.output_path)
    catalog = read_json_object(catalog_path)
    baseline_corpus = read_json_object(baseline_corpus_path)
    baseline_entries = stable_baseline_entries(baseline_corpus)

    catalog_errors = validate_fresh_local_model_drift_catalog(
        catalog,
        config_root=config_root,
        baseline_corpus=baseline_corpus,
        require_baseline_artifacts=True,
    )
    families: list[dict[str, Any]] = []
    if not catalog_errors:
        for family in object_list(catalog.get("families")):
            family_id = str(family.get("family_id"))
            print(f"PHASE127 FRESH DRIFT FAMILY START family={family_id}")
            result = family_result(
                args=args,
                config_root=config_root,
                family=family,
                baseline_entry=baseline_entries.get(family_id, {}),
            )
            families.append(result)
            print(
                "PHASE127 FRESH DRIFT FAMILY "
                + json.dumps(
                    {
                        "family_id": family_id,
                        "status": result["status"],
                        "minimum_route_score": result["minimum_route_score"],
                        "drift_severity": result["drift_severity"],
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )

    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "fresh_local_model_drift_report",
        "phase": 127,
        "priority_backlog_id": "P0-BB-012",
        "status": FreshLocalModelDriftStatus.PASSED.value,
        "generated_at": utc_timestamp(),
        "catalog_path": str(Path(args.catalog_path)),
        "catalog_sha256": artifact_hash(catalog_path),
        "baseline_corpus_path": str(Path(args.baseline_corpus_path)),
        "baseline_corpus_sha256": artifact_hash(baseline_corpus_path),
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_api_base_url": args.anythingllm_api_base_url,
        "workspace": args.workspace,
        "baseline_governance_status": "passed" if not catalog_errors else "failed",
        "families": families,
        "summary": report_summary(catalog, families),
        "errors": catalog_errors,
    }
    errors = catalog_errors + validate_fresh_local_model_drift_report(
        report,
        catalog=catalog,
        baseline_corpus=baseline_corpus,
        config_root=config_root,
        require_artifacts=True,
    )
    if errors:
        report["status"] = FreshLocalModelDriftStatus.FAILED.value
        report["errors"] = sorted(set(errors))
        errors = catalog_errors + validate_fresh_local_model_drift_report(
            report,
            catalog=catalog,
            baseline_corpus=baseline_corpus,
            config_root=config_root,
            require_artifacts=True,
        )
        report["errors"] = sorted(set(errors))
    else:
        report["errors"] = []
    report["summary"]["error_count"] = len(report["errors"])
    write_json(output_path, report)
    print("PHASE127 FRESH LOCAL MODEL DRIFT " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != FreshLocalModelDriftStatus.PASSED.value:
        print("PHASE127 FRESH LOCAL MODEL DRIFT ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE127 FRESH LOCAL MODEL DRIFT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
