# Workflow Feedback Capture

`workflow_feedback.record` records founder/tester feedback against a prior controller workflow run.

It is a controller-owned artifact workflow, not a model skill. It does not call the model, does not edit the target repository, and does not imply approval to implement follow-up changes.

## When To Use It

Use this after running `execution_planning.plan`, `code_context.lookup`, `code_investigation.plan`, or `refactor.single_path` when the tester needs to record what was useful, wrong, missing, too slow, or too noisy.

The workflow is useful when feedback should survive outside the conversation history and be linked to run IDs and artifacts.

## Endpoint

```text
POST /v1/controller/workflow-feedback/records
```

Default controller URL:

```text
http://127.0.0.1:8400
```

AnythingLLM should send the same explicit `agentic_controller_request` envelope through the gateway base URL:

```text
http://127.0.0.1:8300/v1
```

## Request Shape

```json
{
  "workflow": "workflow_feedback.record",
  "schema_version": 1,
  "target_workflow": "refactor.single_path",
  "target_run_id": "refactor-single-path-20260604T031238337959Z",
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
  "feedback": {
    "useful": ["Beginning point was correct."],
    "wrong": [],
    "missing": ["Need clearer verification command source."],
    "too_slow": [],
    "too_noisy": [],
    "notes": "Founder/tester feedback from AnythingLLM."
  },
  "tester": {
    "id": "founder",
    "surface": "AnythingLLM"
  },
  "request_payload": {
    "source": "manual-test"
  },
  "artifact_refs": {}
}
```

`target_run_id` must be present. If the controller run record still exists, the feedback artifact links to it. If the record is not found, the workflow still records feedback and emits a warning.

## Artifacts

Artifacts are written under `CONTROLLER_OUTPUT_ROOT/workflow-feedback/<run-id>/`:

- `request.json`: bounded request echo
- `feedback-record.json`: normalized feedback and linked run summary
- `run-state.json`: compact completed state

The compact response includes feedback counts, whether notes were present, and whether the target run record was linked.

## Safety

- Requires an explicit `workflow_feedback.record` request.
- Rejects ordinary chat without an `agentic_controller_request` envelope.
- Validates `target_root` against the controller allowlist when provided.
- Rejects unsupported feedback fields and empty feedback.
- Uses no model-visible tools and no repository write path.

Examples are in [docs/examples/workflow-feedback.md](docs/examples/workflow-feedback.md).
