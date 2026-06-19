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
POST /v1/controller/workflow-router/plans
POST /v1/controller/workflow-router/chat/completions
POST /v1/controller/execution-planning/plans
POST /v1/controller/code-context/lookups
POST /v1/controller/code-investigation/plans
POST /v1/controller/refactor/single-path
POST /v1/controller/workflow-feedback/records
POST /v1/controller/connector-catalog/validations
POST /v1/controller/connector-catalog/registrations
POST /v1/controller/connectors/invocations
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

`CONTROLLER_ALLOWED_TARGET_ROOTS` is a colon-separated list. Controller workflow requests are rejected before workflow execution if `target_root` is outside that allowlist.

Artifacts created by the service are written under `CONTROLLER_OUTPUT_ROOT`, not directly into the target repository.

## Controller Tool Policy

The controller resolves tool policy before workflow execution:

- `runtime/workflows.json` defines which tools a workflow may use.
- `runtime/roles.json` defines which tools a role may use.
- `runtime/tools.json` defines executable local capabilities.

For `workflow_router.plan`, the default `dispatcher/default` role has no controller tools or model-visible tools; Phase 1 reads registry metadata only. For `documenter.review`, the default `documenter/default` role can use `git_ls_files` and `read_file`; `document_scope: "all"` also enables `scan_files`. For `execution_planning.plan`, `code_investigation.plan`, and `refactor.single_path`, the default `architect/default` role can use controller-owned `structure_index`, `git_grep`, and `read_file` context gathering. `code_context.lookup` can also use the curated read-only `codegraph_context` relationship adapter for callers, callees, and imports when the request includes `relationship_queries`. `workflow_feedback.record` uses the same `architect/default` role policy but has no controller tool or model-visible tool dependencies. Model-visible tools are disabled for these workflows until a later phase wires a bounded model tool loop into the service.

If a request selects a role that is not allowed for the workflow, or asks for model-visible tools that the workflow does not allow, the service rejects the request with `tool_policy_denied` before creating workflow artifacts.

`connector_catalog.validate` is a read-only validation workflow for future external integration contracts. It validates typed connector manifests and writes artifacts, but it does not register connectors, execute connectors, call external APIs, expose raw MCP, or modify runtime registries.

`connector_catalog.register` is the approval-gated registration workflow for validated connector metadata. It appends only to `runtime/connectors.json`; draft registration installs `enabled=false`, and enabled registration requires a passed connector eval release-gate report. It does not modify tools, workflows, roles, target repositories, or external services.

`connector.invoke` is the controller-owned mediation workflow for enabled local stub connectors. It requires actor/session/request context, enforces declared user scopes for `oauth_user_scope` connectors, writes replay-safe audit artifacts, and proves operation allowlists, approval checks, and bypass rejection. It does not call external APIs, exchange real OAuth tokens, or expose connector operations as model-visible tools.

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

Use the workflow router endpoint when natural-language request text should be classified before repository work begins:

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-router/plans \
  -H 'Content-Type: application/json' \
  -d '<workflow_router.plan JSON with user_request>'
```

Concrete payloads are in [docs/examples/workflow-router.md](docs/examples/workflow-router.md).

Use the workflow-router chat endpoint only for OpenAI-compatible clients on the dedicated workflow-router gateway. It accepts normal chat messages, extracts the latest user message, requires an allowed target path in that message, and delegates to `workflow_router.plan`:

```text
POST /v1/controller/workflow-router/chat/completions
```

AnythingLLM should reach this through `http://127.0.0.1:8500/v1`, not by calling the controller port directly.

Use the execution planning endpoint when the request should produce planning artifacts or draft implementation packet candidates:

```bash
curl -s http://127.0.0.1:8400/v1/controller/execution-planning/plans \
  -H 'Content-Type: application/json' \
  -d '<explicit execution_planning.plan JSON>'
```

Concrete payloads are in [docs/examples/execution-planning-harness.md](docs/examples/execution-planning-harness.md).

Use the code context lookup endpoint when a request needs deterministic read-only source lookup before planning:

```bash
curl -s http://127.0.0.1:8400/v1/controller/code-context/lookups \
  -H 'Content-Type: application/json' \
  -d '<explicit code_context.lookup JSON>'
```

Concrete payloads are in [docs/examples/code-context.md](docs/examples/code-context.md).

Use the code investigation endpoint when a request needs a read-only beginning-point and path-risk artifact before packet design:

```bash
curl -s http://127.0.0.1:8400/v1/controller/code-investigation/plans \
  -H 'Content-Type: application/json' \
  -d '<explicit code_investigation.plan JSON>'
```

Concrete payloads are in [docs/examples/code-investigation.md](docs/examples/code-investigation.md).

Use the refactor single-path endpoint when a request should start with investigation and require approval before draft packet planning:

```bash
curl -s http://127.0.0.1:8400/v1/controller/refactor/single-path \
  -H 'Content-Type: application/json' \
  -d '<explicit refactor.single_path JSON>'
```

Concrete payloads are in [docs/examples/refactor-single-path.md](docs/examples/refactor-single-path.md).

Use the workflow feedback endpoint when founder/tester notes should be attached to a previous controller run:

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-feedback/records \
  -H 'Content-Type: application/json' \
  -d '<explicit workflow_feedback.record JSON>'
```

Concrete payloads are in [docs/examples/workflow-feedback.md](docs/examples/workflow-feedback.md).

Use the connector catalog validation endpoint when a future external integration needs a governed manifest check before registration or execution work exists:

```bash
curl -s http://127.0.0.1:8400/v1/controller/connector-catalog/validations \
  -H 'Content-Type: application/json' \
  -d '<connector_catalog.validate JSON>'
```

Concrete payloads are in [docs/examples/connector-catalog.md](docs/examples/connector-catalog.md).

Use the connector catalog registration endpoint when a validated connector should be appended to the runtime connector registry:

```bash
curl -s http://127.0.0.1:8400/v1/controller/connector-catalog/registrations \
  -H 'Content-Type: application/json' \
  -d '<connector_catalog.register JSON>'
```

Concrete payloads are in [docs/examples/connector-catalog.md](docs/examples/connector-catalog.md).

Use the connector invocation endpoint only for enabled local stub connectors:

```bash
curl -s http://127.0.0.1:8400/v1/controller/connectors/invocations \
  -H 'Content-Type: application/json' \
  -d '<connector.invoke JSON>'
```

Concrete payloads are in [docs/examples/connector-catalog.md](docs/examples/connector-catalog.md).

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

## Execution Planning Request

`execution_planning.plan` accepts explicit planning envelopes and writes artifacts under `CONTROLLER_OUTPUT_ROOT/execution-planning/<run-id>/`.

Minimal `dry_run` shape:

```json
{
  "workflow": "execution_planning.plan",
  "schema_version": 1,
  "target_root": "/path/to/repo",
  "user_request": "Prepare implementation packet candidates for an approved documentation clarification. Use draft mode only and do not mutate the repository.",
  "mode": "dry_run",
  "approval": {
    "status": "approved_for_packet_design",
    "scope": "packet_design_only",
    "apply_allowed": false,
    "approval_refs": ["user:approved packet design only"]
  },
  "packet_operations": [
    {
      "kind": "replace_text",
      "path": "docs/agents/INVARIANTS.md",
      "old": "exact existing text",
      "new": "exact proposed text"
    }
  ],
  "budgets": {
    "max_context_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "max_model_calls": 12,
    "max_output_tokens": 4600
  }
}
```

The current implementation requires `packet_operations` for `implementation_prep` and `dry_run`. It rejects apply mode, raw CodeGraphContext/Cypher requests, unsupported context tools, unsupported skills, and unsupported budget fields before model-visible work. The curated `codegraph_context` adapter is currently available through `code_context.lookup`, not directly through `execution_planning.plan`.

## Workflow Feedback Request

`workflow_feedback.record` records bounded feedback under `CONTROLLER_OUTPUT_ROOT/workflow-feedback/<run-id>/`.

Minimal shape:

```json
{
  "workflow": "workflow_feedback.record",
  "schema_version": 1,
  "target_workflow": "refactor.single_path",
  "target_run_id": "refactor-single-path-20260604T031238337959Z",
  "target_root": "/path/to/repo",
  "feedback": {
    "useful": ["Beginning point was correct."],
    "wrong": [],
    "missing": ["Need clearer verification command source."],
    "too_slow": [],
    "too_noisy": [],
    "notes": "Founder/tester feedback."
  },
  "tester": {
    "id": "founder",
    "surface": "AnythingLLM"
  }
}
```

The workflow links to a persisted controller run record when available. If the target run record has already been cleaned up, the feedback record is still written with a warning. Empty feedback and unsupported feedback fields are rejected.

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
