#!/usr/bin/env python3
"""Run skill-system mutation checks against disposable registry copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_skill_release_gate import validate_release_gate_proofs  # noqa: E402
from vllm_agent_gateway.skills.registry import SkillRegistryError, load_skill_registry  # noqa: E402


DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-mutations"
DEFAULT_PROTECTED_ROOTS = [
    Path("/mnt/c/coinbase_testing_repo_frozen_tmp"),
    Path("/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
]
PROTECTED_WATCHED_FILES = ["core/stealth_order_manager.py"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def protected_snapshot(roots: list[Path]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for root in roots:
        if not root.exists():
            snapshot[str(root)] = {"present": False, "files": {}, "git_status": None}
            continue
        files = {
            relative: sha256_file(root / relative)
            for relative in PROTECTED_WATCHED_FILES
            if (root / relative).exists()
        }
        snapshot[str(root)] = {"present": True, "files": files, "git_status": git_status(root)}
    return snapshot


def protected_mutated(before: dict[str, Any], roots: list[Path]) -> bool:
    return protected_snapshot(roots) != before


def copy_fixture_root(config_root: Path, case_root: Path) -> Path:
    disposable = case_root / "disposable-root"
    shutil.copytree(config_root / "runtime", disposable / "runtime")
    shutil.copytree(config_root / ".qwen" / "skills", disposable / ".qwen" / "skills")
    shutil.copy2(config_root / "README.skill-registry.md", disposable / "README.skill-registry.md")
    (disposable / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        config_root / "docs" / "SKILL_LIBRARY_SCALING_PLAN.md",
        disposable / "docs" / "SKILL_LIBRARY_SCALING_PLAN.md",
    )
    return disposable


def first_full_skill(root: Path) -> dict[str, Any]:
    manifest = read_json(root / "runtime" / "skills.json")
    for skill in manifest["skills"]:
        if isinstance(skill, dict) and isinstance(skill.get("path"), str) and "capability_contract" in skill:
            return deepcopy(skill)
    raise RuntimeError("No full skill entry found for mutation fixture.")


def mutate_first_skill(root: Path, mutator: Callable[[dict[str, Any]], None]) -> None:
    path = root / "runtime" / "skills.json"
    manifest = read_json(path)
    for index, skill in enumerate(manifest["skills"]):
        if isinstance(skill, dict) and isinstance(skill.get("path"), str) and "capability_contract" in skill:
            updated = deepcopy(skill)
            mutator(updated)
            manifest["skills"][index] = updated
            write_json(path, manifest)
            return
    raise RuntimeError("No full skill entry found for mutation fixture.")


def duplicate_route_key(root: Path) -> None:
    path = root / "runtime" / "skills.json"
    manifest = read_json(path)
    full_indices = [
        index
        for index, skill in enumerate(manifest["skills"])
        if isinstance(skill, dict) and isinstance(skill.get("capability_contract"), dict)
    ]
    if len(full_indices) < 2:
        raise RuntimeError("Need at least two skills for duplicate_route_key mutation.")
    first = manifest["skills"][full_indices[0]]
    second = deepcopy(manifest["skills"][full_indices[1]])
    second["capability_contract"]["route_key"] = first["capability_contract"]["route_key"]
    manifest["skills"][full_indices[1]] = second
    write_json(path, manifest)


def missing_skill_body(root: Path) -> None:
    skill = first_full_skill(root)
    (root / skill["path"]).unlink()


def broken_frontmatter(root: Path) -> None:
    skill = first_full_skill(root)
    (root / skill["path"]).write_text("# Broken frontmatter\n", encoding="utf-8")


def unknown_workflow(root: Path) -> None:
    def mutate(skill: dict[str, Any]) -> None:
        skill["workflows"] = ["missing.workflow"]
        skill["workflow_priorities"] = {"missing.workflow": 1000}

    mutate_first_skill(root, mutate)


def unknown_tool(root: Path) -> None:
    mutate_first_skill(root, lambda skill: skill.__setitem__("allowed_tools", ["missing_tool"]))


def missing_eval_case(root: Path) -> None:
    def mutate(skill: dict[str, Any]) -> None:
        skill["capability_contract"]["eval_case_ids"] = ["missing_eval_case"]

    mutate_first_skill(root, mutate)


def deprecated_replacement_breakage(root: Path) -> None:
    def mutate(skill: dict[str, Any]) -> None:
        skill["eval_status"] = "deprecated"
        skill["deprecation"] = {
            "replaced_by": "missing-replacement-skill",
            "reason": "Mutation fixture breaks deprecated replacement validation.",
            "effective_date": "2026-06-05",
        }

    mutate_first_skill(root, mutate)


def route_namespace_drift(root: Path) -> None:
    def mutate(skill: dict[str, Any]) -> None:
        skill["capability_contract"]["route_key"] = "unknown.phase48_namespace_drift"

    mutate_first_skill(root, mutate)


def validate_registry_failure(root: Path) -> tuple[str, list[str]]:
    try:
        load_skill_registry(root)
    except SkillRegistryError as exc:
        message = str(exc)
        return classify_registry_failure(message), [message]
    return "no_failure", []


def classify_registry_failure(message: str) -> str:
    lower = message.lower()
    if "duplicate skill capability route_key" in lower:
        return "duplicate_route_key"
    if "path does not exist" in lower:
        return "missing_skill_body"
    if "frontmatter" in lower:
        return "broken_frontmatter"
    if "workflows contains unknown" in lower:
        return "unknown_workflow"
    if "allowed_tools contains unknown" in lower:
        return "unknown_tool"
    if "unknown case" in lower:
        return "missing_eval_case"
    if "deprecation.replaced_by references unknown" in lower or "deprecated" in lower:
        return "deprecated_replacement_breakage"
    if "unsupported namespace" in lower:
        return "route_namespace_drift"
    return "unexpected_registry_failure"


def stale_live_proof(root: Path, case_root: Path) -> tuple[str, list[str]]:
    skills_manifest = read_json(root / "runtime" / "skills.json")
    eval_manifest = read_json(root / "runtime" / "skill_evals.json")
    skills = [item for item in skills_manifest.get("skills", []) if isinstance(item, dict)]
    eval_cases = [item for item in eval_manifest.get("cases", []) if isinstance(item, dict)]
    route_key_count = sum(
        1
        for item in skills
        if isinstance(item.get("capability_contract"), dict)
        and isinstance(item["capability_contract"].get("route_key"), str)
    )
    stale_eval = {
        "status": "passed",
        "summary": {"case_count": -1, "failed_count": 0},
    }
    stale_scale = {
        "status": "passed",
        "summary": {
            "skill_count": len(skills),
            "eval_case_count": len(eval_cases),
            "route_key_count": route_key_count,
            "do_not_admit_count": 0,
        },
    }
    stale_selector = {
        "status": "passed",
        "summary": {
            "largest_skill_count": 10_000,
            "body_reads_during_selection": 0,
            "negative_fixture_rejected_count": 1,
            "negative_fixture_count": 1,
        },
    }
    docs_index = {"status": "passed", "orphaned_docs": []}
    paths = {
        "eval": case_root / "stale-skill-evals.json",
        "scale": case_root / "stale-scale.json",
        "selector": case_root / "stale-selector.json",
        "docs": case_root / "docs-index.json",
    }
    write_json(paths["eval"], stale_eval)
    write_json(paths["scale"], stale_scale)
    write_json(paths["selector"], stale_selector)
    write_json(paths["docs"], docs_index)
    checks = validate_release_gate_proofs(
        catalog={
            "skill_count": len(skills),
            "eval_case_count": len(eval_cases),
            "route_key_count": route_key_count,
        },
        skill_eval_path=paths["eval"],
        scale_path=paths["scale"],
        selector_scale_path=paths["selector"],
        docs_index_path=paths["docs"],
    )
    errors = [
        error
        for check in checks
        if check["status"] != "passed"
        for error in check.get("errors", [])
    ]
    if errors:
        return "stale_live_proof", errors
    return "no_failure", []


MUTATIONS: list[dict[str, Any]] = [
    {"id": "duplicate_route_key", "expected": "duplicate_route_key", "kind": "registry", "mutate": duplicate_route_key},
    {"id": "missing_skill_body", "expected": "missing_skill_body", "kind": "registry", "mutate": missing_skill_body},
    {"id": "broken_frontmatter", "expected": "broken_frontmatter", "kind": "registry", "mutate": broken_frontmatter},
    {"id": "unknown_workflow", "expected": "unknown_workflow", "kind": "registry", "mutate": unknown_workflow},
    {"id": "unknown_tool", "expected": "unknown_tool", "kind": "registry", "mutate": unknown_tool},
    {"id": "missing_eval_case", "expected": "missing_eval_case", "kind": "registry", "mutate": missing_eval_case},
    {"id": "stale_live_proof", "expected": "stale_live_proof", "kind": "proof", "mutate": None},
    {
        "id": "deprecated_replacement_breakage",
        "expected": "deprecated_replacement_breakage",
        "kind": "registry",
        "mutate": deprecated_replacement_breakage,
    },
    {"id": "route_namespace_drift", "expected": "route_namespace_drift", "kind": "registry", "mutate": route_namespace_drift},
]


def run_mutation_case(config_root: Path, run_dir: Path, mutation: dict[str, Any], protected_roots: list[Path]) -> dict[str, Any]:
    case_root = run_dir / mutation["id"]
    case_root.mkdir(parents=True, exist_ok=True)
    protected_before = protected_snapshot(protected_roots)
    disposable = copy_fixture_root(config_root, case_root)
    observed = "no_failure"
    errors: list[str] = []
    try:
        if mutation["kind"] == "registry":
            mutation["mutate"](disposable)
            observed, errors = validate_registry_failure(disposable)
        elif mutation["kind"] == "proof":
            observed, errors = stale_live_proof(disposable, case_root)
        else:
            observed, errors = "unknown_mutation_kind", [str(mutation["kind"])]
    finally:
        shutil.rmtree(disposable, ignore_errors=True)
    restored = not disposable.exists()
    protected_changed = protected_mutated(protected_before, protected_roots)
    passed = observed == mutation["expected"] and restored and not protected_changed
    return {
        "mutation_id": mutation["id"],
        "expected_failure_code": mutation["expected"],
        "observed_failure_code": observed,
        "status": "passed" if passed else "failed",
        "errors": errors,
        "disposable_root": str(disposable),
        "restored_or_deleted": restored,
        "protected_fixture_mutated": protected_changed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--protected-root", action="append", dest="protected_roots")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = (
        Path(args.output_path).resolve()
        if args.output_path
        else config_root / DEFAULT_REPORT_DIR / f"skill-mutations-{artifact_timestamp()}.json"
    )
    run_dir = output_path.parent / output_path.stem
    protected_roots = [Path(item).resolve() for item in args.protected_roots] if args.protected_roots else DEFAULT_PROTECTED_ROOTS
    results = [run_mutation_case(config_root, run_dir, mutation, protected_roots) for mutation in MUTATIONS]
    failed = [item for item in results if item["status"] != "passed"]
    report = {
        "kind": "skill_mutation_report",
        "schema_version": 1,
        "status": "passed" if not failed else "failed",
        "created_at": utc_now(),
        "config_root": str(config_root),
        "protected_roots": [str(root) for root in protected_roots],
        "summary": {
            "mutation_count": len(results),
            "passed_count": len(results) - len(failed),
            "failed_count": len(failed),
            "protected_fixture_mutated": any(item["protected_fixture_mutated"] for item in results),
            "all_disposable_roots_restored_or_deleted": all(item["restored_or_deleted"] for item in results),
        },
        "mutations": results,
    }
    write_json(output_path, report)
    print(f"SKILL MUTATION REPORT {output_path}")
    print("SKILL MUTATION SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if failed:
        print("SKILL MUTATION FAILURES " + json.dumps(failed, ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL MUTATION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
