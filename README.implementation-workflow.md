# Implementation Workflow

The implementation workflow turns approved work into bounded implementation packets with draft/apply policy, state, and verification capture.

It does not make the documenter an implementer. It consumes approved change-plan items or explicit user-provided packets and then enforces file scope, operation scope, output location, and verification policy.

## Capabilities

- Builds `implementation-plan-*.json`.
- Writes resumable `implementation-state-*.json`.
- Writes final `implementation-report-*.json`.
- Defaults to draft-only output under `implementation-drafts/<run-id>/`.
- Writes unified diff patch previews for draft and apply operations.
- Supports explicit `--mode apply`.
- Refuses out-of-scope writes.
- Refuses untracked apply targets.
- Records before/after hashes in apply mode.
- Records rollback operation metadata for applied packets.
- Captures verification command exit codes, bounded excerpts, and output hashes.
- Uses Phase 12 structure slices in packets when enabled.

## Packet Sources

- Approved `safe_documentation_edit` items from a documenter report.
- Explicit packet JSON files.

## Supported Operations

- `append_text`
- `replace_text`
- `create_file`

Apply mode is intentionally stricter than draft mode. It refuses `create_file` and refuses untracked files until a future unsafe/create policy is explicitly added.

## Patch And Rollback Artifacts

Every completed packet records a `patch_preview` path. Draft mode writes the proposed file content under the draft artifact directory and leaves the target repository unchanged. Apply mode writes the target file only after explicit apply mode is selected, then records `before_sha256`, `after_sha256`, `rollback_operation`, and `rollback_hint`.

The controller-owned controlled apply wrapper adds approval gates around this same implementation path. See [README.controlled-apply.md](README.controlled-apply.md).

## Verification Policy

Verification commands are controller-declared and policy-limited to pytest-style commands:

- `pytest ...`
- `python -m pytest ...`
- `python3 -m pytest ...`

## References

- Examples: [docs/examples/implementation-workflow.md](docs/examples/implementation-workflow.md)
- Roadmap phase: [docs/DOCUMENTER_E2E_ROADMAP.md](docs/DOCUMENTER_E2E_ROADMAP.md#phase-13-implementation-workflow)
