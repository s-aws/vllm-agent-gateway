from __future__ import annotations

from vllm_agent_gateway.anythingllm_ui_e2e import (
    DEFAULT_MARKERS,
    UI_PROMPT_CASES,
    api_base_for_ui,
    build_electron_require_shim,
    free_port,
    host_path,
    ignored_request_failures,
    json_request,
    marker_hits,
    non_ignored_request_failures,
    prompt_for_target,
    segment_after_new_tag,
    semantic_status_for_segment,
    start_static_server,
    ui_case_passed,
    wait_for_http,
)


def test_segment_after_new_tag_ignores_old_chat_history_markers() -> None:
    old_history = "workflow_router.plan completed\nselected_workflow: code_investigation.plan\nrun_id:\nAnswer:"
    tag = "phase71-ui-e2e-test"
    new_response = "user prompt " + tag + "\n\nassistant response\nworkflow_router.plan completed\nAnswer:"
    segment = segment_after_new_tag(old_history + "\n" + new_response, tag, len(old_history))

    hits = marker_hits(segment)

    assert hits["workflow_router.plan completed"] is True
    assert hits["Answer:"] is True
    assert hits["selected_workflow: code_investigation.plan"] is False
    assert "phase71-ui-e2e-test" not in segment


def test_ui_case_passed_requires_markers_and_stream_chat() -> None:
    assert ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "stream_chat_seen": True,
        }
    )
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "stream_chat_seen": False,
        }
    )
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {"workflow_router.plan completed": True},
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
        }
    )
    assert not ui_case_passed(
        {
            "marker_hits_after_tag": {marker: True for marker in DEFAULT_MARKERS},
            "semantic_marker_hits_after_tag": {"Beginning point:": True},
            "rejected_marker_hits_after_tag": {"Entrypoints:": True},
            "stream_chat_seen": True,
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
