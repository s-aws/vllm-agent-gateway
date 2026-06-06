# Execution Planning Workflow

`execution_planning.plan` is a controller-owned workflow that turns an explicit planning request into bounded planning artifacts, optional implementation packet candidates, a draft packet preview, a verification plan, and a feedback record.

It is for founder/tester workflow validation and implementation preparation. It is not a normal chat path, and it does not infer repository work from ordinary natural-language messages.

## When To Use It

Use this workflow when you need an agent to:

- triage a requested task
- find the likely entrypoint
- gather bounded repository context
- produce an evidence-backed execution plan
- design implementation packet candidates after packet-design approval
- run a draft-only compatibility check through `implementation.workflow`
- prove selected target files were not mutated

Do not use it for applying edits. The current workflow version rejects apply mode and only invokes `implementation.workflow` in `draft` mode.

Approved apply behavior is tested separately through the existing `implementation.workflow` on disposable copies of the frozen validation repositories. Mutation tests must never run against the source frozen fixtures.

## Endpoint

Direct controller endpoint:

```text
POST /v1/controller/execution-planning/plans
```

Harness adapter endpoint:

```text
POST /v1/controller/harness/chat/completions
```

The harness adapter requires an explicit `agentic_controller_request` envelope. Ordinary natural-language chat is rejected with `missing_controller_envelope`.

When a chat harness includes prior messages, the active message-content envelope is the latest message containing exactly one `agentic_controller_request`. Older controller envelopes in history are ignored; top-level plus message ambiguity and multiple envelopes inside the active message are still rejected.

## Key Concepts

- `workflow`: must be `execution_planning.plan`.
- `target_root`: must be under `CONTROLLER_ALLOWED_TARGET_ROOTS`.
- `mode`: one of `investigation_only`, `implementation_prep`, or `dry_run`.
- `packet_operations`: exact intended packet operations. Required for `implementation_prep` and `dry_run` in this controller version.
- `approval`: packet candidate creation requires `approval.status: "approved_for_packet_design"` and `apply_allowed: false`.
- `context.allowed_context_tools`: limited to `structure_index`, `git_grep`, `read_file`, and `manual`.

Raw CodeGraphContext operations, raw Cypher, watcher/indexing control, and broad model-visible repository tools are rejected by this workflow.

## Artifacts

Artifacts are written under `CONTROLLER_OUTPUT_ROOT/execution-planning/<run-id>/`.

Typical `dry_run` artifacts:

- `request.json`
- `request-triage.json`
- `scope-and-assumptions.json`
- `entrypoint-finder.json`
- `context-plan.json`
- `context-results.json`
- `context-results-for-model.json`
- `impact-map.json`
- `execution-plan.json`
- `implementation-packet-candidates.json`
- `packet-preview.json`
- `verification-plan.json`
- `implementation-workflow-report.json`
- `feedback-record.json`
- `run-state.json`

The compact response includes artifact paths, a summary, tool-policy audit data, and `non_mutation.changed_files`.

`context-results.json` remains the full controller-owned evidence artifact. `context-results-for-model.json` is the bounded model-facing version used by downstream skills such as `impact-map-builder`; it preserves exact packet operations and source refs while compacting large structure-index slices.

## Validation Boundary

Required validation covers the direct model on `localhost:8000`, the gateway, all role ports in `runtime/roles.json`, the controller service, the controller harness adapter, both frozen validation repositories, AnythingLLM, and mutation testing on disposable fixture copies.

AnythingLLM validation is not satisfied by a normal chat response. It is only satisfied when the response includes controller output such as `agentic_controller_response`, a run ID, bounded artifact paths, and non-mutation proof.

Run the current live runtime matrix from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"
PYTHONUNBUFFERED=1 python3 scripts/validate_live_execution_planning_matrix.py --mode dry_run --timeout-seconds 900
```

The matrix covers the local model, gateway, controller, all role ports, AnythingLLM provider configuration, direct gateway dry runs, AnythingLLM dry runs, both frozen fixtures, and mutation probes on disposable copies.

## References

- Schema: [docs/EXECUTION_PLANNING_CONTROLLER_WORKFLOW_SCHEMA.md](docs/EXECUTION_PLANNING_CONTROLLER_WORKFLOW_SCHEMA.md)
- Examples: [docs/examples/execution-planning-harness.md](docs/examples/execution-planning-harness.md)
- Roadmap: [docs/ACTIONABLE_WORKFLOW_ROADMAP.md](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
