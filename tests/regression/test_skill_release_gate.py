from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_skill_release_gate import (
    catalog_summary,
    release_gate_profile_contract,
    release_gate_profile_values,
    resolve_release_profile,
    validate_release_gate_proofs,
)
from vllm_agent_gateway.acceptance.profiles import LiveGuardLevel, ReleaseGateProfile


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


class Args:
    def __init__(
        self,
        *,
        profile: str | None = None,
        offline_only: bool = False,
        live: bool = False,
        anythingllm: bool = False,
    ) -> None:
        self.profile = profile
        self.offline_only = offline_only
        self.live = live
        self.anythingllm = anythingllm


def test_release_gate_profiles_are_distinct_and_ordered() -> None:
    assert release_gate_profile_values() == [
        "offline",
        "mutation",
        "live-smoke",
        "live-full",
        "release-candidate",
        "v1.1-release-candidate",
    ]
    offline = release_gate_profile_contract(ReleaseGateProfile.OFFLINE)
    mutation = release_gate_profile_contract(ReleaseGateProfile.MUTATION)
    live_smoke = release_gate_profile_contract(ReleaseGateProfile.LIVE_SMOKE)
    live_full = release_gate_profile_contract(ReleaseGateProfile.LIVE_FULL)
    release_candidate = release_gate_profile_contract(ReleaseGateProfile.RELEASE_CANDIDATE)
    v1_1_release_candidate = release_gate_profile_contract(ReleaseGateProfile.V1_1_RELEASE_CANDIDATE)

    assert not offline.includes_mutation
    assert mutation.includes_mutation
    assert live_smoke.live_guard_level == LiveGuardLevel.SMOKE
    assert live_full.live_guard_level == LiveGuardLevel.FULL
    assert release_candidate.includes_anythingllm
    assert release_candidate.final_gate
    assert v1_1_release_candidate.includes_anythingllm
    assert v1_1_release_candidate.final_gate


def test_release_gate_legacy_flags_map_to_profiles() -> None:
    assert resolve_release_profile(Args()) == ReleaseGateProfile.MUTATION
    assert resolve_release_profile(Args(offline_only=True)) == ReleaseGateProfile.MUTATION
    assert resolve_release_profile(Args(live=True)) == ReleaseGateProfile.LIVE_FULL
    assert resolve_release_profile(Args(anythingllm=True)) == ReleaseGateProfile.RELEASE_CANDIDATE
    assert resolve_release_profile(Args(profile="offline")) == ReleaseGateProfile.OFFLINE
    assert resolve_release_profile(Args(profile="live-smoke")) == ReleaseGateProfile.LIVE_SMOKE

    try:
        resolve_release_profile(Args(profile="offline", live=True))
    except ValueError as exc:
        assert "cannot be combined" in str(exc)
    else:
        raise AssertionError("expected conflicting profile flags to fail")


def test_skill_release_gate_catalog_summary_reports_current_registry_counts() -> None:
    summary = catalog_summary(REPO_ROOT)
    skills = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))["skills"]
    eval_cases = json.loads((REPO_ROOT / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))["cases"]
    workflows = json.loads((REPO_ROOT / "runtime" / "workflows.json").read_text(encoding="utf-8"))["workflows"]
    route_keys = {
        item["capability_contract"]["route_key"]
        for item in skills
        if isinstance(item.get("capability_contract"), dict)
    }
    validated_count = sum(1 for item in skills if item.get("eval_status") == "validated")

    assert summary["skill_count"] == len(skills)
    assert summary["eval_case_count"] == len(eval_cases)
    assert summary["route_key_count"] == len(route_keys)
    assert summary["workflow_count"] == len(workflows)
    assert summary["workflow_count"] >= 13
    assert summary["route_namespace_counts"]["code"] > 0
    assert summary["eval_status_counts"]["validated"] == validated_count
    assert "skill.update" in summary["workflow_ids"]


def test_skill_release_gate_proof_validation_rejects_missing_and_stale_reports(tmp_path: Path) -> None:
    catalog = {
        "skill_count": 42,
        "eval_case_count": 41,
        "route_key_count": 42,
    }
    stale_eval_report = tmp_path / "skill-evals.json"
    scale_report = tmp_path / "skill-scale.json"
    selector_report = tmp_path / "selector-scale.json"
    docs_report = tmp_path / "docs-index.json"
    prompt_catalog_report = tmp_path / "prompt-catalog.json"
    prompt_matrix_report = tmp_path / "prompt-matrix.json"
    write_json(
        stale_eval_report,
        {
            "status": "passed",
            "summary": {"case_count": 40, "failed_count": 0},
        },
    )
    write_json(
        scale_report,
        {
            "status": "passed",
            "summary": {
                "skill_count": 42,
                "eval_case_count": 41,
                "route_key_count": 42,
                "do_not_admit_count": 0,
            },
        },
    )
    write_json(
        selector_report,
        {
            "status": "passed",
            "summary": {
                "largest_skill_count": 10_000,
                "body_reads_during_selection": 0,
                "negative_fixture_count": 5,
                "negative_fixture_rejected_count": 5,
            },
        },
    )
    write_json(docs_report, {"status": "passed", "orphaned_docs": []})
    write_json(
        prompt_catalog_report,
        {
            "status": "passed",
            "summary": {"case_count": 34, "problem_count": 0, "refined_prompt_count": 16},
        },
    )
    write_json(
        prompt_matrix_report,
        {
            "status": "passed",
            "summary": {"passed": 50, "failed": 0},
            "cases": [{"case_id": f"P{i:02d}"} for i in range(1, 35)],
        },
    )

    checks = validate_release_gate_proofs(
        catalog=catalog,
        skill_eval_path=stale_eval_report,
        scale_path=scale_report,
        selector_scale_path=selector_report,
        docs_index_path=docs_report,
        prompt_catalog_path=prompt_catalog_report,
        prompt_matrix_path=prompt_matrix_report,
    )

    by_label = {check["label"]: check for check in checks}
    assert by_label["skill_eval_report"]["status"] == "failed"
    assert "case_count does not match" in by_label["skill_eval_report"]["errors"][0]

    missing_checks = validate_release_gate_proofs(
        catalog=catalog,
        skill_eval_path=tmp_path / "missing-skill-evals.json",
        scale_path=scale_report,
        selector_scale_path=selector_report,
        docs_index_path=docs_report,
        prompt_catalog_path=tmp_path / "missing-prompt-catalog.json",
        prompt_matrix_path=tmp_path / "missing-prompt-matrix.json",
    )
    missing_by_label = {check["label"]: check for check in missing_checks}
    assert missing_by_label["skill_eval_report"]["status"] == "failed"
    assert missing_by_label["skill_eval_report"]["errors"] == ["missing proof file"]
    assert missing_by_label["prompt_catalog_report"]["status"] == "failed"
    assert missing_by_label["prompt_catalog_report"]["errors"] == ["missing proof file"]
    assert missing_by_label["prompt_matrix_report"]["status"] == "failed"
    assert missing_by_label["prompt_matrix_report"]["errors"] == ["missing proof file"]


def test_skill_release_gate_prompt_matrix_proof_rejects_failed_or_truncated_report(tmp_path: Path) -> None:
    catalog = {
        "skill_count": 42,
        "eval_case_count": 41,
        "route_key_count": 42,
    }
    skill_eval_report = tmp_path / "skill-evals.json"
    scale_report = tmp_path / "skill-scale.json"
    selector_report = tmp_path / "selector-scale.json"
    docs_report = tmp_path / "docs-index.json"
    prompt_catalog_report = tmp_path / "prompt-catalog.json"
    prompt_matrix_report = tmp_path / "prompt-matrix.json"
    write_json(skill_eval_report, {"status": "passed", "summary": {"case_count": 41, "failed_count": 0}})
    write_json(
        scale_report,
        {
            "status": "passed",
            "summary": {
                "skill_count": 42,
                "eval_case_count": 41,
                "route_key_count": 42,
                "do_not_admit_count": 0,
            },
        },
    )
    write_json(
        selector_report,
        {
            "status": "passed",
            "summary": {
                "largest_skill_count": 10_000,
                "body_reads_during_selection": 0,
                "negative_fixture_count": 5,
                "negative_fixture_rejected_count": 5,
            },
        },
    )
    write_json(docs_report, {"status": "passed", "orphaned_docs": []})
    write_json(
        prompt_catalog_report,
        {
            "status": "passed",
            "summary": {"case_count": 34, "problem_count": 0, "refined_prompt_count": 16},
        },
    )
    write_json(prompt_matrix_report, {"status": "failed", "summary": {"passed": 10, "failed": 1}, "cases": []})

    checks = validate_release_gate_proofs(
        catalog=catalog,
        skill_eval_path=skill_eval_report,
        scale_path=scale_report,
        selector_scale_path=selector_report,
        docs_index_path=docs_report,
        prompt_catalog_path=prompt_catalog_report,
        prompt_matrix_path=prompt_matrix_report,
    )

    by_label = {check["label"]: check for check in checks}
    assert by_label["prompt_matrix_report"]["status"] == "failed"
    assert "status is not passed" in by_label["prompt_matrix_report"]["errors"][0]
    assert any("full field prompt catalog" in item for item in by_label["prompt_matrix_report"]["errors"])
