"""EIG pull-request merge-readiness gate."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import (
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_pr_merge_readiness_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-pr-merge-readiness"
ALLOWED_MERGE_STATES = {"CLEAN"}


class EIGPrMergeReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGPrMergeReadinessConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    skip_github: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-pr-merge-readiness-{utc_timestamp()}.json"


def git_lines(config_root: Path, *args: str, check: bool = True) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(config_root),
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def gh_json(config_root: Path, pr_number: int) -> dict[str, Any]:
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,state,mergeStateStatus,url,headRefName,baseRefName,title,body",
        ],
        cwd=str(config_root),
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    return value if isinstance(value, dict) else {}


def phase_statuses(roadmap_text: str, phases: list[int]) -> dict[str, str | None]:
    statuses: dict[str, str | None] = {}
    for phase in phases:
        marker = f"### Approved Phase {phase}:"
        start = roadmap_text.find(marker)
        if start < 0:
            statuses[str(phase)] = None
            continue
        next_start = roadmap_text.find("### Approved Phase ", start + len(marker))
        body = roadmap_text[start:] if next_start < 0 else roadmap_text[start:next_start]
        status = None
        for line in body.splitlines():
            if line.startswith("Status: "):
                status = line.removeprefix("Status: ").strip()
                break
        statuses[str(phase)] = status
    return statuses


def file_records(config_root: Path, paths: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path_value in paths:
        path = resolve_path(config_root, path_value)
        records.append(
            {
                "path": path_value,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return records


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "eig_pr_merge_readiness_policy":
        errors.append("policy.kind must be eig_pr_merge_readiness_policy")
    if policy.get("phase") != 310:
        errors.append("policy.phase must be 310")
    pr = policy.get("pr") if isinstance(policy.get("pr"), dict) else {}
    if pr.get("number") != 1:
        errors.append("pr.number must be 1")
    if pr.get("required_state") != "OPEN":
        errors.append("pr.required_state must be OPEN")
    if pr.get("expected_head_ref") != "codex/eig-stable-handoff":
        errors.append("pr.expected_head_ref must be codex/eig-stable-handoff")
    if pr.get("expected_base_ref") != "main":
        errors.append("pr.expected_base_ref must be main")
    if set(string_list(pr.get("required_merge_state_statuses"))) != ALLOWED_MERGE_STATES:
        errors.append("pr.required_merge_state_statuses must be CLEAN")
    for field in ("required_docs", "required_scripts", "required_pr_body_markers", "forbidden_tracked_path_fragments"):
        if not string_list(policy.get(field)):
            errors.append(f"policy.{field} must be a non-empty string array")
    phases = policy.get("required_phases")
    if not isinstance(phases, list) or not phases or not all(isinstance(item, int) for item in phases):
        errors.append("policy.required_phases must be a non-empty integer array")
    merge_policy = policy.get("merge_policy") if isinstance(policy.get("merge_policy"), dict) else {}
    for key in ("merge_allowed", "main_mutation_allowed", "stable_corpus_promotion_allowed"):
        if merge_policy.get(key) is not False:
            errors.append(f"merge_policy.{key} must be false")
    return errors


def build_report(
    *,
    policy: dict[str, Any],
    branch: str,
    commit: str,
    upstream: str | None,
    status_lines: list[str],
    docs: list[dict[str, Any]],
    scripts: list[dict[str, Any]],
    phase_status_map: dict[str, str | None],
    tracked_forbidden_paths: list[str],
    pr: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    pr_policy = policy.get("pr") if isinstance(policy.get("pr"), dict) else {}
    merge_policy = policy.get("merge_policy") if isinstance(policy.get("merge_policy"), dict) else {}
    body = pr.get("body") if isinstance(pr.get("body"), str) else ""
    required_markers = string_list(policy.get("required_pr_body_markers"))
    missing_body_markers = [marker for marker in required_markers if marker not in body]
    missing_docs = [item["path"] for item in docs if item.get("exists") is not True]
    missing_scripts = [item["path"] for item in scripts if item.get("exists") is not True]
    incomplete_phases = [phase for phase, status in phase_status_map.items() if status != "Complete."]
    expected_head_ref = pr_policy.get("expected_head_ref")
    pr_checks = {
        "number": pr.get("number"),
        "state": pr.get("state"),
        "merge_state_status": pr.get("mergeStateStatus"),
        "head_ref": pr.get("headRefName"),
        "base_ref": pr.get("baseRefName"),
        "url": pr.get("url"),
        "state_ok": pr.get("state") == pr_policy.get("required_state"),
        "merge_state_ok": pr.get("mergeStateStatus") in string_list(pr_policy.get("required_merge_state_statuses")),
        "head_ref_ok": pr.get("headRefName") == pr_policy.get("expected_head_ref"),
        "base_ref_ok": pr.get("baseRefName") == pr_policy.get("expected_base_ref"),
    }
    source = {
        "branch": branch,
        "commit": commit,
        "upstream": upstream,
        "branch_ok": branch == expected_head_ref,
        "source_clean": not status_lines,
        "status_lines": status_lines,
    }
    summary = {
        "status": EIGPrMergeReadinessStatus.PASSED.value,
        "pr_number": pr.get("number"),
        "pr_state": pr.get("state"),
        "pr_merge_state_status": pr.get("mergeStateStatus"),
        "source_clean": source["source_clean"],
        "missing_doc_count": len(missing_docs),
        "missing_script_count": len(missing_scripts),
        "incomplete_phase_count": len(incomplete_phases),
        "forbidden_tracked_path_count": len(tracked_forbidden_paths),
        "missing_pr_body_marker_count": len(missing_body_markers),
        "merge_allowed": merge_policy.get("merge_allowed"),
        "main_mutation_allowed": merge_policy.get("main_mutation_allowed"),
        "stable_corpus_promotion_allowed": merge_policy.get("stable_corpus_promotion_allowed"),
        "validation_error_count": 0,
        "ready_for_founder_merge_decision": False,
    }
    validation_errors = list(errors)
    if not source["source_clean"]:
        validation_errors.append("source must be clean before merge-readiness")
    if not source["branch_ok"]:
        validation_errors.append(f"source.branch must be {expected_head_ref}")
    if missing_docs:
        validation_errors.append("required docs missing: " + ", ".join(missing_docs))
    if missing_scripts:
        validation_errors.append("required scripts missing: " + ", ".join(missing_scripts))
    if incomplete_phases:
        validation_errors.append("required phases incomplete: " + ", ".join(incomplete_phases))
    if tracked_forbidden_paths:
        validation_errors.append("forbidden tracked paths present: " + ", ".join(tracked_forbidden_paths))
    if missing_body_markers:
        validation_errors.append("required PR body markers missing: " + ", ".join(missing_body_markers))
    for key, value in pr_checks.items():
        if key.endswith("_ok") and value is not True:
            validation_errors.append(f"pr.{key} must be true")
    status = EIGPrMergeReadinessStatus.PASSED.value if not validation_errors else EIGPrMergeReadinessStatus.FAILED.value
    summary["status"] = status
    summary["validation_error_count"] = len(validation_errors)
    summary["ready_for_founder_merge_decision"] = status == EIGPrMergeReadinessStatus.PASSED.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_pr_merge_readiness_report",
        "phase": 310,
        "status": status,
        "summary": summary,
        "source": source,
        "pr": pr_checks,
        "docs": docs,
        "scripts": scripts,
        "prior_phases": {
            "required": [str(item) for item in policy.get("required_phases", [])],
            "statuses": phase_status_map,
            "incomplete": incomplete_phases,
        },
        "hygiene": {
            "forbidden_tracked_paths": tracked_forbidden_paths,
            "forbidden_tracked_path_fragments": string_list(policy.get("forbidden_tracked_path_fragments")),
        },
        "pr_body": {
            "required_markers": required_markers,
            "missing_markers": missing_body_markers,
        },
        "merge_policy": merge_policy,
        "validation_errors": validation_errors,
    }


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"report.schema_version must be {SCHEMA_VERSION}")
    if report.get("kind") != "eig_pr_merge_readiness_report":
        errors.append("report.kind must be eig_pr_merge_readiness_report")
    if report.get("phase") != 310:
        errors.append("report.phase must be 310")
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if summary.get("merge_allowed") is not False:
        errors.append("summary.merge_allowed must be false")
    if summary.get("main_mutation_allowed") is not False:
        errors.append("summary.main_mutation_allowed must be false")
    if summary.get("stable_corpus_promotion_allowed") is not False:
        errors.append("summary.stable_corpus_promotion_allowed must be false")
    if report.get("status") == EIGPrMergeReadinessStatus.PASSED.value:
        if summary.get("ready_for_founder_merge_decision") is not True:
            errors.append("summary.ready_for_founder_merge_decision must be true when passed")
        if report.get("validation_errors"):
            errors.append("validation_errors must be empty when passed")
    return errors


def run_eig_pr_merge_readiness(config: EIGPrMergeReadinessConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)
    branch = (git_lines(config_root, "branch", "--show-current", check=False) or [""])[0]
    commit = (git_lines(config_root, "rev-parse", "--short", "HEAD", check=False) or [""])[0]
    upstream_lines = git_lines(config_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    upstream = upstream_lines[0] if upstream_lines else None
    status_lines = git_lines(config_root, "status", "--porcelain", "--untracked-files=no", check=False)
    docs = file_records(config_root, string_list(policy.get("required_docs")))
    scripts = file_records(config_root, string_list(policy.get("required_scripts")))
    roadmap_path = resolve_path(config_root, "docs/ACTIONABLE_WORKFLOW_ROADMAP.md")
    phase_status_map = phase_statuses(
        roadmap_path.read_text(encoding="utf-8") if roadmap_path.is_file() else "",
        [item for item in policy.get("required_phases", []) if isinstance(item, int)],
    )
    tracked = git_lines(config_root, "ls-files", check=False)
    fragments = string_list(policy.get("forbidden_tracked_path_fragments"))
    tracked_forbidden_paths = [path for path in tracked if any(fragment in path for fragment in fragments)]
    pr_policy = policy.get("pr") if isinstance(policy.get("pr"), dict) else {}
    required_merge_states = string_list(pr_policy.get("required_merge_state_statuses"))
    pr = {
        "number": pr_policy.get("number"),
        "state": pr_policy.get("required_state"),
        "mergeStateStatus": required_merge_states[0] if required_merge_states else None,
        "headRefName": pr_policy.get("expected_head_ref"),
        "baseRefName": pr_policy.get("expected_base_ref"),
        "url": None,
        "body": "\n".join(string_list(policy.get("required_pr_body_markers"))),
    }
    if not config.skip_github:
        try:
            pr = gh_json(config_root, int(pr_policy.get("number") or 0))
        except Exception as exc:  # pragma: no cover - depends on GitHub CLI availability.
            errors.append(f"gh pr view failed: {type(exc).__name__}: {exc}")
    report = build_report(
        policy=policy,
        branch=branch,
        commit=commit,
        upstream=upstream,
        status_lines=status_lines,
        docs=docs,
        scripts=scripts,
        phase_status_map=phase_status_map,
        tracked_forbidden_paths=tracked_forbidden_paths,
        pr=pr,
        errors=errors,
    )
    report["policy_path"] = str(policy_path)
    report["report_path"] = str(output_path)
    report_validation_errors = validate_report(report)
    if report_validation_errors:
        report["validation_errors"].extend(report_validation_errors)
        report["status"] = EIGPrMergeReadinessStatus.FAILED.value
        report["summary"]["status"] = EIGPrMergeReadinessStatus.FAILED.value
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["ready_for_founder_merge_decision"] = False
    write_json(output_path, report)
    return report
