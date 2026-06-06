# Controlled Small-Change Apply

`implementation.workflow` is the controller-owned edit engine for approved small changes. It can draft patch previews without mutating source files and can apply exact packet operations only after explicit real-apply approval.

The workflow is intentionally narrow. It supports exact `replace_text`, `append_text`, and draft-only `create_file` packet operations through one canonical implementation path. The workflow writes patch previews, before/after hashes, verification results, rollback metadata, and durable reports.

## When To Use It

Use controlled apply after a small L1/L2 request has produced exact packet operations and the tester wants one of these outcomes:

- dry-run patch preview with no source mutation
- disposable-copy apply proof before any real source apply
- real apply to an allowed non-protected target root after explicit approval

Do not use this workflow for broad refactors, ambiguous edits, generated patches without exact anchors, or protected frozen fixture source mutation.

## Direct Controller Endpoint

```text
POST /v1/controller/implementation-runs
```

Dry-run example:

```json
{
  "workflow": "implementation.workflow",
  "schema_version": 1,
  "target_root": "/path/to/repo",
  "mode": "dry_run",
  "approval": {
    "status": "approved_for_small_change_dry_run",
    "scope": "patch_preview_only",
    "apply_allowed": false,
    "approval_refs": ["founder-approved dry run"]
  },
  "packet_operations": [
    {
      "kind": "replace_text",
      "path": "README.md",
      "old": "exact old text",
      "new": "exact new text"
    }
  ],
  "no_structure_index": true
}
```

Real apply requires stronger approval:

```json
{
  "status": "approved_for_real_apply",
  "apply_allowed": true,
  "apply_scope": "target_root",
  "explicit_real_apply": true,
  "approval_refs": ["founder-approved real apply"]
}
```

Real apply is blocked for the protected frozen fixture roots:

- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

Use disposable-copy apply for those fixtures.

## Natural Disposable-Copy Apply

AnythingLLM and other OpenAI-compatible clients should go through the workflow-router gateway at:

```text
http://127.0.0.1:8500/v1
```

Natural disposable-copy apply requires all of the following in the user message:

- explicit approved disposable-copy apply intent
- exact `packet_operations` JSON
- an allowed target root path

The router copies the target repository, applies the exact operation through `implementation.workflow`, records mutation proof, rolls the copy back, and proves the source repository stayed unchanged.

## Artifacts

Direct implementation artifacts include:

- `implementation_plan`
- `implementation_state`
- `implementation_report`
- patch preview files under the implementation draft/patch artifact directory

Workflow-router disposable apply artifacts include:

- `route-decision.json`
- `downstream-result.json`
- downstream `implementation_report`
- `disposable-mutation-sandbox-contract.json`
- `disposable-mutation-diff.json`
- `disposable-rollback-proof.json`
- `disposable-mutation-proof.json`

Key proof fields:

- `patch_preview`
- `before_sha256`
- `after_sha256`
- `rollback_operation`
- `source_changed`
- `copy_changed`
- `sandbox_contract.status`
- `structured_diff.changed_file_count`
- `rollback.status`

## Validation

Focused regression:

```bash
python -m pytest tests/regression/test_controlled_small_change_apply.py tests/regression/test_implementation_workflow.py -q
```

Live Bash validation:

```bash
python3 scripts/validate_controlled_small_change_apply_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

## References

- Examples: [docs/examples/controlled-apply.md](docs/examples/controlled-apply.md)
- Mutation sandbox proof: [README.mutation-sandbox.md](README.mutation-sandbox.md)
- Workflow router: [README.workflow-router.md](README.workflow-router.md)
- Implementation workflow: [README.implementation-workflow.md](README.implementation-workflow.md)
- Roadmap: [docs/ACTIONABLE_WORKFLOW_ROADMAP.md](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
