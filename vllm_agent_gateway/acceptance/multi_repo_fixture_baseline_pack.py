"""Multi-repo fixture baseline-pack validation for Phase 209."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "multi_repo_fixture_baseline_pack_policy"
EXPECTED_REPORT_KIND = "multi_repo_fixture_baseline_pack_report"
EXPECTED_PHASE = 209
EXPECTED_BACKLOG_ID = "P0-M5-209"
EXPECTED_MILESTONE_ID = "M5"
DEFAULT_POLICY_PATH = Path("runtime") / "multi_repo_fixture_baseline_pack_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase209" / "phase209-multi-repo-fixture-baseline-pack-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase209" / "phase209-multi-repo-fixture-baseline-pack-report.md"


class MultiRepoBaselineStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class MultiRepoFixtureBaselinePackConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def fixture_file_counts(root: Path) -> dict[str, int]:
    files = [path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts]
    return {
        "file_count": len(files),
        "python_file_count": sum(path.suffix == ".py" for path in files),
        "test_file_count": sum("tests" in path.parts for path in files),
        "markdown_file_count": sum(path.suffix.lower() == ".md" for path in files),
    }


def rubric_total(case: dict[str, Any]) -> int:
    baseline = dict_value(case.get("blind_baseline"))
    return sum(int(item.get("points", 0)) for item in object_list(baseline.get("scoring_rubric")))


def validate_fixture(policy: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    fixture = dict_value(policy.get("fixture"))
    root_value = fixture.get("local_path")
    proof: dict[str, Any] = {
        "fixture_id": fixture.get("fixture_id"),
        "name": fixture.get("name"),
        "local_path": root_value,
        "exists": False,
        "git": False,
        "clean": False,
    }
    if not isinstance(root_value, str) or not root_value:
        return proof, ["fixture.local_path must be a non-empty string"]
    root = Path(root_value)
    proof["exists"] = root.is_dir()
    proof["git"] = (root / ".git").is_dir()
    if not root.is_dir():
        errors.append(f"fixture.local_path is missing: {root}")
        return proof, errors
    if not (root / ".git").is_dir():
        errors.append(f"fixture.local_path is not a git checkout: {root}")
        return proof, errors
    try:
        head = run_git(root, "rev-parse", "HEAD")
        branch = run_git(root, "branch", "--show-current")
        status = run_git(root, "status", "--short")
    except subprocess.CalledProcessError as exc:
        errors.append(f"fixture git command failed: {exc}")
        return proof, errors
    counts = fixture_file_counts(root)
    proof.update(counts)
    proof.update({"head": head, "branch": branch, "clean": status == "", "status_short": status})
    if head != fixture.get("expected_commit"):
        errors.append(f"fixture HEAD {head} does not match expected_commit {fixture.get('expected_commit')}")
    if branch != fixture.get("default_branch"):
        errors.append(f"fixture branch {branch!r} does not match default_branch {fixture.get('default_branch')!r}")
    if status:
        errors.append("fixture worktree must be clean")
    for count_key in ("expected_file_count", "expected_python_file_count", "expected_test_file_count"):
        expected = fixture.get(count_key)
        actual_key = count_key.replace("expected_", "")
        if isinstance(expected, int) and counts.get(actual_key) != expected:
            errors.append(f"fixture.{count_key} expected {expected} got {counts.get(actual_key)}")
    forbidden = set(string_list(fixture.get("forbidden_operations")))
    for required in ("commit_to_staterail", "push_to_staterail", "publish_staterail_branch", "mutate_staterail_remote"):
        if required not in forbidden:
            errors.append(f"fixture.forbidden_operations must include {required}")
    allowed = set(string_list(fixture.get("allowed_operations")))
    for required in ("clone_or_refresh_local_fixture", "read_source_docs_tests", "run_tests", "create_disposable_mutation_copy"):
        if required not in allowed:
            errors.append(f"fixture.allowed_operations must include {required}")
    if fixture.get("mutation_policy") != "read_only_fixture_disposable_copy_only":
        errors.append("fixture.mutation_policy must be read_only_fixture_disposable_copy_only")
    return proof, errors


def validate_case(case: dict[str, Any], *, fixture_root: Path, required_categories: set[str], seen: set[str]) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("case_id") or "<missing>")
    prefix = f"case {case_id}"
    if case_id in seen:
        errors.append(f"{prefix} duplicates an earlier case_id")
    seen.add(case_id)
    category = case.get("category")
    if category not in required_categories:
        errors.append(f"{prefix} category must be one of {sorted(required_categories)}")
    for key in ("prompt_family", "target_root", "prompt", "expected_workflow", "mutation_policy"):
        if not isinstance(case.get(key), str) or not str(case[key]).strip():
            errors.append(f"{prefix}.{key} must be a non-empty string")
    if case.get("target_root") != str(fixture_root):
        errors.append(f"{prefix}.target_root must match fixture.local_path")
    if case.get("expected_workflow") != "code_investigation.plan":
        errors.append(f"{prefix}.expected_workflow must be code_investigation.plan")
    if case.get("mutation_policy") != "read_only_no_source_mutation":
        errors.append(f"{prefix}.mutation_policy must be read_only_no_source_mutation")
    for hint_key in ("source_hints", "test_hints"):
        hints = string_list(case.get(hint_key))
        if not hints:
            errors.append(f"{prefix}.{hint_key} must contain at least one path")
        for hint in hints:
            if not (fixture_root / hint).is_file():
                errors.append(f"{prefix}.{hint_key} path does not exist in fixture: {hint}")
    baseline = dict_value(case.get("blind_baseline"))
    for key in ("ideal_answer_shape", "must_have_evidence", "safety_boundaries", "output_format_expectations"):
        if len(string_list(baseline.get(key))) < 2:
            errors.append(f"{prefix}.blind_baseline.{key} must contain at least two entries")
    if "commit or push to s-aws/staterail" not in " ".join(string_list(baseline.get("safety_boundaries"))).lower():
        errors.append(f"{prefix}.blind_baseline.safety_boundaries must include the no commit/push boundary")
    if rubric_total(case) != 100:
        errors.append(f"{prefix}.blind_baseline.scoring_rubric points must total 100")
    if len(object_list(baseline.get("scoring_rubric"))) < 4:
        errors.append(f"{prefix}.blind_baseline.scoring_rubric must contain at least four dimensions")
    return errors


def validate_policy(policy: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 209")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"policy.milestone_id must be {EXPECTED_MILESTONE_ID}")
    required_categories = set(string_list(policy.get("required_categories")))
    expected_categories = {
        "code_explanation",
        "behavior_beginning_point",
        "related_tests",
        "change_surface",
        "validation_commands",
    }
    if required_categories != expected_categories:
        errors.append("policy.required_categories must cover the five Phase 209 prompt categories")
    fixture_proof, fixture_errors = validate_fixture(policy)
    errors.extend(fixture_errors)
    fixture_root = Path(str(dict_value(policy.get("fixture")).get("local_path") or ""))
    cases = object_list(policy.get("cases"))
    if len(cases) < len(expected_categories):
        errors.append("policy.cases must include at least one case per required category")
    seen_case_ids: set[str] = set()
    seen_categories: set[str] = set()
    if fixture_root:
        for case in cases:
            if isinstance(case.get("category"), str):
                seen_categories.add(str(case["category"]))
            errors.extend(validate_case(case, fixture_root=fixture_root, required_categories=required_categories, seen=seen_case_ids))
    missing_categories = sorted(required_categories - seen_categories)
    if missing_categories:
        errors.append("policy.cases missing required categories: " + ", ".join(missing_categories))
    limitations = " ".join(string_list(policy.get("current_phase_limitations"))).lower()
    for phrase in ("does not run local-model comparison", "does not mutate", "phase 210"):
        if phrase not in limitations:
            errors.append(f"policy.current_phase_limitations must mention {phrase!r}")
    requirements = string_list(policy.get("phase210_ready_requirements"))
    for phrase in ("fixture HEAD matches expected_commit", "rubrics total 100", "no commit or push"):
        if not any(phrase.lower() in item.lower() for item in requirements):
            errors.append(f"policy.phase210_ready_requirements must mention {phrase!r}")
    return errors, fixture_proof


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Multi-Repo Fixture Baseline Pack",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Phase: `{report.get('phase')}`",
        f"- Fixture: `{dict_value(report.get('fixture_proof')).get('name')}`",
        f"- Case count: `{summary.get('case_count')}`",
        f"- Phase 210 ready: `{summary.get('phase210_ready')}`",
        "",
        "## Fixture Proof",
    ]
    for key, value in dict_value(report.get("fixture_proof")).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Cases"])
    for case in object_list(report.get("case_summaries")):
        lines.append(f"- `{case.get('case_id')}` {case.get('category')}: {case.get('prompt')}")
    if string_list(report.get("errors")):
        lines.extend(["", "## Errors"])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines).rstrip() + "\n"


def validate_multi_repo_fixture_baseline_pack(config: MultiRepoFixtureBaselinePackConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors, fixture_proof = validate_policy(policy)
    cases = object_list(policy.get("cases"))
    status = MultiRepoBaselineStatus.PASSED.value if not errors else MultiRepoBaselineStatus.FAILED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "fixture_proof": fixture_proof,
        "case_summaries": [
            {
                "case_id": case.get("case_id"),
                "category": case.get("category"),
                "prompt_family": case.get("prompt_family"),
                "prompt": case.get("prompt"),
                "rubric_total": rubric_total(case),
                "source_hint_count": len(string_list(case.get("source_hints"))),
                "test_hint_count": len(string_list(case.get("test_hints"))),
            }
            for case in cases
        ],
        "errors": errors,
        "summary": {
            "fixture_id": dict_value(policy.get("fixture")).get("fixture_id"),
            "case_count": len(cases),
            "category_count": len({case.get("category") for case in cases if isinstance(case.get("category"), str)}),
            "required_category_count": len(string_list(policy.get("required_categories"))),
            "fixture_clean": fixture_proof.get("clean"),
            "phase210_ready": status == MultiRepoBaselineStatus.PASSED.value,
        },
    }
    output_path = resolve_path(config_root, config.output_path)
    markdown_path = resolve_path(config_root, config.markdown_output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_path, render_markdown_report(report))
    return report
