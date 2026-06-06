# Workflow Feedback Examples

These examples record feedback against a previous controller run. They do not call the model and do not mutate the target repository.

## Direct Controller Request

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-feedback/records \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "workflow_feedback.record",
    "schema_version": 1,
    "target_workflow": "refactor.single_path",
    "target_run_id": "refactor-single-path-20260604T031238337959Z",
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "feedback": {
      "useful": ["The likely beginning point matched the code owner."],
      "wrong": [],
      "missing": ["The next command should be more explicit."],
      "too_slow": [],
      "too_noisy": [],
      "notes": "Manual feedback captured after founder review."
    },
    "tester": {
      "id": "founder",
      "surface": "curl"
    },
    "request_payload": {
      "source": "manual-controller-test"
    },
    "artifact_refs": {}
  }'
```

## Gateway Or AnythingLLM Envelope

Paste this JSON as the AnythingLLM message, or send it to the gateway chat completions endpoint. AnythingLLM should be configured to use `http://127.0.0.1:8300/v1`.

```json
{
  "agentic_controller_request": {
    "workflow": "workflow_feedback.record",
    "schema_version": 1,
    "target_workflow": "refactor.single_path",
    "target_run_id": "refactor-single-path-20260604T031238337959Z",
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "feedback": {
      "useful": ["The workflow produced bounded artifact links."],
      "wrong": [],
      "missing": ["Need clearer pass/fail proof in the assistant text."],
      "too_slow": [],
      "too_noisy": [],
      "notes": "AnythingLLM feedback capture probe."
    },
    "tester": {
      "id": "founder",
      "surface": "AnythingLLM"
    },
    "request_payload": {
      "source": "manual-anythingllm-test"
    },
    "artifact_refs": {}
  }
}
```

Gateway curl form:

```bash
curl -s http://127.0.0.1:8300/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-controller",
    "messages": [
      {
        "role": "user",
        "content": "{\"agentic_controller_request\":{\"workflow\":\"workflow_feedback.record\",\"schema_version\":1,\"target_workflow\":\"refactor.single_path\",\"target_run_id\":\"refactor-single-path-20260604T031238337959Z\",\"target_root\":\"/mnt/c/coinbase_testing_repo_frozen_tmp\",\"feedback\":{\"useful\":[\"Gateway returned controller artifacts.\"],\"wrong\":[],\"missing\":[],\"too_slow\":[],\"too_noisy\":[],\"notes\":\"Gateway feedback probe.\"},\"tester\":{\"id\":\"founder\",\"surface\":\"gateway\"},\"request_payload\":{\"source\":\"manual-gateway-test\"},\"artifact_refs\":{}}}"
      }
    ]
  }'
```

## Expected Response Markers

The assistant text should contain:

```text
workflow_feedback.record completed
run_id: workflow-feedback-...
Artifacts:
- feedback_record: ...
- request: ...
- run_state: ...
```

The structured response includes:

```json
{
  "workflow": "workflow_feedback.record",
  "status": "completed",
  "summary": {
    "target_workflow": "refactor.single_path",
    "target_run_id": "refactor-single-path-20260604T031238337959Z",
    "feedback_counts": {
      "useful": 1,
      "wrong": 0,
      "missing": 1,
      "too_slow": 0,
      "too_noisy": 0
    },
    "has_notes": true,
    "linked_run_found": true
  }
}
```

If the target run record has already been cleaned up, `linked_run_found` is false and a warning is recorded. The feedback artifact is still useful because it preserves the target run ID, workflow ID, target root, tester surface, and notes.
