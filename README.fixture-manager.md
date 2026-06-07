# Fixture Manager

The fixture manager validates fixture manifests, snapshots protected source state, creates disposable copies, and cleans up managed fixture runs.

It replaces hand-managed fixture-copy logic for validation paths that need real or synthetic repositories without mutating protected sources.

## Manifest

The canonical manifest is:

```text
runtime/fixtures.json
```

It currently includes:

- `coinbase-frozen`
- `coinbase-frozen-git`
- `python-service-generalization`
- `node-cli-generalization`
- `go-http-generalization`

Each fixture entry declares:

- source path
- category
- protected/disposable-only flags
- watched source files
- description

## Commands

Validate the manifest:

```bash
python scripts/manage_fixtures.py validate
```

Snapshot one fixture:

```bash
python scripts/manage_fixtures.py snapshot \
  --fixture-id python-service-generalization
```

Create a disposable copy and clean it up in the same run:

```bash
python scripts/manage_fixtures.py setup \
  --fixture-id python-service-generalization \
  --run-id phase74-smoke \
  --cleanup-after
```

Clean up a managed run:

```bash
python scripts/manage_fixtures.py cleanup \
  --run-id phase74-smoke
```

Run the multi-repo live fixture validator from Bash:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_multi_repo_fixtures_live.py --timeout-seconds 900
```

Run the Phase 101 live proof with port health and AnythingLLM:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_multi_repo_fixtures_live.py \
  --port-health \
  --live-anythingllm \
  --timeout-seconds 900
```

Reports are written under:

```text
runtime-state/fixture-manager/
```

## Safety

- Cleanup is constrained to the configured managed output root.
- Disposable copies are created under `runtime-state/managed-fixtures/` by default.
- Source watched hashes and git status are checked before and after setup.
- `.git`, `__pycache__`, `.pytest_cache`, and `.mypy_cache` directories are excluded from copied fixtures.
- Protected source fixtures remain disposable-only.

## Current Integration

The generalization fixture validator delegates copy, cleanup, and hash-tree behavior to this manager while preserving its existing command interface.

Phase 82 added `node-cli-generalization` and `scripts/validate_multi_repo_fixtures_live.py` so live workflow-router proof covers both frozen Coinbase fixtures and a non-Coinbase JavaScript/Node CLI repository shape. Phase 101 adds `go-http-generalization` and extends that validator to prove gateway plus AnythingLLM routing across Coinbase, Python service, Node CLI, and Go HTTP fixture categories.
