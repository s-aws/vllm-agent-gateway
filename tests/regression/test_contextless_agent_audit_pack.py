import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.contextless_agent_audit_pack import (
    ContextlessAgentAuditPackConfig,
    build_validation_report,
    run_contextless_agent_audit_pack,
    validate_policy,
    validate_sample_reports,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "contextless_agent_audit_pack_policy.json"
SAMPLE_REPORTS_PATH = REPO_ROOT / "runtime" / "contextless_agent_audit_pack_sample_reports.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def load_sample_reports() -> dict:
    return json.loads(SAMPLE_REPORTS_PATH.read_text(encoding="utf-8"))


def messages(errors: list[dict[str, str]]) -> str:
    return "\n".join(f"{item['path']}: {item['message']}" for item in errors)


def test_contextless_agent_audit_pack_policy_passes_contract() -> None:
    assert validate_policy(load_policy()) == []


def test_contextless_agent_audit_pack_sample_reports_pass_contract() -> None:
    assert validate_sample_reports(load_sample_reports(), load_policy()) == []


def test_contextless_agent_audit_pack_run_writes_validation_report(tmp_path: Path) -> None:
    report = run_contextless_agent_audit_pack(
        ContextlessAgentAuditPackConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase185-report.json",
        )
    )
    persisted = json.loads((tmp_path / "phase185-report.json").read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert persisted["summary"]["template_count"] == 4
    assert persisted["summary"]["process_step_count"] == 7
    assert persisted["summary"]["sample_report_count"] == 3
    assert persisted["summary"]["validation_error_count"] == 0


def test_contextless_agent_audit_pack_rejects_late_blind_baseline() -> None:
    policy = load_policy()
    samples = load_sample_reports()
    samples["reports"][0]["blind_baseline"]["created_at"] = "2026-06-11T00:00:00Z"

    errors = validate_sample_reports(samples, policy)

    assert "blind_baseline.created_at" in messages(errors)
    assert "must be before local_run.started_at" in messages(errors)


def test_contextless_agent_audit_pack_rejects_context_leakage() -> None:
    policy = load_policy()
    samples = load_sample_reports()
    samples["reports"][0]["blind_agent"]["fork_context"] = True
    samples["reports"][0]["blind_agent"]["local_model_output_seen"] = True

    errors = validate_sample_reports(samples, policy)

    assert "blind_agent.fork_context" in messages(errors)
    assert "blind_agent.local_model_output_seen" in messages(errors)


def test_contextless_agent_audit_pack_rejects_prompt_hash_mismatch() -> None:
    policy = load_policy()
    samples = load_sample_reports()
    samples["reports"][0]["local_run"]["prompt_hash"] = "d" * 64

    errors = validate_sample_reports(samples, policy)

    assert "local_run.prompt_hash" in messages(errors)
    assert "must match report.prompt_hash" in messages(errors)


def test_contextless_agent_audit_pack_rejects_hash_that_does_not_match_prompt_text() -> None:
    policy = load_policy()
    samples = load_sample_reports()
    samples["reports"][0]["prompt_hash"] = "a" * 64
    samples["reports"][0]["blind_baseline"]["prompt_hash"] = "a" * 64
    samples["reports"][0]["local_run"]["prompt_hash"] = "a" * 64
    samples["reports"][0]["comparison"]["prompt_hash"] = "a" * 64

    errors = validate_sample_reports(samples, policy)

    assert "prompt_hash" in messages(errors)
    assert "must be the sha256 hash of report.prompt" in messages(errors)


def test_contextless_agent_audit_pack_rejects_missing_output_expectations() -> None:
    policy = load_policy()
    samples = load_sample_reports()
    del samples["reports"][0]["blind_baseline"]["output_expectations"]

    errors = validate_sample_reports(samples, policy)

    assert "blind_baseline.output_expectations" in messages(errors)


def test_contextless_agent_audit_pack_rejects_missing_live_surface() -> None:
    policy = load_policy()
    samples = load_sample_reports()
    samples["reports"][0]["local_run"]["route_surfaces"] = ["workflow_router_gateway", "anythingllm"]

    errors = validate_sample_reports(samples, policy)

    assert "local_run.route_surfaces" in messages(errors)
    assert "must include all required local-stack surfaces" in messages(errors)


def test_contextless_agent_audit_pack_rejects_missing_response_route_and_fixture_proof() -> None:
    policy = load_policy()
    samples = load_sample_reports()
    local_run = samples["reports"][0]["local_run"]
    del local_run["response_ref"]
    del local_run["route_evidence"]
    local_run["fixture_mutation_proof"]["fixture_unchanged"] = False

    errors = validate_sample_reports(samples, policy)
    text = messages(errors)

    assert "local_run.response_text" in text
    assert "local_run.route_evidence" in text
    assert "local_run.fixture_mutation_proof.fixture_unchanged" in text


def test_contextless_agent_audit_pack_rejects_unbounded_recursion_policy() -> None:
    policy = load_policy()
    policy["recursion_limits"]["max_rounds"] = 99
    policy["recursion_limits"]["max_repair_cycles_per_issue"] = 99

    errors = validate_policy(policy)

    assert "recursion_limits.max_rounds" in messages(errors)
    assert "recursion_limits.max_repair_cycles_per_issue" in messages(errors)


def test_contextless_agent_audit_pack_rejects_missing_baseline_template() -> None:
    policy = load_policy()
    policy["prompt_templates"] = [
        template for template in policy["prompt_templates"] if template["id"] != "ideal_answer_baseline"
    ]

    errors = validate_policy(policy)

    assert "policy.prompt_templates" in messages(errors)


def test_contextless_agent_audit_pack_build_report_collects_policy_and_sample_errors() -> None:
    policy = copy.deepcopy(load_policy())
    samples = copy.deepcopy(load_sample_reports())
    policy["context_policy"]["fork_context"] = True
    samples["reports"][0]["closure"]["fixture_unchanged"] = False

    report = build_validation_report(
        config_root=REPO_ROOT,
        policy=policy,
        sample_reports=samples,
        policy_path=POLICY_PATH,
        sample_reports_path=SAMPLE_REPORTS_PATH,
    )

    assert report["status"] == "failed"
    assert report["summary"]["validation_error_count"] >= 2
    assert {item["source"] for item in report["validation_errors"]} == {"policy", "sample_reports"}
