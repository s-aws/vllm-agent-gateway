import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.release_candidate_founder_trial_pack import (
    FounderTrialPackConfig,
    build_founder_trial_pack_report,
    read_json_object,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "release_candidate_founder_trial_pack_policy.json"
PACK_PATH = REPO_ROOT / "runtime" / "release_candidate_founder_trial_pack.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def pack() -> dict:
    return read_json_object(PACK_PATH)


def expected_phase_from_ref(value: str) -> int:
    name = Path(value).name
    digits = []
    for char in name.removeprefix("phase"):
        if not char.isdigit():
            break
        digits.append(char)
    return int("".join(digits))


def write_valid_proof_refs(root: Path, policy_payload: dict) -> None:
    import json

    for proof_ref in policy_payload["required_proof_refs"]:
        path = root / proof_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "test_proof_report",
                    "phase": expected_phase_from_ref(proof_ref),
                    "status": "passed",
                    "summary": {"validation_error_count": 0},
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )


def report_for(
    pack_payload: dict | None = None,
    policy_payload: dict | None = None,
    *,
    require_proof_artifacts: bool = True,
) -> dict:
    test_pack = PACK_PATH.read_text(encoding="utf-8")
    test_policy = POLICY_PATH.read_text(encoding="utf-8")
    if pack_payload is None and policy_payload is None:
        return build_founder_trial_pack_report(
            FounderTrialPackConfig(
                config_root=REPO_ROOT,
                output_path=REPO_ROOT / "runtime-state" / "phase195" / "test-report.json",
                markdown_output_path=None,
                require_proof_artifacts=require_proof_artifacts,
            )
        )
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        runtime = tmp_root / "runtime"
        runtime.mkdir(parents=True)
        (tmp_root / "README.release-candidate-founder-trial-pack.md").write_text("stub", encoding="utf-8")
        (tmp_root / "README.getting-started.md").write_text("stub", encoding="utf-8")
        (tmp_root / "README.external-tester-onboarding.md").write_text("stub", encoding="utf-8")
        (tmp_root / "docs" / "examples").mkdir(parents=True)
        (tmp_root / "docs" / "examples" / "release-candidate-founder-trial-pack.md").write_text("stub", encoding="utf-8")
        (runtime / "prompt_catalogs").mkdir()
        for relative in (
            "founder_test_prompt_pack.json",
            "prompt_catalogs/founder_field_v1.json",
        ):
            source = REPO_ROOT / "runtime" / relative
            destination = runtime / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        (runtime / "release_candidate_founder_trial_pack.json").write_text(
            json.dumps(pack_payload or json.loads(test_pack), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (runtime / "release_candidate_founder_trial_pack_policy.json").write_text(
            json.dumps(policy_payload or json.loads(test_policy), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        write_valid_proof_refs(tmp_root, policy_payload or json.loads(test_policy))
        return build_founder_trial_pack_report(
            FounderTrialPackConfig(
                config_root=tmp_root,
                output_path=tmp_root / "report.json",
                markdown_output_path=None,
                require_proof_artifacts=require_proof_artifacts,
            )
        )


def test_project_release_candidate_founder_trial_pack_passes() -> None:
    report = report_for()

    assert report["status"] == "passed"
    assert report["summary"]["prompt_case_count"] == 14
    assert report["summary"]["smoke_case_count"] == 4
    assert report["summary"]["expanded_case_count"] == 10
    assert report["summary"]["target_root_count"] == 2
    assert report["anythingllm"]["llm_base_url"] == "http://127.0.0.1:8500/v1"
    assert report["proof_artifact_mode"]["required_for_release"] is True
    assert all(case["prompt"] for case in report["selected_case_summaries"])
    assert report["feedback_capture"]["destination"] == "runtime-state/phase195/founder-feedback.jsonl"
    assert report["feedback_capture"]["allowed_classifications"] == ["answer_quality", "confusing", "routing"]
    assert report["fixture_safety"]["integrity_commands"]


def test_release_candidate_founder_trial_pack_rejects_disabled_proof_mode() -> None:
    report = report_for(require_proof_artifacts=False)

    assert report["status"] == "failed"
    assert any(error["id"] == "run.proof_artifacts.required" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_policy_rejects_wrong_anythingllm_target() -> None:
    broken = policy()
    broken["required_anythingllm"]["llm_base_url"] = "http://127.0.0.1:8300/v1"

    errors = validate_policy(broken)

    assert any(error["id"] == "policy.required_anythingllm.llm_base_url" for error in errors)


def test_release_candidate_founder_trial_pack_rejects_pack_wrong_anythingllm_target() -> None:
    broken = copy.deepcopy(pack())
    broken["anythingllm"]["llm_base_url"] = "http://127.0.0.1:8300/v1"

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.anythingllm.llm_base_url" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_required_prompt_case() -> None:
    broken = copy.deepcopy(pack())
    broken["trial_stages"][1]["prompt_case_ids"].remove("P02")

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.trial_stages.required_prompt_case_ids" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_unsafe_prompt_tag() -> None:
    broken = copy.deepcopy(pack())
    broken["trial_stages"][2]["prompt_case_ids"].append("P23")

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any("forbidden founder trial tag" in error["message"] for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_setup_command() -> None:
    broken = copy.deepcopy(pack())
    broken["trial_stages"][0]["commands"] = [
        {
            "command": "python3 scripts/run_first_time_user_doctor.py",
            "expected_marker": "FIRST TIME USER DOCTOR PASS",
            "failure_recovery": "fix failed checks",
            "required_before_prompt_testing": True,
        }
    ]

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.trial_stages.setup-readiness.commands" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_proof_artifact_flag() -> None:
    broken = copy.deepcopy(pack())
    for command in broken["trial_stages"][0]["commands"]:
        command["command"] = command["command"].replace(" --require-proof-artifacts", "")

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any("--require-proof-artifacts" in error["message"] for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_weak_feedback_template() -> None:
    broken = copy.deepcopy(pack())
    broken["feedback_capture"]["templates"][0]["template"] = "Record feedback: unclear."

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(str(error["id"]).startswith("pack.feedback_capture.") for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_unapproved_feedback_classification() -> None:
    broken = copy.deepcopy(pack())
    broken["feedback_capture"]["templates"][0]["classification"] = "general_note"

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"].endswith(".classification") for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_expanded_stage() -> None:
    broken = copy.deepcopy(pack())
    broken["trial_stages"] = [stage for stage in broken["trial_stages"] if stage["id"] != "expanded-read-only"]

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.trial_stages.expanded-read-only" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_unstructured_setup_command() -> None:
    broken = copy.deepcopy(pack())
    broken["trial_stages"][0]["commands"] = ["python3 scripts/run_first_time_user_doctor.py"]

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.trial_stages.setup-readiness.commands" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_feedback_destination() -> None:
    broken = copy.deepcopy(pack())
    broken["feedback_capture"]["destination"] = ""

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.feedback_capture.destination" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_fixture_integrity_commands() -> None:
    broken = copy.deepcopy(pack())
    broken["fixture_safety"]["integrity_commands"] = []

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.fixture_safety.integrity_commands" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_non_git_diff_command() -> None:
    broken = copy.deepcopy(pack())
    broken["fixture_safety"]["integrity_commands"] = [
        command
        for command in broken["fixture_safety"]["integrity_commands"]
        if not str(command["command"]).startswith("diff -u")
    ]

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.fixture_safety.non_git.diff" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_missing_anythingllm_recovery() -> None:
    broken = copy.deepcopy(pack())
    broken["recovery"].pop("anythingllm_down")

    report = report_for(broken)

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.recovery.anythingllm_down" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_require_proof_artifacts_fails_when_missing(tmp_path: Path) -> None:
    import json
    import shutil

    tmp_root = tmp_path / "project"
    shutil.copytree(REPO_ROOT / "runtime", tmp_root / "runtime")
    (tmp_root / "docs" / "examples").mkdir(parents=True)
    for doc in (
        "README.release-candidate-founder-trial-pack.md",
        "README.getting-started.md",
        "README.external-tester-onboarding.md",
    ):
        (tmp_root / doc).write_text("stub", encoding="utf-8")
    (tmp_root / "docs" / "examples" / "release-candidate-founder-trial-pack.md").write_text("stub", encoding="utf-8")
    pack_payload = pack()
    (tmp_root / "runtime" / "release_candidate_founder_trial_pack.json").write_text(
        json.dumps(pack_payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    report = build_founder_trial_pack_report(
        FounderTrialPackConfig(
            config_root=tmp_root,
            output_path=tmp_root / "report.json",
            markdown_output_path=None,
            require_proof_artifacts=True,
        )
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.proof_refs.artifact" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_failed_proof_artifact(tmp_path: Path) -> None:
    import json
    import shutil

    tmp_root = tmp_path / "project"
    shutil.copytree(REPO_ROOT / "runtime", tmp_root / "runtime")
    (tmp_root / "docs" / "examples").mkdir(parents=True)
    for doc in (
        "README.release-candidate-founder-trial-pack.md",
        "README.getting-started.md",
        "README.external-tester-onboarding.md",
    ):
        (tmp_root / doc).write_text("stub", encoding="utf-8")
    (tmp_root / "docs" / "examples" / "release-candidate-founder-trial-pack.md").write_text("stub", encoding="utf-8")
    test_policy = policy()
    write_valid_proof_refs(tmp_root, test_policy)
    first_ref = test_policy["required_proof_refs"][0]
    (tmp_root / first_ref).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "test_proof_report",
                "phase": expected_phase_from_ref(first_ref),
                "status": "failed",
                "summary": {"validation_error_count": 1},
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_founder_trial_pack_report(
        FounderTrialPackConfig(
            config_root=tmp_root,
            output_path=tmp_root / "report.json",
            markdown_output_path=None,
            require_proof_artifacts=True,
        )
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "pack.proof_refs.artifact_status" for error in report["validation_errors"])


def test_release_candidate_founder_trial_pack_rejects_invalid_feedback_record(tmp_path: Path) -> None:
    import json
    import shutil

    tmp_root = tmp_path / "project"
    shutil.copytree(REPO_ROOT / "runtime", tmp_root / "runtime")
    (tmp_root / "docs" / "examples").mkdir(parents=True)
    for doc in (
        "README.release-candidate-founder-trial-pack.md",
        "README.getting-started.md",
        "README.external-tester-onboarding.md",
    ):
        (tmp_root / doc).write_text("stub", encoding="utf-8")
    (tmp_root / "docs" / "examples" / "release-candidate-founder-trial-pack.md").write_text("stub", encoding="utf-8")
    write_valid_proof_refs(tmp_root, policy())
    feedback_path = tmp_root / "runtime-state" / "phase195" / "founder-feedback.jsonl"
    feedback_path.parent.mkdir(parents=True)
    feedback_path.write_text(
        json.dumps(
            {
                "case_id": "P01",
                "prompt": "prompt",
                "target_run_id": "bad-run-id",
                "classification": "unsupported",
                "severity": "advisory",
                "actual_response_excerpt": "excerpt",
                "expected_behavior": "expected",
                "fixture_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                "created_at": "2026-06-11T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_founder_trial_pack_report(
        FounderTrialPackConfig(
            config_root=tmp_root,
            output_path=tmp_root / "report.json",
            markdown_output_path=None,
        )
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "feedback_records.classification" for error in report["validation_errors"])
    assert any(error["id"] == "feedback_records.target_run_id" for error in report["validation_errors"])
