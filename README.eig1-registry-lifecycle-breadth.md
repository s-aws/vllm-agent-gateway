# EIG-1 Registry Lifecycle Breadth

This feature validates Phase 292 registry lifecycle breadth for EIG-1 connector fixtures.

It exercises the existing `connector_catalog.register` path on disposable runtime copies and proves draft registration, enabled registration, disabled invocation denial, duplicate rejection, stale release-gate validation rejection, and release-gate mismatch rejection for every Phase 289 EIG-1 connector fixture.

## Scope

This gate must not mutate the real runtime registry. It creates disposable runtime copies and verifies hash deltas for each scenario.

Update and deprecation semantics are explicitly deferred as a future milestone candidate.

## Run

```bash
python3 scripts/validate_eig1_registry_lifecycle_breadth.py
python3 -m pytest tests/regression/test_eig1_registry_lifecycle_breadth.py -q
```

On Windows PowerShell:

```powershell
python scripts/validate_eig1_registry_lifecycle_breadth.py
python -m pytest tests/regression/test_eig1_registry_lifecycle_breadth.py -q
```

## Output

The validator writes an `eig1_registry_lifecycle_breadth_report` under:

```text
runtime-state/eig1-registry-lifecycle-breadth/
```

`phase296_ready=true` means the EIG-1 breadth proof chain is ready for EIG closeout after any required EIG-2 phases.
