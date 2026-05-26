# Implementation Workflow

The implementation workflow turns approved work into bounded implementation packets with draft/apply policy, state, and verification capture.

It does not make the documenter an implementer. It consumes approved change-plan items or explicit user-provided packets and then enforces file scope, operation scope, output location, and verification policy.

## Capabilities

- Builds `implementation-plan-*.json`.
- Writes resumable `implementation-state-*.json`.
- Writes final `implementation-report-*.json`.
- Defaults to draft-only output under `implementation-drafts/<run-id>/`.
- Supports explicit `--mode apply`.
- Refuses out-of-scope writes.
- Refuses untracked apply targets.
- Records before/after hashes in apply mode.
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

## Verification Policy

Verification commands are controller-declared and policy-limited to pytest-style commands:

- `pytest ...`
- `python -m pytest ...`
- `python3 -m pytest ...`

## References

- Examples: [docs/examples/implementation-workflow.md](docs/examples/implementation-workflow.md)
- Roadmap phase: [docs/DOCUMENTER_E2E_ROADMAP.md](docs/DOCUMENTER_E2E_ROADMAP.md#phase-13-implementation-workflow)
