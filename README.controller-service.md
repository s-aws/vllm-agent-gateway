# Controller Service

The controller service exposes explicit HTTP endpoints for stateful workflows.
It is separate from the role prompt proxy and token-budget gateway.

```text
client -> controller service -> workflow controller -> bounded role/model calls -> artifacts
```

Normal chat requests to role ports do not trigger controller workflows. A caller must use a controller endpoint and send a structured workflow request.

## Endpoints

```text
GET  /health
POST /v1/controller/documenter/reviews
POST /v1/controller/harness/chat/completions
GET  /v1/controller/runs/{run_id}
POST /v1/controller/runs/{run_id}/cancel
POST /v1/controller/runs/cleanup
```

Default controller URL:

```text
http://127.0.0.1:8400
```

## Configuration

The startup script starts the controller service by default.

Environment variables:

```text
CONTROLLER_BIND_HOST=127.0.0.1
CONTROLLER_PORT=8400
CONTROLLER_OUTPUT_ROOT=<private runtime state>/controller-artifacts
CONTROLLER_ALLOWED_TARGET_ROOTS=<repo root>
```

`CONTROLLER_ALLOWED_TARGET_ROOTS` is a colon-separated list. A documenter request is rejected before workflow execution if `target_root` is outside that allowlist.

Artifacts created by the service are written under `CONTROLLER_OUTPUT_ROOT`, not directly into the target repository.

## Controller Tool Policy

The controller resolves tool policy before workflow execution:

- `runtime/workflows.json` defines which tools a workflow may use.
- `runtime/roles.json` defines which tools a role may use.
- `runtime/tools.json` defines executable local capabilities.

For `documenter.review`, the default `documenter/default` role can use `git_ls_files` and `read_file`; `document_scope: "all"` also enables `scan_files`. Model-visible tools are disabled for this workflow until a later phase wires a bounded model tool loop into the service.

If a request selects a role that is not allowed for the workflow, or asks for model-visible tools that the workflow does not allow, the service rejects the request with `tool_policy_denied` before creating workflow artifacts.

## Which Interface To Use

Use the CLI when developing or debugging a workflow locally:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md --dry-run --max-chunks 1
```

Use the direct role prompt port for ordinary bounded chat with a role. It does not traverse the repo, build manifests, or manage state.

Use the controller HTTP endpoint for explicit workflow execution:

```bash
python scripts/run_documenter_service_example.py --target-root . --case seed --max-chunks 1
```

Use the harness adapter only when a client expects an OpenAI-style chat completion response but can send an explicit `agentic_controller_request` envelope:

```bash
python scripts/run_documenter_service_example.py --target-root . --case harness --max-chunks 1
```

## Documenter Review Request

Minimal dry-run request:

```json
{
  "workflow": "documenter.review",
  "target_root": "/path/to/repo",
  "seed_doc": "README.md",
  "mode": "full",
  "dry_run": true,
  "budgets": {
    "max_chunks": 1
  }
}
```

Bootstrap all-docs request:

```json
{
  "workflow": "documenter.review",
  "target_root": "/path/to/repo",
  "mode": "full",
  "document_scope": "all",
  "review_scope": "manifest",
  "budgets": {
    "max_chunks": 1
  }
}
```

The `budgets` object supports `max_chunks`, `parallelism`, and `stop_after_chunks`. Use `parallelism` for bounded concurrent chunk review, `stop_after_chunks` for deterministic pause/resume testing, and `"async": true` for long runs that should survive client disconnects.

Async request:

```json
{
  "workflow": "documenter.review",
  "target_root": "/path/to/repo",
  "seed_doc": "README.md",
  "mode": "full",
  "async": true,
  "budgets": {
    "max_chunks": 10
  }
}
```

Async requests return `202 Accepted` with a controller `run_id`. Poll it with:

```text
GET /v1/controller/runs/{run_id}
```

Statuses are distinct:

- `running`: accepted and executing.
- `paused`: workflow wrote resumable state, usually through `stop_after_chunks`.
- `cancel_requested`: cooperative stop signal has been written.
- `canceled`: workflow stopped after the current packet.
- `completed`: workflow finished.
- `failed`: workflow failed before completion.

Cancel an async run after the current packet:

```text
POST /v1/controller/runs/{run_id}/cancel
```

The cancel endpoint writes a stop signal under the controller output root. The workflow checks that signal between packets, so cancellation is cooperative rather than immediate process termination.

Resume a paused run by sending another documenter review request with the `resume` path from the prior response artifact:

```json
{
  "workflow": "documenter.review",
  "target_root": "/path/to/repo",
  "seed_doc": "README.md",
  "mode": "full",
  "resume": ".../run-state-target-README.md-<run-id>.json"
}
```

Resume uses the same compatibility checks as the CLI run state. Argument changes are rejected unless `resume_allow_arg_changes` is set.

Clean up old terminal run records:

```text
POST /v1/controller/runs/cleanup
```

Cleanup removes bounded controller run records and cooperative stop signal files. It does not delete workflow artifacts such as reports, manifests, summaries, change plans, drafts, or run-state artifacts.

## Response Shape

Responses are bounded and do not embed full reports:

```json
{
  "run_id": "20260526T204620829488Z",
  "workflow": "documenter.review",
  "status": "completed",
  "artifacts": {
    "json_report": ".../documenter-target-README.md-<run-id>.json",
    "run_state": ".../run-state-target-README.md-<run-id>.json"
  },
  "summary": null,
  "warnings": [],
  "failures": [],
  "resume_key": {},
  "review_summary": {
    "seed_doc_id": "README.md",
    "document_scope": "tracked",
    "review_scope": "seed",
    "reviewed_file_count": 1,
    "reviewed_files": ["README.md"],
    "chunks_processed": 1,
    "chunks_total": 1,
    "skipped_followup_count": 0
  },
  "tool_policy": {
    "workflow": "documenter.review",
    "role_id": "documenter/default",
    "controller_tool_ids": ["git_ls_files", "read_file"],
    "model_visible_tool_ids": [],
    "denied_tool_ids": [],
    "controller_actions": []
  }
}
```

Use `GET /v1/controller/runs/{run_id}` to retrieve the persisted bounded run record.
Poll responses remain bounded and do not include full report bodies.

## Harness Adapter

The harness adapter uses an OpenAI-style chat completion response, but it is not a normal chat endpoint. It lives under the controller namespace:

```text
POST /v1/controller/harness/chat/completions
```

The request must contain exactly one explicit envelope:

```json
{
  "model": "agentic-controller",
  "messages": [
    {
      "role": "user",
      "content": "{\"agentic_controller_request\":{\"workflow\":\"documenter.review\",\"target_root\":\"/path/to/repo\",\"seed_doc\":\"README.md\",\"mode\":\"full\",\"dry_run\":true,\"budgets\":{\"max_chunks\":1}}}"
    }
  ]
}
```

Top-level envelopes are also accepted for harnesses that support extra JSON fields:

```json
{
  "model": "agentic-controller",
  "agentic_controller_request": {
    "workflow": "documenter.review",
    "target_root": "/path/to/repo",
    "seed_doc": "README.md",
    "mode": "full",
    "dry_run": true,
    "budgets": {
      "max_chunks": 1
    }
  }
}
```

Ordinary natural-language text is rejected with `missing_controller_envelope`. Streaming responses are not supported in this phase.

The adapter returns a compact assistant message plus a bounded structured `agentic_controller_response`. Full details stay in artifact files and the persisted run record.

## Safety Model

- No implicit natural-language workflow triggering.
- Harness adapter requests require an explicit `agentic_controller_request` envelope.
- No direct role-port repo traversal.
- `target_root` must be inside the configured allowlist.
- Request bodies are capped at 1 MiB.
- Unsupported request fields are rejected.
- Unsupported budget fields are rejected.
- Target repo files remain read-only by default.

## References

- Roadmap: [docs/CONTROLLER_SERVICE_ROADMAP.md](docs/CONTROLLER_SERVICE_ROADMAP.md)
- Examples: [docs/examples/controller-service.md](docs/examples/controller-service.md)
