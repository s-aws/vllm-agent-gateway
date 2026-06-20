"""EIG baseline-candidate promotion-readiness gate."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import (
    BaselineCorpusConfig,
    object_list,
    read_json_object,
    resolve_path,
    run_baseline_corpus_governance,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.acceptance.baseline_corpus_promotion_rules import REQUIRED_EVIDENCE
from vllm_agent_gateway.acceptance.eig_baseline_candidate_intake import (
    EIGBaselineCandidateIntakeConfig,
    run_eig_baseline_candidate_intake,
)
from vllm_agent_gateway.acceptance.eig_baseline_candidate_live_replay import (
    EIGBaselineCandidateLiveReplayConfig,
    run_eig_baseline_candidate_live_replay,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_baseline_candidate_promotion_readiness_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-baseline-candidate-promotion-readiness"
REQUIRED_MILESTONES = {"M2", "M9", "M14", "M19", "M25", "M31", "M36"}
REQUIRED_SURFACES = {"workflow_router_gateway", "anythingllm"}


class EIGBaselineCandidatePromotionReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGBaselineCandidatePromotionReadinessConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    skip_github: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-baseline-candidate-promotion-readiness-{utc_timestamp()}.json"


def artifact_hash_errors(
    *,
    config_root: Path,
    prefix: str,
    path_value: object,
    hash_value: object,
) -> list[str]:
    if not isinstance(path_value, str) or not path_value.strip():
        return [f"{prefix}.path is required"]
    if not isinstance(hash_value, str) or len(hash_value) != 64:
        return [f"{prefix}.sha256 must be a 64-character hash"]
    path = resolve_path(config_root, path_value)
    if not path.is_file():
        return [f"{prefix}.path does not exist: {path_value}"]
    actual = sha256_file(path)
    if actual != hash_value:
        return [f"{prefix}.sha256 is stale for {path_value}"]
    return []


def gh_pr_json(config_root: Path, pr_number: int) -> dict[str, Any]:
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
    value = json.loads(result.stdout.lstrip("\ufeff"))
    return value if isinstance(value, dict) else {}


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "eig_baseline_candidate_promotion_readiness_policy":
        errors.append("policy.kind must be eig_baseline_candidate_promotion_readiness_policy")
    if policy.get("phase") != 311:
        errors.append("policy.phase must be 311")
    if set(string_list(policy.get("required_milestones"))) != REQUIRED_MILESTONES:
        errors.append("policy.required_milestones must match Phase 311 milestones")

    for field in ("candidate_source", "live_replay_source", "baseline_corpus"):
        source = policy.get(field) if isinstance(policy.get(field), dict) else {}
        errors.extend(
            artifact_hash_errors(
                config_root=config_root,
                prefix=field,
                path_value=source.get("path"),
                hash_value=source.get("sha256"),
            )
        )

    candidate_source = policy.get("candidate_source") if isinstance(policy.get("candidate_source"), dict) else {}
    if candidate_source.get("expected_candidate_count") != 2:
        errors.append("candidate_source.expected_candidate_count must be 2")
    if candidate_source.get("expected_total_source_case_count") != 7:
        errors.append("candidate_source.expected_total_source_case_count must be 7")

    live_source = policy.get("live_replay_source") if isinstance(policy.get("live_replay_source"), dict) else {}
    if live_source.get("expected_candidate_count") != 2:
        errors.append("live_replay_source.expected_candidate_count must be 2")
    if live_source.get("expected_total_source_case_count") != 7:
        errors.append("live_replay_source.expected_total_source_case_count must be 7")
    if live_source.get("expected_live_result_count") != 14:
        errors.append("live_replay_source.expected_live_result_count must be 14")
    if set(string_list(live_source.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append("live_replay_source.required_surfaces must be workflow_router_gateway and anythingllm")

    corpus_source = policy.get("baseline_corpus") if isinstance(policy.get("baseline_corpus"), dict) else {}
    if corpus_source.get("expected_entry_count") != 5:
        errors.append("baseline_corpus.expected_entry_count must be 5")

    promotion_policy = policy.get("promotion_policy") if isinstance(policy.get("promotion_policy"), dict) else {}
    if set(string_list(promotion_policy.get("required_evidence"))) != REQUIRED_EVIDENCE:
        errors.append("promotion_policy.required_evidence must match baseline corpus promotion evidence")
    for key in (
        "auto_promote_allowed",
        "stable_corpus_mutation_allowed",
    ):
        if promotion_policy.get(key) is not False:
            errors.append(f"promotion_policy.{key} must be false")
    for key in (
        "stable_corpus_update_requires_separate_phase",
        "founder_approval_required_for_promotion",
        "committed_evidence_refs_required_for_promotion",
    ):
        if promotion_policy.get(key) is not True:
            errors.append(f"promotion_policy.{key} must be true")

    pr = policy.get("pr_evidence") if isinstance(policy.get("pr_evidence"), dict) else {}
    if pr.get("number") != 1:
        errors.append("pr_evidence.number must be 1")
    if pr.get("required_state") != "OPEN":
        errors.append("pr_evidence.required_state must be OPEN")
    if pr.get("expected_head_ref") != "codex/eig-stable-handoff":
        errors.append("pr_evidence.expected_head_ref must be codex/eig-stable-handoff")
    if pr.get("expected_base_ref") != "main":
        errors.append("pr_evidence.expected_base_ref must be main")
    if not string_list(pr.get("required_body_markers")):
        errors.append("pr_evidence.required_body_markers must be non-empty")
    return errors


def existing_corpus_entry_ids(corpus: dict[str, Any]) -> set[str]:
    return {str(entry.get("entry_id")) for entry in object_list(corpus.get("entries")) if isinstance(entry.get("entry_id"), str)}


def pr_evidence_summary(
    *,
    policy: dict[str, Any],
    config_root: Path,
    skip_github: bool,
    errors: list[str],
) -> dict[str, Any]:
    pr_policy = policy.get("pr_evidence") if isinstance(policy.get("pr_evidence"), dict) else {}
    markers = string_list(pr_policy.get("required_body_markers"))
    pr = {
        "number": pr_policy.get("number"),
        "state": pr_policy.get("required_state"),
        "mergeStateStatus": "SKIPPED",
        "headRefName": pr_policy.get("expected_head_ref"),
        "baseRefName": pr_policy.get("expected_base_ref"),
        "url": None,
        "body": "\n".join(markers),
    }
    if not skip_github:
        try:
            pr = gh_pr_json(config_root, int(pr_policy.get("number") or 0))
        except Exception as exc:  # pragma: no cover - depends on GitHub CLI availability.
            errors.append(f"gh pr view failed: {type(exc).__name__}: {exc}")
    body = pr.get("body") if isinstance(pr.get("body"), str) else ""
    missing_markers = [marker for marker in markers if marker not in body]
    if pr.get("state") != pr_policy.get("required_state"):
        errors.append("pr_evidence.state must be OPEN")
    if pr.get("headRefName") != pr_policy.get("expected_head_ref"):
        errors.append("pr_evidence.head_ref must match expected head")
    if pr.get("baseRefName") != pr_policy.get("expected_base_ref"):
        errors.append("pr_evidence.base_ref must match expected base")
    if missing_markers:
        errors.append("pr_evidence.required_body_markers missing: " + ", ".join(missing_markers))
    return {
        "number": pr.get("number"),
        "state": pr.get("state"),
        "merge_state_status": pr.get("mergeStateStatus"),
        "head_ref": pr.get("headRefName"),
        "base_ref": pr.get("baseRefName"),
        "url": pr.get("url"),
        "missing_marker_count": len(missing_markers),
        "missing_markers": missing_markers,
        "github_checked": not skip_github,
    }


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": report.get("kind"),
        "phase": report.get("phase"),
        "status": report.get("status"),
        "summary": report.get("summary"),
        "report_path": report.get("report_path"),
    }


def run_eig_baseline_candidate_promotion_readiness(
    config: EIGBaselineCandidatePromotionReadinessConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy, config_root=config_root)
    report_dir = output_path.parent

    phase307 = run_eig_baseline_candidate_intake(
        EIGBaselineCandidateIntakeConfig(
            config_root=config_root,
            output_path=report_dir / f"{output_path.stem}-phase307-intake.json",
        )
    )
    phase308_static = run_eig_baseline_candidate_live_replay(
        EIGBaselineCandidateLiveReplayConfig(
            config_root=config_root,
            output_path=report_dir / f"{output_path.stem}-phase308-static.json",
            run_live=False,
        )
    )
    baseline = run_baseline_corpus_governance(
        BaselineCorpusConfig(
            config_root=config_root,
            output_path=report_dir / f"{output_path.stem}-baseline-corpus.json",
        )
    )
    if phase307.get("status") != EIGBaselineCandidatePromotionReadinessStatus.PASSED.value:
        errors.append("phase307 candidate intake must pass")
    if phase308_static.get("status") != EIGBaselineCandidatePromotionReadinessStatus.PASSED.value:
        errors.append("phase308 static preflight must pass")
    if baseline.get("status") != EIGBaselineCandidatePromotionReadinessStatus.PASSED.value:
        errors.append("baseline corpus governance must pass")

    pr_summary = pr_evidence_summary(
        policy=policy,
        config_root=config_root,
        skip_github=config.skip_github,
        errors=errors,
    )

    corpus_path = (policy.get("baseline_corpus") or {}).get("path") if isinstance(policy.get("baseline_corpus"), dict) else None
    corpus = read_json_object(resolve_path(config_root, str(corpus_path))) if isinstance(corpus_path, str) else {}
    stable_entry_ids = existing_corpus_entry_ids(corpus)
    candidates = []
    missing_union: set[str] = set()
    phase307_evidence = phase307.get("evidence") if isinstance(phase307.get("evidence"), dict) else {}
    for candidate in object_list(phase307_evidence.get("candidates")):
        missing = sorted(REQUIRED_EVIDENCE)
        missing_union.update(missing)
        proposed_entry_id = candidate.get("proposed_entry_id")
        already_promoted = isinstance(proposed_entry_id, str) and proposed_entry_id in stable_entry_ids
        if already_promoted:
            errors.append(f"candidate {candidate.get('candidate_id')} proposed entry already exists in stable corpus")
        candidates.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "proposed_entry_id": proposed_entry_id,
                "source_case_count": candidate.get("source_case_count"),
                "decision_status": "blocked_pending_evidence",
                "missing_evidence": missing,
                "already_in_stable_corpus": already_promoted,
                "promotion_allowed": False,
            }
        )

    status = EIGBaselineCandidatePromotionReadinessStatus.PASSED.value if not errors else EIGBaselineCandidatePromotionReadinessStatus.FAILED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_baseline_candidate_promotion_readiness_report",
        "phase": 311,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "status": status,
            "candidate_count": len(candidates),
            "blocked_candidate_count": len([item for item in candidates if item["decision_status"] == "blocked_pending_evidence"]),
            "approved_candidate_count": 0,
            "promoted_candidate_count": 0,
            "stable_corpus_entry_count": len(stable_entry_ids),
            "stable_corpus_mutated": False,
            "stable_corpus_mutation_allowed": False,
            "stable_corpus_update_requires_separate_phase": True,
            "auto_promote_allowed": False,
            "founder_approval_recorded": False,
            "promotion_allowed": False,
            "missing_evidence": sorted(missing_union),
            "pr_evidence_checked": not config.skip_github,
            "validation_error_count": len(errors),
            "phase312_ready": status == EIGBaselineCandidatePromotionReadinessStatus.PASSED.value,
        },
        "candidates": candidates,
        "phase307_candidate_intake": compact_report(phase307),
        "phase308_static_preflight": compact_report(phase308_static),
        "baseline_corpus": compact_report(baseline),
        "pr_evidence": pr_summary,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
