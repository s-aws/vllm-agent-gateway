# Refactor Single Path

`refactor.single_path` is a controller-owned workflow that starts with read-only code investigation and gates any implementation planning behind explicit approval.

It does not apply edits. In `dry_run` mode it delegates packet design to `execution_planning.plan`, which uses `implementation.workflow` in draft mode only.

## When To Use It

Use this workflow when a tester or agent needs to:

- investigate the likely beginning point for a behavior
- identify whether bounded evidence suggests possible parallel behavior paths
- produce an approval-gated refactor plan artifact
- optionally generate draft packet artifacts after packet-design approval

Do not use it for apply mode, natural-language implicit repo edits, or raw CodeGraphContext access.

## Modes

`investigation_only`:

- runs `code_investigation.plan`
- writes a `refactor-plan.json`
- stops with `refactor_status: "approval_required"`

`dry_run`:

- requires `approval.status: "approved_for_packet_design"`
- rejects `approval.apply_allowed: true`
- requires explicit `packet_operations`
- runs `code_investigation.plan`
- delegates to `execution_planning.plan`
- writes draft packet artifacts only

## Endpoints

Direct controller endpoint:

```text
POST /v1/controller/refactor/single-path
```

OpenAI-style harness endpoint:

```text
POST /v1/controller/harness/chat/completions
```

The harness endpoint requires an explicit `agentic_controller_request` envelope.

## Artifacts

Artifacts are written under:

```text
CONTROLLER_OUTPUT_ROOT/refactor-single-path/<run-id>/
```

Typical artifacts:

- `request.json`
- `refactor-plan.json`
- nested `code_investigation.plan` artifacts
- nested `execution_planning.plan` artifacts in `dry_run` mode
- `run-state.json`

## Validation

Regression covers:

- investigation-only approval gate
- dry-run delegation to `execution_planning.plan`
- harness adapter execution with prior envelope history
- dry-run approval refusal

Live Bash validation has also passed through:

- direct controller endpoint on `8400`
- gateway controller-envelope route on `8300`
- AnythingLLM workspace chat with AnythingLLM pointed at `http://127.0.0.1:8300/v1`
- both frozen validation fixtures in investigation-only mode
- AnythingLLM dry-run delegation on the copied frozen fixture, with selected file hash unchanged

Examples: [docs/examples/refactor-single-path.md](docs/examples/refactor-single-path.md).
