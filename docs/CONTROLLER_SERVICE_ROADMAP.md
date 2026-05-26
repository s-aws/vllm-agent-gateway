# Controller Service Roadmap

This roadmap defines the path from local CLI workflows to an explicit harness-facing controller service.

The end result is:

```text
LLM harness
  -> explicit controller request adapter
  -> controller service
  -> workflow controller
  -> mediated tools and bounded role/model calls
  -> persisted artifacts and final result
  -> LLM harness
```

The key point is explicit control. A normal chat request to a documenter, architect, tester, or implementer port remains a role-prompted model request. It must not silently become a repo-wide workflow. Stateful orchestration belongs to the controller service, not to role prompts and not to the transport gateway.

## Current Decision

Do not add community agent-framework dependencies yet.

The current path is to keep using the existing controller code and add the smallest service layer needed to expose it cleanly. Frameworks such as graph/workflow engines can be reconsidered only after the local controller hits concrete limits around durability, scheduling, or workflow complexity.

## Target Behavior

A caller should be able to make an explicit request such as:

```json
{
  "workflow": "documenter.review",
  "target_root": "/path/to/repo",
  "mode": "full",
  "document_scope": "all",
  "review_scope": "manifest",
  "budgets": {
    "max_chunks": 200,
    "max_elapsed_seconds": 1800
  }
}
```

The controller service should:

- validate that the request is an allowed workflow request
- validate path scope before reading target files
- create or resume controller state
- build manifests, indexes, review plans, packets, and tool records as needed
- call role/model endpoints only with bounded packets
- validate model output before accepting it
- persist artifacts under a configured output directory
- return a compact final response with status, summary, artifact paths, and next actions

## Non-Goals

- No implicit natural-language workflow triggering.
- No repo-wide traversal from direct role ports.
- No model-owned manifest creation, chunk selection, retry policy, or write policy.
- No hidden summarization or automatic lossy compression.
- No default target repo mutation.
- No broad dependency stack until there is a specific failure mode the local controller cannot handle well.

## Architecture Boundaries

| Layer | Owns | Does Not Own |
| --- | --- | --- |
| Role prompt proxy | Prompt injection, client compatibility, role routing | Workflow sequencing, repo traversal, state |
| Gateway server | Token budget enforcement, request forwarding | Task orchestration, tool execution |
| Controller service | Workflow request validation, state, sequencing, artifacts | Low-level model inference |
| Workflow controller | Manifest/index/review/implementation logic | Harness protocol compatibility |
| Tool mediator | Allowed local tool execution and result shaping | Deciding workflow goals |
| Role endpoint | Bounded packet reasoning | Choosing next files or chunks |

## Phase 1: Controller Invocation Contract

Status: Done

Refactor the existing CLI-first workflows behind typed request/result boundaries.

Deliverables:

- Shared request objects for documenter, streaming, structure index, and implementation workflows. Done.
- Shared result object that exposes status, artifact paths, summary text, failures, resume keys, reports, and run IDs. Done.
- CLI wrappers call the same invocation API instead of owning workflow setup directly. Done.
- Request validation still lives in the existing workflow controllers and rejects ambiguous or unsafe combinations before work starts. Done.

Acceptance criteria:

- The existing CLIs keep their behavior. Done.
- Tests can invoke workflows without shelling out. Done.
- A future HTTP service can call the same workflow entrypoints without reconstructing `argparse` internals. Done.
- Failures return structured results where possible, not only printed text. Done.

## Phase 2: Local Controller HTTP Service

Status: Done

Add a small local service that exposes explicit workflow endpoints. Prefer the Python standard library first unless a concrete feature requires a dependency.

Initial endpoints:

```text
GET  /health
POST /v1/controller/documenter/reviews
GET  /v1/controller/runs/{run_id}
```

Deliverables:

- Linux-first startup script support for the controller service. Done.
- Configurable bind host, port, output directory, and target-root allowlist. Done.
- Synchronous first implementation for short runs. Done.
- Structured JSON response with `run_id`, `status`, `artifacts`, `summary`, `warnings`, and `failures`. Done.
- Deterministic regression tests using temp repos and fake role endpoints. Done.

Acceptance criteria:

- The service cannot read outside allowed target roots. Done.
- Direct role ports still behave as direct role ports. Done.
- A documenter full-manifest run can be started through HTTP and produces the same core artifacts as the CLI. Done.
- Oversized or invalid requests fail before any model call. Done.

## Phase 3: Harness-Facing Adapter

Status: Done

Make the controller usable from clients that expect an LLM-compatible API, without making normal chat requests magical.

The adapter may speak an OpenAI-compatible or Anthropic-compatible request shape, but it must require an explicit controller envelope. If the request does not contain a valid envelope, it should reject with a clear message instead of guessing intent.

Example envelope:

```json
{
  "agentic_controller_request": {
    "workflow": "documenter.review",
    "target_root": "/path/to/repo",
    "mode": "full",
    "document_scope": "all"
  }
}
```

Deliverables:

- One harness-compatible adapter endpoint. Done.
- Strict envelope parser. Done.
- Clear rejection for ordinary chat text. Done.
- Final assistant-style response that summarizes status and artifact paths. Done.
- Tests proving the adapter does not trigger workflows from natural language alone. Done.

Acceptance criteria:

- A harness can send an explicit controller request and receive the workflow result. Done.
- The adapter cannot be confused with a normal documenter role port. Done.
- The result returned to the harness is compact enough for the model context window. Done.
- Full artifacts remain on disk; the harness response only includes bounded summaries and paths. Done.

## Phase 4: Run Lifecycle

Status: Done

Support long-running workflows without requiring the harness connection to stay open.

Deliverables:

- Async job creation option. Done.
- Pollable run status. Done.
- Resume support through the service. Done.
- Cancel or stop-after-current-packet support. Done.
- Run state cleanup policy. Done.

Acceptance criteria:

- Long runs can survive client disconnects. Done.
- Resume uses the same compatibility checks as CLI state. Done.
- The controller records incomplete, failed, canceled, and completed states distinctly. Done.
- Poll responses are bounded and do not include full artifacts by default. Done.

## Phase 5: Controller-Owned Tool Policy

Status: Done

Generate allowed tool surfaces from role/workflow policy without letting role prompts invent tool access.

Deliverables:

- Workflow-to-tool-policy mapping in runtime configuration. Done.
- Request-time tool policy resolution. Done.
- Tool mediator integration for controller actions and any future model-visible tool calls. Done.
- Audit records for which tool capabilities were enabled for a run. Done.

Acceptance criteria:

- Tools are selected by workflow and role policy, not by model claims. Done.
- A model-visible tool name always maps to an executable local capability or is rejected. Done.
- Tool results can be traced to controller actions. Done.
- Denied tools are reported clearly. Done.

## Phase 6: Documenter End-To-End Service Example

Status: Done

Ship the first complete service-backed workflow using the documenter.

Deliverables:

- Example request for all tracked documentation. Done.
- Example request for bootstrap all-file documentation review. Done.
- Example request for a single seed document. Done.
- Example response showing summary, warnings, artifact paths, and resume key. Done.
- Documentation that explains when to use CLI, direct role port, controller HTTP, and harness adapter. Done.

Acceptance criteria:

- A new user can start vLLM, start the gateway/controller stack, send one explicit documenter controller request, and inspect the generated report. Done.
- The model only receives bounded packets. Done.
- The final harness response explains what was reviewed, what was skipped, and where the full artifacts are. Done.

## Phase 7: Hardening And Deferred Framework Review

Status: Deferred

Only revisit external workflow/controller frameworks after the local path exposes a real need.

Triggers for reconsideration:

- Run lifecycle complexity becomes difficult to test locally.
- Durable checkpoints need richer semantics than current state files.
- Multiple workflows need shared scheduling, backpressure, or fan-out/fan-in primitives.
- Tool permission policy becomes hard to reason about without a formal graph.

Acceptance criteria for adding any framework:

- It replaces local complexity that already exists or is clearly imminent.
- It does not force role prompts to own orchestration.
- It can run locally against vLLM.
- It does not make basic setup fragile.
- It has deterministic test seams for controller behavior.

## Drift Controls

Before implementing controller-service work, answer these:

1. Is this direct model transport, workflow control, or tool execution?
2. Is the request explicit enough to avoid accidental repo-wide work?
3. Can the behavior be tested without vLLM?
4. Does it preserve read-only target repo defaults?
5. Are returned harness responses bounded?
6. Are full details persisted as artifacts instead of injected into the chat response?
7. Does the role receive only the current bounded packet?

If any answer is unclear, update this roadmap before implementing the behavior.

## Immediate Next Step

Phase 6 completed the first service-backed documenter example. The next roadmap phase remains deferred hardening and framework review unless a concrete local-controller limit appears.
