#!/usr/bin/env python3
"""Run the canonical skill-system release gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.docs_index import docs_index_report  # noqa: E402
from vllm_agent_gateway.skills.evals import run_skill_eval_catalog  # noqa: E402
from vllm_agent_gateway.skills.scale import build_skill_scale_report  # noqa: E402
from vllm_agent_gateway.skills.selector_scale import build_skill_selector_scale_report  # noqa: E402
from scripts.run_founder_field_prompt_eval import FIELD_PROMPTS  # noqa: E402
from scripts.validate_founder_field_prompt_matrix import (  # noqa: E402
    build_report as build_prompt_matrix_report,
    catalog_matrix_prompts,
    write_json as write_prompt_matrix_json,
    write_markdown as write_prompt_matrix_markdown,
)
from scripts.validate_prompt_catalog import build_report as build_prompt_catalog_report  # noqa: E402
from vllm_agent_gateway.acceptance.profiles import (  # noqa: E402
    LiveGuardLevel,
    ReleaseGateProfile,
    release_gate_profile_contract,
    release_gate_profile_contract_json,
    release_gate_profile_values,
)


DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-release-gates"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
WATCHED_RUNTIME_FILES = [
    "runtime/skills.json",
    "runtime/skill_evals.json",
    "runtime/workflows.json",
]


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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def skill_body_hashes(config_root: Path) -> dict[str, str]:
    skill_root = config_root / ".qwen" / "skills"
    if not skill_root.exists():
        return {}
    return {
        path.relative_to(config_root).as_posix(): sha256_file(path)
        for path in sorted(skill_root.glob("*/SKILL.md"))
    }


def watched_hashes(config_root: Path) -> dict[str, str]:
    hashes = {
        relative: sha256_file(config_root / relative)
        for relative in WATCHED_RUNTIME_FILES
        if (config_root / relative).exists()
    }
    body_hashes = skill_body_hashes(config_root)
    if body_hashes:
        digest = hashlib.sha256()
        for relative, value in body_hashes.items():
            digest.update(relative.encode("utf-8"))
            digest.update(value.encode("utf-8"))
        hashes[".qwen/skills/*/SKILL.md"] = digest.hexdigest()
    return hashes


def changed_hashes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, value in after.items() if before.get(key) != value)


def catalog_summary(config_root: Path) -> dict[str, Any]:
    skills_manifest = read_json(config_root / "runtime" / "skills.json")
    eval_manifest = read_json(config_root / "runtime" / "skill_evals.json")
    workflow_manifest = read_json(config_root / "runtime" / "workflows.json")
    skills = [item for item in skills_manifest.get("skills", []) if isinstance(item, dict)]
    eval_cases = [item for item in eval_manifest.get("cases", []) if isinstance(item, dict)]
    workflows = [item for item in workflow_manifest.get("workflows", []) if isinstance(item, dict)]
    route_namespace_counts: dict[str, int] = {}
    eval_status_counts: dict[str, int] = {}
    route_keys: list[str] = []
    for skill in skills:
        eval_status = str(skill.get("eval_status", "unknown"))
        eval_status_counts[eval_status] = eval_status_counts.get(eval_status, 0) + 1
        contract = skill.get("capability_contract") if isinstance(skill.get("capability_contract"), dict) else {}
        route_key = contract.get("route_key")
        if isinstance(route_key, str):
            route_keys.append(route_key)
            namespace = route_key.split(".", 1)[0]
            route_namespace_counts[namespace] = route_namespace_counts.get(namespace, 0) + 1
    return {
        "skill_count": len(skills),
        "eval_case_count": len(eval_cases),
        "workflow_count": len(workflows),
        "workflow_ids": sorted(str(item.get("id")) for item in workflows if isinstance(item.get("id"), str)),
        "route_key_count": len(route_keys),
        "route_namespace_counts": dict(sorted(route_namespace_counts.items())),
        "eval_status_counts": dict(sorted(eval_status_counts.items())),
    }


def command_record(label: str, command: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
    )
    elapsed = time.monotonic() - started
    return {
        "label": label,
        "command": command,
        "cwd": str(cwd),
        "returncode": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "elapsed_seconds": elapsed,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "rerun": " ".join(command),
    }


def proof_check(label: str, path: Path, status: str, errors: list[str]) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "status": status,
        "errors": errors,
    }


def json_summary_from_stdout(stdout: str, prefix: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if not line.startswith(prefix):
            continue
        text = line[len(prefix) :].strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def validate_release_gate_proofs(
    *,
    catalog: dict[str, Any],
    skill_eval_path: Path,
    scale_path: Path,
    selector_scale_path: Path,
    docs_index_path: Path,
    prompt_catalog_path: Path | None = None,
    prompt_matrix_path: Path | None = None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    if not skill_eval_path.exists():
        checks.append(proof_check("skill_eval_report", skill_eval_path, "failed", ["missing proof file"]))
    else:
        report = read_json(skill_eval_path)
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        errors: list[str] = []
        if report.get("status") != "passed":
            errors.append("skill eval report status is not passed")
        if summary.get("case_count") != catalog["eval_case_count"]:
            errors.append("skill eval report case_count does not match current catalog")
        if summary.get("failed_count") != 0:
            errors.append("skill eval report failed_count is not zero")
        checks.append(proof_check("skill_eval_report", skill_eval_path, "passed" if not errors else "failed", errors))

    if not scale_path.exists():
        checks.append(proof_check("skill_scale_report", scale_path, "failed", ["missing proof file"]))
    else:
        report = read_json(scale_path)
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        errors = []
        if report.get("status") != "passed":
            errors.append("skill scale report status is not passed")
        for key in ("skill_count", "eval_case_count", "route_key_count"):
            if summary.get(key) != catalog[key]:
                errors.append(f"skill scale report {key} does not match current catalog")
        if summary.get("do_not_admit_count") != 0:
            errors.append("skill scale report do_not_admit_count is not zero")
        checks.append(proof_check("skill_scale_report", scale_path, "passed" if not errors else "failed", errors))

    if not selector_scale_path.exists():
        checks.append(proof_check("selector_scale_report", selector_scale_path, "failed", ["missing proof file"]))
    else:
        report = read_json(selector_scale_path)
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        errors = []
        if report.get("status") != "passed":
            errors.append("selector scale report status is not passed")
        if summary.get("largest_skill_count", 0) < 10_000:
            errors.append("selector scale report did not cover 10,000 synthetic skills")
        if summary.get("body_reads_during_selection") != 0:
            errors.append("selector scale report loaded skill bodies")
        if summary.get("negative_fixture_rejected_count") != summary.get("negative_fixture_count"):
            errors.append("selector scale report did not reject all negative fixtures")
        checks.append(proof_check("selector_scale_report", selector_scale_path, "passed" if not errors else "failed", errors))

    if not docs_index_path.exists():
        checks.append(proof_check("docs_index_report", docs_index_path, "failed", ["missing proof file"]))
    else:
        report = read_json(docs_index_path)
        errors = []
        if report.get("status") != "passed":
            errors.append("docs index report status is not passed")
        if report.get("orphaned_docs"):
            errors.append("docs index report has orphaned docs")
        checks.append(proof_check("docs_index_report", docs_index_path, "passed" if not errors else "failed", errors))

    if prompt_matrix_path is not None:
        if prompt_catalog_path is None or not prompt_catalog_path.exists():
            checks.append(
                proof_check(
                    "prompt_catalog_report",
                    prompt_catalog_path or Path("prompt-catalog.json"),
                    "failed",
                    ["missing proof file"],
                )
            )
        else:
            report = read_json(prompt_catalog_path)
            summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
            errors = []
            if report.get("status") != "passed":
                errors.append("prompt catalog report status is not passed")
            if summary.get("problem_count") != 0:
                errors.append("prompt catalog report problem count is not zero")
            if summary.get("case_count") != len(FIELD_PROMPTS):
                errors.append("prompt catalog report does not cover the full field prompt catalog")
            checks.append(proof_check("prompt_catalog_report", prompt_catalog_path, "passed" if not errors else "failed", errors))

        if not prompt_matrix_path.exists():
            checks.append(proof_check("prompt_matrix_report", prompt_matrix_path, "failed", ["missing proof file"]))
        else:
            report = read_json(prompt_matrix_path)
            summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
            errors = []
            if report.get("status") != "passed":
                errors.append("prompt matrix report status is not passed")
            if summary.get("failed") != 0:
                errors.append("prompt matrix report failed count is not zero")
            if len(report.get("cases") or []) < len(FIELD_PROMPTS):
                errors.append("prompt matrix report does not cover the full field prompt catalog")
            checks.append(proof_check("prompt_matrix_report", prompt_matrix_path, "passed" if not errors else "failed", errors))

    return checks


def resolve_release_profile(args: argparse.Namespace) -> ReleaseGateProfile:
    legacy_flags = [bool(args.offline_only), bool(args.live), bool(args.anythingllm)]
    if args.profile and any(legacy_flags):
        raise ValueError("--profile cannot be combined with --offline-only, --live, or --anythingllm")
    if args.profile:
        return ReleaseGateProfile(args.profile)
    if args.anythingllm:
        return ReleaseGateProfile.RELEASE_CANDIDATE
    if args.live:
        return ReleaseGateProfile.LIVE_FULL
    return ReleaseGateProfile.MUTATION


def resolved_mode(args: argparse.Namespace, profile: ReleaseGateProfile) -> str:
    if args.anythingllm:
        return "anythingllm"
    if args.live:
        return "live"
    if args.offline_only or not args.profile:
        return "offline-only"
    return profile.value


def run_release_gate(args: argparse.Namespace) -> dict[str, Any]:
    profile = resolve_release_profile(args)
    contract = release_gate_profile_contract(profile)
    config_root = Path(args.config_root).resolve()
    report_root = Path(args.output_root).resolve()
    run_id = f"skill-release-gate-{artifact_timestamp()}"
    run_dir = report_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    before_hashes = watched_hashes(config_root)
    catalog = catalog_summary(config_root)
    commands: list[dict[str, Any]] = []
    generated_reports: dict[str, str] = {}
    errors: list[str] = []

    skill_eval_path = run_dir / "skill-evals.json"
    scale_path = run_dir / "skill-scale.json"
    selector_scale_path = run_dir / "selector-scale.json"
    docs_index_path = run_dir / "docs-index.json"
    prompt_catalog_path = run_dir / "prompt-catalog.json"
    prompt_matrix_path = run_dir / "prompt-matrix.json"
    prompt_matrix_markdown_path = run_dir / "prompt-matrix.md"

    skill_eval_report = run_skill_eval_catalog(config_root, output_path=skill_eval_path)
    generated_reports["skill_eval_report"] = str(skill_eval_path)
    scale_report = build_skill_scale_report(config_root, output_path=scale_path)
    generated_reports["skill_scale_report"] = str(scale_path)
    selector_scale_report = build_skill_selector_scale_report(config_root, output_path=selector_scale_path)
    generated_reports["selector_scale_report"] = str(selector_scale_path)
    docs_report = docs_index_report(config_root)
    write_json(docs_index_path, docs_report)
    generated_reports["docs_index_report"] = str(docs_index_path)
    prompt_catalog_report = build_prompt_catalog_report(config_root)
    write_json(prompt_catalog_path, prompt_catalog_report)
    generated_reports["prompt_catalog_report"] = str(prompt_catalog_path)
    prompt_matrix_report = build_prompt_matrix_report(catalog_matrix_prompts(), config_root)
    write_prompt_matrix_json(prompt_matrix_path, prompt_matrix_report)
    write_prompt_matrix_markdown(prompt_matrix_markdown_path, prompt_matrix_report)
    generated_reports["prompt_matrix_report"] = str(prompt_matrix_path)
    generated_reports["prompt_matrix_markdown_report"] = str(prompt_matrix_markdown_path)

    for label, report in (
        ("skill_eval_report", skill_eval_report),
        ("skill_scale_report", scale_report),
        ("selector_scale_report", selector_scale_report),
        ("docs_index_report", docs_report),
        ("prompt_catalog_report", prompt_catalog_report),
        ("prompt_matrix_report", prompt_matrix_report),
    ):
        if report.get("status") != "passed":
            errors.append(f"{label} did not pass")

    python = sys.executable
    focused_commands = [
        (
            "skill_registry_eval_selector_regression",
            [
                python,
                "-m",
                "pytest",
                "tests/regression/test_skill_registry.py",
                "tests/regression/test_skill_evals.py",
                "tests/regression/test_skill_selector_scale.py",
                "-q",
            ],
        ),
        (
            "focused_skill_controller_regression",
            [
                python,
                "-m",
                "pytest",
                "tests/regression/test_controller_service.py",
                "-k",
                "phase50_batch_c or skill_batch or skill_eval_promotion or skill_lifecycle or skill_deprecation or skill_update or skill_selection or skill_pack or skill_scaffold",
                "-q",
            ],
        ),
    ]
    for label, command in focused_commands:
        record = command_record(label, command, cwd=config_root, timeout_seconds=args.timeout_seconds)
        commands.append(record)
        if record["status"] != "passed":
            errors.append(f"{label} failed")

    if contract.includes_mutation:
        mutation_command = [
            python,
            "scripts/validate_skill_mutations.py",
            "--output-path",
            str(run_dir / "skill-mutations.json"),
        ]
        record = command_record(
            "skill_mutation_fault_injection",
            mutation_command,
            cwd=config_root,
            timeout_seconds=args.timeout_seconds,
        )
        commands.append(record)
        if record["status"] != "passed":
            errors.append("skill_mutation_fault_injection failed")

    mode = resolved_mode(args, profile)
    if contract.live_guard_level != LiveGuardLevel.NONE:
        target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
        live_command = [
            python,
            "scripts/validate_skill_lifecycle_live.py",
            "--config-root",
            str(config_root),
            "--controller-base-url",
            args.controller_base_url,
            "--workflow-router-gateway-base-url",
            args.workflow_router_gateway_base_url,
            "--anythingllm-api-base-url",
            args.anythingllm_api_base_url,
            "--workspace",
            args.workspace,
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]
        for target_root in target_roots:
            live_command.extend(["--target-root", target_root])
        if not contract.includes_anythingllm:
            live_command.append("--skip-anythingllm")
        record = command_record("skill_lifecycle_live_guard", live_command, cwd=config_root, timeout_seconds=args.timeout_seconds)
        commands.append(record)
        if record["status"] != "passed":
            errors.append("skill_lifecycle_live_guard failed")

        if contract.live_guard_level == LiveGuardLevel.FULL:
            natural_lifecycle_command = [
                python,
                "scripts/validate_skill_natural_lifecycle_live.py",
                "--config-root",
                str(config_root),
                "--workflow-router-gateway-base-url",
                args.workflow_router_gateway_base_url,
                "--anythingllm-api-base-url",
                args.anythingllm_api_base_url,
                "--workspace",
                args.workspace,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ]
            for target_root in target_roots:
                natural_lifecycle_command.extend(["--target-root", target_root])
            if not contract.includes_anythingllm:
                natural_lifecycle_command.append("--skip-anythingllm")
            record = command_record(
                "skill_natural_lifecycle_live_guard",
                natural_lifecycle_command,
                cwd=config_root,
                timeout_seconds=args.timeout_seconds,
            )
            commands.append(record)
            if record["status"] != "passed":
                errors.append("skill_natural_lifecycle_live_guard failed")
            phase50_batch_command = [
                python,
                "scripts/validate_phase50_skill_batch_live.py",
                "--config-root",
                str(config_root),
                "--controller-base-url",
                args.controller_base_url,
                "--workflow-router-gateway-base-url",
                args.workflow_router_gateway_base_url,
                "--anythingllm-api-base-url",
                args.anythingllm_api_base_url,
                "--workspace",
                args.workspace,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ]
            for target_root in target_roots:
                phase50_batch_command.extend(["--target-root", target_root])
            if not contract.includes_anythingllm:
                phase50_batch_command.append("--skip-anythingllm")
            record = command_record(
                "phase50_skill_batch_live_guard",
                phase50_batch_command,
                cwd=config_root,
                timeout_seconds=args.timeout_seconds,
            )
            commands.append(record)
            if record["status"] != "passed":
                errors.append("phase50_skill_batch_live_guard failed")
            phase63_batch_command = [
                python,
                "scripts/validate_phase63_skill_batch_live.py",
                "--config-root",
                str(config_root),
                "--controller-base-url",
                args.controller_base_url,
                "--workflow-router-gateway-base-url",
                args.workflow_router_gateway_base_url,
                "--anythingllm-api-base-url",
                args.anythingllm_api_base_url,
                "--workspace",
                args.workspace,
                "--timeout-seconds",
                str(args.timeout_seconds),
                "--skip-promotion",
            ]
            for target_root in target_roots:
                phase63_batch_command.extend(["--target-root", target_root])
            if not contract.includes_anythingllm:
                phase63_batch_command.append("--skip-anythingllm")
            record = command_record(
                "phase63_batch_d_live_guard",
                phase63_batch_command,
                cwd=config_root,
                timeout_seconds=args.timeout_seconds,
            )
            commands.append(record)
            phase63_summary = json_summary_from_stdout(record["stdout_tail"], "PHASE63 LIVE SUMMARY ")
            if isinstance(phase63_summary.get("report_path"), str):
                generated_reports["batch_d_live_report"] = phase63_summary["report_path"]
            if record["status"] != "passed":
                errors.append("phase63_batch_d_live_guard failed")

    proof_validation = validate_release_gate_proofs(
        catalog=catalog,
        skill_eval_path=skill_eval_path,
        scale_path=scale_path,
        selector_scale_path=selector_scale_path,
        docs_index_path=docs_index_path,
        prompt_catalog_path=prompt_catalog_path,
        prompt_matrix_path=prompt_matrix_path,
    )
    for check in proof_validation:
        if check["status"] != "passed":
            errors.append(f"{check['label']} proof validation failed")

    after_hashes = watched_hashes(config_root)
    changed_files = changed_hashes(before_hashes, after_hashes)
    if changed_files:
        errors.append("release gate changed watched runtime files: " + ", ".join(changed_files))

    target_roots_for_report: list[str] = []
    if contract.live_guard_level != LiveGuardLevel.NONE:
        target_roots_for_report = args.target_roots or DEFAULT_TARGET_ROOTS
    report = {
        "kind": "skill_release_gate_report",
        "schema_version": 2,
        "run_id": run_id,
        "mode": mode,
        "profile": profile.value,
        "profile_contract": release_gate_profile_contract_json(profile),
        "status": "passed" if not errors else "failed",
        "created_at": utc_now(),
        "config_root": str(config_root),
        "catalog_summary": catalog,
        "prompt_catalog_summary": {
            "field_prompt_count": len(FIELD_PROMPTS),
            "prompt_catalog_case_count": prompt_catalog_report.get("summary", {}).get("case_count"),
            "prompt_catalog_refined_prompt_count": prompt_catalog_report.get("summary", {}).get("refined_prompt_count"),
            "prompt_matrix_case_count": len(prompt_matrix_report.get("cases") or []),
            "prompt_matrix_passed": prompt_matrix_report.get("summary", {}).get("passed"),
            "prompt_matrix_failed": prompt_matrix_report.get("summary", {}).get("failed"),
        },
        "generated_reports": generated_reports,
        "proof_validation": proof_validation,
        "commands": commands,
        "hash_summary": {
            "before": before_hashes,
            "after": after_hashes,
            "changed_files": changed_files,
        },
        "target_roots": target_roots_for_report,
        "errors": errors,
    }
    output_path = Path(args.output_path).resolve() if args.output_path else run_dir / "skill-release-gate.json"
    write_json(output_path, report)
    report["report_path"] = str(output_path)
    write_json(output_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline-only", action="store_true", help="Run only offline release gates. Default.")
    mode.add_argument("--live", action="store_true", help="Run offline gates plus Bash-hosted live guard without AnythingLLM.")
    mode.add_argument("--anythingllm", action="store_true", help="Run offline gates plus Bash-hosted live guard with AnythingLLM.")
    parser.add_argument(
        "--profile",
        choices=release_gate_profile_values(),
        default=None,
        help=(
            "Canonical release profile. Use offline, mutation, live-smoke, live-full, release-candidate, or v1.1-release-candidate. "
            "Legacy --offline-only/--live/--anythingllm flags remain supported as aliases."
        ),
    )
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-root", default=str(REPO_ROOT / DEFAULT_REPORT_DIR))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--controller-base-url", default="http://127.0.0.1:8400")
    parser.add_argument("--workflow-router-gateway-base-url", default="http://127.0.0.1:8500/v1")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default="my-workspace")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        profile = resolve_release_profile(args)
    except ValueError as exc:
        print(f"SKILL RELEASE GATE FAIL: {exc}", file=sys.stderr)
        return 2
    if release_gate_profile_contract(profile).includes_anythingllm and not os.environ.get("ANYTHINGLLM_API_KEY"):
        print(
            f"SKILL RELEASE GATE FAIL: ANYTHINGLLM_API_KEY is required for profile {profile.value}",
            file=sys.stderr,
        )
        return 1
    report = run_release_gate(args)
    print(f"SKILL RELEASE GATE REPORT {report['report_path']}")
    print(
        "SKILL RELEASE GATE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "mode": report["mode"],
                "profile": report["profile"],
                "skill_count": report["catalog_summary"]["skill_count"],
                "eval_case_count": report["catalog_summary"]["eval_case_count"],
                "workflow_count": report["catalog_summary"]["workflow_count"],
                "changed_files": report["hash_summary"]["changed_files"],
                "error_count": len(report["errors"]),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["errors"]:
        print("SKILL RELEASE GATE FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL RELEASE GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
