from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.release_notes import (
    DEFAULT_POLICY_PATH,
    build_release_notes_report,
    read_json_object,
    validate_policy,
    validate_release_notes_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
NOTES_PATH = REPO_ROOT / "README.release-notes.md"
ROOT_README_PATH = REPO_ROOT / "README.md"
DOCS_INDEX_PATH = REPO_ROOT / "docs" / "README.md"
EXAMPLES_INDEX_PATH = REPO_ROOT / "docs" / "examples" / "README.md"
STABLE_RELEASE_PATH = (
    REPO_ROOT / "runtime-state" / "stable-chat-quality-release" / "phase130" / "phase130-stable-chat-quality-release-report.json"
)
SNAPSHOT_PATH = (
    REPO_ROOT / "runtime-state" / "chat-quality-release-snapshot" / "phase136" / "phase136-chat-quality-release-snapshot.json"
)
NATURAL_OUTPUT_PATH = (
    REPO_ROOT
    / "runtime-state"
    / "natural-output-format-preference"
    / "phase144"
    / "phase144-natural-output-format-preference-live.json"
)
FEEDBACK_DASHBOARD_PATH = (
    REPO_ROOT
    / "runtime-state"
    / "founder-feedback-triage-dashboard"
    / "phase145"
    / "phase145-founder-feedback-triage-dashboard.json"
)
CLOSURE_PATH = (
    REPO_ROOT
    / "runtime-state"
    / "stable-release-blocker-closure"
    / "phase131"
    / "phase131-stable-release-blocker-closure-report.json"
)
HEALTH_DRIFT_PATH = (
    REPO_ROOT
    / "runtime-state"
    / "gateway-anythingllm-health-drift"
    / "phase141"
    / "phase141-health-drift-report.json"
)
PROMPT_PACK_PATH = REPO_ROOT / "runtime" / "founder_test_prompt_pack.json"
PROMPT_CATALOG_PATH = REPO_ROOT / "runtime" / "prompt_catalogs" / "founder_field_v1.json"
FOUNDER_SMOKE_PATH = REPO_ROOT / "runtime-state" / "founder-field-tests" / "phase134-founder-smoke.json"
STABLE_PROOF_PATH = REPO_ROOT / "runtime" / "release_proofs" / "v1-1-release-candidate-stable-proof.json"
ADVANCED_READINESS_PATH = (
    REPO_ROOT / "runtime-state" / "advanced-refactor-readiness" / "phase105-readiness.json"
)


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def stable_release() -> dict[str, Any]:
    return read_json_object(STABLE_RELEASE_PATH)


def snapshot() -> dict[str, Any]:
    return read_json_object(SNAPSHOT_PATH)


def natural_output() -> dict[str, Any]:
    return read_json_object(NATURAL_OUTPUT_PATH)


def feedback_dashboard() -> dict[str, Any]:
    return read_json_object(FEEDBACK_DASHBOARD_PATH)


def blocker_closure() -> dict[str, Any]:
    return read_json_object(CLOSURE_PATH)


def health_drift() -> dict[str, Any]:
    return read_json_object(HEALTH_DRIFT_PATH)


def prompt_pack() -> dict[str, Any]:
    return read_json_object(PROMPT_PACK_PATH)


def prompt_catalog() -> dict[str, Any]:
    return read_json_object(PROMPT_CATALOG_PATH)


def founder_smoke() -> dict[str, Any]:
    return read_json_object(FOUNDER_SMOKE_PATH)


def stable_proof() -> dict[str, Any]:
    return read_json_object(STABLE_PROOF_PATH)


def advanced_readiness() -> dict[str, Any]:
    return read_json_object(ADVANCED_READINESS_PATH)


def project_report(
    *,
    policy_payload: dict[str, Any] | None = None,
    text: str | None = None,
    root_text: str | None = None,
    docs_text: str | None = None,
    examples_text: str | None = None,
    stable_payload: dict[str, Any] | None = None,
    snapshot_payload: dict[str, Any] | None = None,
    natural_payload: dict[str, Any] | None = None,
    feedback_payload: dict[str, Any] | None = None,
    closure_payload: dict[str, Any] | None = None,
    health_payload: dict[str, Any] | None = None,
    prompt_pack_payload: dict[str, Any] | None = None,
    prompt_catalog_payload: dict[str, Any] | None = None,
    founder_smoke_payload: dict[str, Any] | None = None,
    stable_proof_payload: dict[str, Any] | None = None,
    advanced_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_release_notes_report(
        policy=policy_payload or policy(),
        notes_text=read_text(NOTES_PATH) if text is None else text,
        root_readme_text=read_text(ROOT_README_PATH) if root_text is None else root_text,
        docs_index_text=read_text(DOCS_INDEX_PATH) if docs_text is None else docs_text,
        examples_index_text=read_text(EXAMPLES_INDEX_PATH) if examples_text is None else examples_text,
        stable_release=stable_payload or stable_release(),
        snapshot=snapshot_payload or snapshot(),
        natural_output=natural_payload or natural_output(),
        feedback_dashboard=feedback_payload or feedback_dashboard(),
        blocker_closure=closure_payload or blocker_closure(),
        health_drift=health_payload or health_drift(),
        prompt_pack=prompt_pack_payload or prompt_pack(),
        prompt_catalog=prompt_catalog_payload or prompt_catalog(),
        founder_smoke=founder_smoke_payload or founder_smoke(),
        stable_proof=stable_proof_payload or stable_proof(),
        advanced_readiness=advanced_payload or advanced_readiness(),
        policy_path=POLICY_PATH,
        notes_path=NOTES_PATH,
        root_readme_path=ROOT_README_PATH,
        docs_index_path=DOCS_INDEX_PATH,
        examples_index_path=EXAMPLES_INDEX_PATH,
        stable_release_path=STABLE_RELEASE_PATH,
        snapshot_path=SNAPSHOT_PATH,
        natural_output_path=NATURAL_OUTPUT_PATH,
        feedback_dashboard_path=FEEDBACK_DASHBOARD_PATH,
        blocker_closure_path=CLOSURE_PATH,
        health_drift_path=HEALTH_DRIFT_PATH,
        prompt_pack_path=PROMPT_PACK_PATH,
        prompt_catalog_path=PROMPT_CATALOG_PATH,
        founder_smoke_path=FOUNDER_SMOKE_PATH,
        stable_proof_path=STABLE_PROOF_PATH,
        advanced_readiness_path=ADVANCED_READINESS_PATH,
    )


def validate_report(report: dict[str, Any], *, text: str | None = None) -> list[str]:
    return validate_release_notes_report(
        report,
        policy=policy(),
        notes_text=read_text(NOTES_PATH) if text is None else text,
        root_readme_text=read_text(ROOT_README_PATH),
        docs_index_text=read_text(DOCS_INDEX_PATH),
        examples_index_text=read_text(EXAMPLES_INDEX_PATH),
        stable_release=stable_release(),
        snapshot=snapshot(),
        natural_output=natural_output(),
        feedback_dashboard=feedback_dashboard(),
        blocker_closure=blocker_closure(),
        health_drift=health_drift(),
        prompt_pack=prompt_pack(),
        prompt_catalog=prompt_catalog(),
        founder_smoke=founder_smoke(),
        stable_proof=stable_proof(),
        advanced_readiness=advanced_readiness(),
        policy_path=POLICY_PATH,
        notes_path=NOTES_PATH,
        root_readme_path=ROOT_README_PATH,
        docs_index_path=DOCS_INDEX_PATH,
        examples_index_path=EXAMPLES_INDEX_PATH,
        stable_release_path=STABLE_RELEASE_PATH,
        snapshot_path=SNAPSHOT_PATH,
        natural_output_path=NATURAL_OUTPUT_PATH,
        feedback_dashboard_path=FEEDBACK_DASHBOARD_PATH,
        blocker_closure_path=CLOSURE_PATH,
        health_drift_path=HEALTH_DRIFT_PATH,
        prompt_pack_path=PROMPT_PACK_PATH,
        prompt_catalog_path=PROMPT_CATALOG_PATH,
        founder_smoke_path=FOUNDER_SMOKE_PATH,
        stable_proof_path=STABLE_PROOF_PATH,
        advanced_readiness_path=ADVANCED_READINESS_PATH,
    )


def test_project_release_notes_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_release_notes_pass_current_evidence() -> None:
    report = project_report()

    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["summary"]["error_count"] == 0
    assert report["source_refs"]["release_notes"]["sha256"]
    assert report["summary"]["stable_gate_count"] == 11
    assert report["summary"]["health_failed_check_count"] == 0


def test_release_notes_reject_missing_advanced_refactor_boundary() -> None:
    text = read_text(NOTES_PATH).replace("Advanced broad refactor orchestration is not released.", "")

    report = project_report(text=text)

    assert report["status"] == "failed"
    assert any("Advanced broad refactor orchestration is not released" in error for error in report["errors"])


def test_release_notes_reject_forbidden_overclaim() -> None:
    text = read_text(NOTES_PATH) + "\nThis release works on any repository.\n"

    report = project_report(text=text)

    assert report["status"] == "failed"
    assert any("forbidden claim marker" in error for error in report["errors"])


def test_release_notes_reject_blocked_release_evidence() -> None:
    stable = copy.deepcopy(stable_release())
    stable["readiness"] = "blocked"
    stable["summary"]["blocker_count"] = 1

    report = project_report(stable_payload=stable)

    assert report["status"] == "failed"
    assert any("readiness must be ready_for_founder_testing" in error for error in report["errors"])
    assert any("blocker_count must be 0" in error for error in report["errors"])


def test_release_notes_reject_natural_output_mutation_proof() -> None:
    natural = copy.deepcopy(natural_output())
    natural["mutation_proof"]["runtime_changed_files"] = ["runtime/workflows.json"]

    report = project_report(natural_payload=natural)

    assert report["status"] == "failed"
    assert any("runtime_changed_files must be empty" in error for error in report["errors"])


def test_release_notes_reject_health_drift_failure() -> None:
    health = copy.deepcopy(health_drift())
    health["summary"]["failed_check_count"] = 1

    report = project_report(health_payload=health)

    assert report["status"] == "failed"
    assert any("failed_check_count must be 0" in error for error in report["errors"])


def test_release_notes_reject_founder_prompt_pack_count_drift() -> None:
    pack = copy.deepcopy(prompt_pack())
    pack["tiers"][1]["case_ids"] = pack["tiers"][1]["case_ids"][:-1]

    report = project_report(prompt_pack_payload=pack)

    assert report["status"] == "failed"
    assert any("expanded_read_only case count must be 10" in error for error in report["errors"])


def test_release_notes_reject_stable_proof_boundary_drift() -> None:
    proof = copy.deepcopy(stable_proof())
    proof["known_boundary"] = "Everything is released."

    report = project_report(stable_proof_payload=proof)

    assert report["status"] == "failed"
    assert any("must defer advanced broad refactor orchestration" in error for error in report["errors"])


def test_release_notes_reject_advanced_refactor_stable_promotion() -> None:
    advanced = copy.deepcopy(advanced_readiness())
    advanced["summary"]["stable_promotion_enabled"] = True

    report = project_report(advanced_payload=advanced)

    assert report["status"] == "failed"
    assert any("stable_promotion_enabled must be false" in error for error in report["errors"])


def test_release_notes_reject_missing_root_readme_link() -> None:
    root_text = read_text(ROOT_README_PATH).replace("[README.release-notes.md](README.release-notes.md)", "")

    report = project_report(root_text=root_text)

    assert report["status"] == "failed"
    assert "root README must link README.release-notes.md" in report["errors"]


def test_release_notes_report_rejects_hidden_summary_change() -> None:
    report = project_report()
    report["summary"]["error_count"] = 99

    errors = validate_report(report)

    assert "report.summary must match rebuilt release notes report" in errors
