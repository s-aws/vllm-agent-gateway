# Runtime-State Hygiene

`runtime-state/` is for generated local validation reports, screenshots, controller run artifacts, temporary disposable-copy workspaces, and other proof files created while testing the harness.

It must stay local-only. Do not commit generated `runtime-state/` files.

## What Is Committed

Committed files should include:

- source code
- runtime manifests under `runtime/`
- compact durable proof metadata under `runtime/release_proofs/`
- README files and examples that summarize proof and rerun commands

The current committed stable activation proof is:

```text
runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

That file is intentionally small. It records that stable was activated from a passed V1.1 release-candidate acceptance report while preserving the boundary that advanced broad refactor orchestration is still deferred.

## What Stays Local

Generated reports stay under ignored paths such as:

```text
runtime-state/v1-acceptance/
runtime-state/release-channels/
runtime-state/anythingllm-ui/
runtime-state/controller-artifacts/
```

These reports are valuable during active work, but they are not the source of truth for a clean clone. If a report is needed for future release validation, commit a compact proof summary under `runtime/release_proofs/` and link the rerun command in docs.

## Hygiene Gate

Run:

```bash
python scripts/check_runtime_state_hygiene.py \
  --output-path runtime-state/runtime-state-hygiene/current.json
```

Expected result:

```text
RUNTIME STATE HYGIENE PASS
```

The gate checks:

- `git ls-files runtime-state` returns no tracked generated runtime files
- `git check-ignore -v` proves ignore coverage for top-level, nested validator, and controller-artifact report paths
- committed stable proof metadata exists and is valid
- release-channel stable metadata points at the committed proof
- runtime-state policy docs are indexed

## Retention Rule

Use this rule when adding future validation:

- write detailed reports to ignored `runtime-state/`
- write durable proof summaries to docs or `runtime/release_proofs/`
- link commands from `docs/README.md` and feature examples
- do not depend on a generated `runtime-state/` file existing in a clean clone
- use explicit report paths during audits; do not glob all of `runtime-state/`
- treat old `debug-*` reports and stale local artifacts as noncanonical unless current docs or the roadmap explicitly name them

Examples: [docs/examples/runtime-state.md](docs/examples/runtime-state.md).
