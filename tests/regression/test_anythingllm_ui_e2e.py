from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.anythingllm_ui_e2e import (
    DEFAULT_MARKERS,
    UI_PROMPT_CASES,
    UiPromptTargetRootMode,
    api_base_for_ui,
    build_electron_require_shim,
    execution_target_roots_for_prompt_case,
    free_port,
    host_path,
    ignored_request_failures,
    json_request,
    load_ui_prompt_cases,
    marker_hits,
    non_ignored_request_failures,
    prompt_for_target,
    screenshot_status,
    segment_after_new_tag,
    semantic_status_for_segment,
    start_static_server,
    ui_case_passed,
    usefulness_status_for_segment,
    validate_ui_prompt_catalog,
    wait_for_http,
)

from vllm_agent_gateway.acceptance.anythingllm_answer_usefulness import (
    DEFAULT_CONTRACT_PATH,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "runtime" / "anythingllm_ui_prompt_cases.json"


def load_catalog() -> dict[str, object]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_answer_usefulness_contract() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_CONTRACT_PATH).read_text(encoding="utf-8"))


def test_segment_after_new_tag_ignores_old_chat_history_markers() -> None:
    old_history = "workflow_router.plan completed\nselected_workflow: code_investigation.plan\nrun_id:\nAnswer:"
    tag = "phase71-ui-e2e-test"
    new_response = "user prompt " + tag + "\n\nassistant response\nworkflow_router.plan completed\nAnswer:"
    segment = segment_after_new_tag(old_history + "\n" + new_response, tag, len(old_history))

    hits = marker_hits(segment)

    assert hits["workflow_router.plan completed"] is True
    selected_hits = marker_hits(segment, ("selected_workflow: code_investigation.plan",))
    assert selected_hits["selected_workflow: code_investigation.plan"] is False
    assert "phase71-ui-e2e-test" not in segment


def test_ui_case_passed_requires_markers_and_stream_chat() -> None:
    assert ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "stream_chat_seen": True,
            "parsed_run_id": "workflow-router-test",
        }
    )
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "stream_chat_seen": False,
            "parsed_run_id": "workflow-router-test",
        }
    )
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {"workflow_router.plan completed": True},
            "stream_chat_seen": True,
            "parsed_run_id": "workflow-router-test",
        }
    )
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "stream_chat_seen": True,
        }
    )


def test_ui_case_passed_requires_semantic_markers_and_rejects_wrong_answer() -> None:
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "semantic_marker_hits_after_tag": {"Beginning point:": False},
            "rejected_marker_hits_after_tag": {},
            "stream_chat_seen": True,
            "parsed_run_id": "workflow-router-test",
        }
    )
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "semantic_marker_hits_after_tag": {"Beginning point:": True},
            "rejected_marker_hits_after_tag": {"Entrypoints:": True},
            "stream_chat_seen": True,
            "parsed_run_id": "workflow-router-test",
        }
    )


def test_ui_case_passed_uses_case_transport_markers_for_no_target_cases() -> None:
    assert ui_case_passed(
        {
            "transport_markers": [
                "workflow_router.plan completed",
                "Result:",
                "Summary:",
                "run_id:",
                "Run record:",
            ],
            "marker_hits_after_tag": {
                "workflow_router.plan completed": True,
                "Result:": True,
                "Summary:": True,
                "run_id:": True,
                "Run record:": True,
                "Artifacts:": False,
            },
            "semantic_marker_hits_after_tag": {"Selected workflow: none": True},
            "rejected_marker_hits_after_tag": {"Artifacts:": False},
            "ordered_marker_errors": [],
            "stream_chat_seen": True,
            "parsed_run_id": "workflow-router-general-test",
        }
    )


def test_ui_case_passed_rejects_ordered_marker_error() -> None:
    assert not ui_case_passed(
        {
            "transport_markers": ["workflow_router.plan completed"],
            "marker_hits_after_tag": {"workflow_router.plan completed": True},
            "semantic_marker_hits_after_tag": {"Answer:": True},
            "rejected_marker_hits_after_tag": {},
            "ordered_marker_errors": ["ordered marker 'Answer:' missing after index 20"],
            "stream_chat_seen": True,
            "parsed_run_id": "workflow-router-general-test",
        }
    )


def test_ui_case_passed_rejects_failed_usefulness_or_missing_screenshot() -> None:
    base = {
        "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
        "semantic_marker_hits_after_tag": {"Code Quality Review:": True},
        "rejected_marker_hits_after_tag": {},
        "stream_chat_seen": True,
        "parsed_run_id": "workflow-router-test",
    }

    assert not ui_case_passed(
        {
            **base,
            "answer_usefulness": {"usefulness_status": "failed"},
        }
    )
    assert not ui_case_passed(
        {
            **base,
            "screenshots": {"status": "failed"},
        }
    )


def test_l1_001_semantic_contract_rejects_old_entrypoint_answer() -> None:
    l1_001 = next(case for case in UI_PROMPT_CASES if case.case_id == "L1-001")
    wrong_segment = (
        "workflow_router.plan completed\n"
        "selected_workflow: code_investigation.plan\n"
        "run_id: workflow-router-test\n"
        "Answer:\n"
        "Entrypoints: main.py:65 (python_main_guard): python main.py\n"
    )

    status = semantic_status_for_segment(wrong_segment, l1_001)

    assert status["semantic_status"] == "failed"
    assert "Beginning point:" in status["missing_required_markers"]
    assert "Entrypoints:" in status["rejected_markers_present"]


def test_l1_001_semantic_contract_accepts_beginning_point_answer() -> None:
    l1_001 = next(case for case in UI_PROMPT_CASES if case.case_id == "L1-001")
    segment = (
        "workflow_router.plan completed\n"
        "selected_workflow: code_investigation.plan\n"
        "run_id: workflow-router-test\n"
        "Answer:\n"
        "Beginning point: core/stealth_order_manager.py:42\n"
        "Related tests: tests/unit/test_order_id_and_followup_rules.py\n"
        "Recommended commands: python -m pytest tests/unit/test_order_id_and_followup_rules.py\n"
    )

    status = semantic_status_for_segment(segment, l1_001)

    assert status["semantic_status"] == "passed"
    assert status["missing_required_markers"] == []
    assert status["rejected_markers_present"] == []


def test_ui_prompt_cases_include_tracking_tags() -> None:
    tag = "phase107-ui-e2e-test"
    prompts = [case.prompt("/mnt/c/example", tag) for case in UI_PROMPT_CASES]

    assert prompt_for_target("/mnt/c/example", tag) == prompts[0]
    assert len(prompts) >= 2
    assert all(tag in prompt for prompt in prompts)


def test_phase126_ui_prompt_catalog_passes_contract() -> None:
    catalog = load_catalog()
    errors = validate_ui_prompt_catalog(catalog, config_root=REPO_ROOT)

    assert errors == []
    cases = load_ui_prompt_cases(REPO_ROOT)
    stable_cases = [case for case in cases if case.source_baseline_entry_id]
    phase167_cases = [case for case in cases if case.case_id.startswith("UI167-")]
    assert len(stable_cases) == 8
    assert {case.target_root_mode for case in phase167_cases} == {UiPromptTargetRootMode.NO_TARGET}
    assert {case.expected_route_status for case in phase167_cases} == {
        "general_chat_no_target",
        "general_help_no_target",
        "missing_target_root_for_coding_request",
    }
    assert all("Artifacts:" not in case.transport_markers for case in phase167_cases)
    assert all(case.ordered_markers[:2] == ("Answer:", "I completed workflow_router.plan.") for case in phase167_cases)
    assert {
        (case.source_baseline_entry_id, case.target_roots[0])
        for case in stable_cases
    } >= {
        ("phase116_code_quality", "/mnt/c/coinbase_testing_repo_frozen_tmp"),
        ("phase116_code_quality", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
        ("phase117_defect_diagnosis", "/mnt/c/coinbase_testing_repo_frozen_tmp"),
        ("phase117_defect_diagnosis", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
        ("phase118_engineering_judgment", "/mnt/c/coinbase_testing_repo_frozen_tmp"),
        ("phase118_engineering_judgment", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
        ("phase119_delivery_mentorship", "/mnt/c/coinbase_testing_repo_frozen_tmp"),
        ("phase119_delivery_mentorship", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
    }


def test_phase126_ui_prompt_catalog_rejects_missing_family() -> None:
    catalog = load_catalog()
    catalog["cases"] = [
        case
        for case in catalog["cases"]  # type: ignore[index]
        if case.get("source_baseline_entry_id") != "phase119_delivery_mentorship"
    ]

    errors = validate_ui_prompt_catalog(catalog, config_root=REPO_ROOT)

    assert any("missing stable UI family coverage" in error for error in errors)


def test_phase126_ui_prompt_catalog_rejects_missing_frozen_root_coverage() -> None:
    catalog = load_catalog()
    for case in catalog["cases"]:  # type: ignore[index]
        if case.get("source_baseline_entry_id") == "phase116_code_quality" and case.get("target_roots") == [
            "/mnt/c/coinbase_testing_repo_frozen_tmp"
        ]:
            case["target_roots"] = ["/mnt/c/coinbase_testing_repo_frozen_tmp.github"]

    errors = validate_ui_prompt_catalog(catalog, config_root=REPO_ROOT)

    assert any("phase116_code_quality missing frozen root coverage" in error for error in errors)


def test_phase126_ui_prompt_catalog_rejects_unknown_source_prompt() -> None:
    catalog = load_catalog()
    first_stable = next(case for case in catalog["cases"] if case.get("source_baseline_entry_id"))  # type: ignore[index]
    first_stable["source_prompt_case_id"] = "missing"

    errors = validate_ui_prompt_catalog(catalog, config_root=REPO_ROOT)

    assert any("source_prompt_case_id is not present" in error for error in errors)


def test_phase126_ui_prompt_catalog_rejects_prompt_drift_without_approval() -> None:
    catalog = load_catalog()
    first_stable = next(case for case in catalog["cases"] if case.get("source_baseline_entry_id"))  # type: ignore[index]
    first_stable["prompt_template"] = str(first_stable["prompt_template"]).replace("Read only.", "Read only. Extra.")

    errors = validate_ui_prompt_catalog(catalog, config_root=REPO_ROOT)

    assert any("prompt_template drift requires ui_prompt_variant_approved=true" in error for error in errors)


def test_phase167_ui_prompt_catalog_rejects_no_target_case_with_target_root() -> None:
    catalog = load_catalog()
    first_phase167 = next(case for case in catalog["cases"] if case.get("case_id") == "UI167-GENCHAT-001")  # type: ignore[index]
    first_phase167["target_roots"] = ["/mnt/c/coinbase_testing_repo_frozen_tmp"]

    errors = validate_ui_prompt_catalog(catalog, config_root=REPO_ROOT)

    assert any("target_roots must be empty in no_target mode" in error for error in errors)


def test_phase167_ui_prompt_catalog_rejects_no_target_artifact_transport_marker() -> None:
    catalog = load_catalog()
    first_phase167 = next(case for case in catalog["cases"] if case.get("case_id") == "UI167-GENCHAT-001")  # type: ignore[index]
    first_phase167["transport_markers"] = [*first_phase167["transport_markers"], "Artifacts:"]

    errors = validate_ui_prompt_catalog(catalog, config_root=REPO_ROOT)

    assert any("transport_markers must not require Artifacts:" in error for error in errors)


def test_phase167_no_target_semantic_contract_rejects_boilerplate_before_answer() -> None:
    case = load_ui_prompt_cases(REPO_ROOT, case_ids=("UI167-GENCHAT-001",))[0]
    segment = (
        "I completed workflow_router.plan.\n"
        "workflow_router.plan completed\n"
        "run_id: workflow-router-general-test\n"
        "Result:\n"
        "- Selected workflow: none\n"
        "Summary:\n"
        "- route_status: general_chat_no_target\n"
        "- selected_workflow: none\n"
        "- answer: Hi. For coding workflow help, include an allowed target_root path and the task you want planned or investigated.\n"
        "Answer:\n"
        "Hi. For coding workflow help, include an allowed target_root path and the task you want planned or investigated.\n"
        "Run record: /v1/controller/runs/workflow-router-general-test\n"
    )

    status = semantic_status_for_segment(segment, case)

    assert status["semantic_status"] == "failed"
    assert status["ordered_marker_errors"]


def test_phase167_no_target_semantic_contract_accepts_answer_first() -> None:
    case = load_ui_prompt_cases(REPO_ROOT, case_ids=("UI167-GENCHAT-001",))[0]
    segment = (
        "Answer:\n"
        "Hi. For coding workflow help, include an allowed target_root path and the task you want planned or investigated.\n"
        "\n"
        "I completed workflow_router.plan.\n"
        "workflow_router.plan completed\n"
        "run_id: workflow-router-general-test\n"
        "Result:\n"
        "- Selected workflow: none\n"
        "Summary:\n"
        "- route_status: general_chat_no_target\n"
        "- selected_workflow: none\n"
        "- answer: Hi. For coding workflow help, include an allowed target_root path and the task you want planned or investigated.\n"
        "Run record: /v1/controller/runs/workflow-router-general-test\n"
    )

    status = semantic_status_for_segment(segment, case)

    assert status["semantic_status"] == "passed"
    assert status["ordered_marker_errors"] == []


def test_load_ui_prompt_cases_filters_case_ids() -> None:
    cases = load_ui_prompt_cases(REPO_ROOT, case_ids=("UI126-CQ116-001", "UI126-DM119-002"))

    assert [case.case_id for case in cases] == ["UI126-CQ116-001", "UI126-DM119-002"]
    assert [case.target_roots for case in cases] == [
        ("/mnt/c/coinbase_testing_repo_frozen_tmp.github",),
        ("/mnt/c/coinbase_testing_repo_frozen_tmp",),
    ]


def test_execution_target_roots_for_no_target_case_runs_once_but_hashes_fallback_roots() -> None:
    case = load_ui_prompt_cases(REPO_ROOT, case_ids=("UI167-GENCHAT-001",))[0]

    assert execution_target_roots_for_prompt_case(case, ("/mnt/c/a", "/mnt/c/b")) == ("",)


def test_usefulness_status_rejects_marker_only_stable_ui_segment() -> None:
    case = next(case for case in UI_PROMPT_CASES if case.case_id == "UI126-CQ116-001")
    marker_only = (
        "I completed workflow_router.plan.\n"
        "workflow_router.plan completed\n"
        "run_id: workflow-router-test\n"
        "Result:\n"
        "Skill Selection:\n"
        "Summary:\n"
        "Answer:\n"
        "Code Quality Review:\n"
        "Source mutation: false\n"
        "Artifacts:\n"
        "Run record: /v1/controller/runs/workflow-router-test\n"
    )

    status = usefulness_status_for_segment(marker_only, case, load_answer_usefulness_contract())

    assert status["usefulness_status"] == "failed"
    assert status["errors"]


def test_screenshot_status_requires_existing_non_empty_files(tmp_path: Path) -> None:
    good = tmp_path / "good.png"
    empty = tmp_path / "empty.png"
    good.write_bytes(b"png")
    empty.write_bytes(b"")

    assert screenshot_status(good)["status"] == "passed"
    assert screenshot_status(good, empty)["status"] == "failed"


def test_electron_require_shim_sets_backend_event_and_api_base() -> None:
    shim = build_electron_require_shim("http://127.0.0.1:3001")

    assert "window.require" in shim
    assert "backend-server-online" in shim
    assert '"http://127.0.0.1:3001/api"' in shim
    assert "ipcRenderer" in shim


def test_api_base_for_ui_normalizes_without_double_slash() -> None:
    assert api_base_for_ui("http://127.0.0.1:3001/") == "http://127.0.0.1:3001/api"


def test_request_failure_split_ignores_logo_abort_only() -> None:
    failures = [
        {"url": "http://localhost:3001/api/system/logo?theme=system", "failure": "net::ERR_ABORTED"},
        {"url": "http://localhost:3001/api/workspace/my-workspace/stream-chat", "failure": "net::ERR_FAILED"},
    ]

    assert ignored_request_failures(failures) == [failures[0]]
    assert non_ignored_request_failures(failures) == [failures[1]]


def test_host_path_converts_wsl_mount_path_on_windows() -> None:
    assert str(host_path("/mnt/c/example/repo")).startswith("C:")


def test_host_path_prefers_existing_direct_path(tmp_path) -> None:
    assert host_path(str(tmp_path)) == tmp_path


def test_start_static_server_serves_dist_without_npx(tmp_path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    port = free_port()
    server = start_static_server(tmp_path, port=port)
    try:
        wait_for_http(f"http://127.0.0.1:{port}/", timeout_seconds=10)
        status, body = json_request(f"http://127.0.0.1:{port}/", timeout_seconds=10)
        assert status == 200
        assert body["text"] == "ok"
    finally:
        server.terminate()
        server.wait(timeout=10)
