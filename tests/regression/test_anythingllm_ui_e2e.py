from __future__ import annotations

from vllm_agent_gateway.anythingllm_ui_e2e import (
    DEFAULT_MARKERS,
    api_base_for_ui,
    build_electron_require_shim,
    host_path,
    ignored_request_failures,
    marker_hits,
    non_ignored_request_failures,
    segment_after_new_tag,
    ui_case_passed,
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
