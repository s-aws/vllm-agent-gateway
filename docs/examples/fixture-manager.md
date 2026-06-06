# Fixture Manager Examples

These examples manage disposable copies of registered fixtures.

## Validate The Manifest

```bash
cd /mnt/c/agentic_agents
python3 scripts/manage_fixtures.py validate
```

Expected markers:

```text
FIXTURE MANAGER REPORT ...
FIXTURE MANAGER SUMMARY ...
FIXTURE MANAGER PASS
```

## Snapshot The Python Service Fixture

```bash
python3 scripts/manage_fixtures.py snapshot \
  --fixture-id python-service-generalization \
  --report-path runtime-state/fixture-manager/phase74-python-service-snapshot.json
```

Expected report fields:

```text
kind=fixture_manager_report
command=snapshot
fixtures[0].fixture_id=python-service-generalization
snapshots[0].watched_hashes={...}
```

## Snapshot The Node CLI Fixture

```bash
python3 scripts/manage_fixtures.py snapshot \
  --fixture-id node-cli-generalization \
  --report-path runtime-state/fixture-manager/node-cli-snapshot.json
```

Expected report fields:

```text
kind=fixture_manager_report
command=snapshot
fixtures[0].fixture_id=node-cli-generalization
fixtures[0].category=synthetic-node-cli
snapshots[0].watched_hashes={...}
```

## Setup And Cleanup A Disposable Copy

```bash
python3 scripts/manage_fixtures.py setup \
  --fixture-id python-service-generalization \
  --run-id phase74-smoke \
  --cleanup-after \
  --report-path runtime-state/fixture-manager/phase74-smoke.json
```

Expected report fields:

```text
status=passed
setup[0].source_unchanged=true
setup[0].copy_hash_count>0
cleanup.removed=true
```

## Cleanup Only

```bash
python3 scripts/manage_fixtures.py cleanup \
  --run-id phase74-smoke
```

Cleanup refuses run roots outside the configured managed output root.

## Multi-Repo Live Fixture Validation

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_multi_repo_fixtures_live.py \
  --timeout-seconds 900 \
  --output-path runtime-state/multi-repo-fixtures/manual.json
```

Expected marker:

```text
MULTI REPO FIXTURE PASS
```

The validator runs natural workflow-router prompts against:

- `coinbase-frozen`
- `coinbase-frozen-git`
- `node-cli-generalization`
