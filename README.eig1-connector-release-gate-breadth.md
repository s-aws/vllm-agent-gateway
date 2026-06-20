# EIG-1 Connector Release Gate Breadth

This feature validates Phase 291 connector release-gate breadth across the EIG-1 fixture set.

It generates release packets for every Phase 289 connector fixture and validates them through the existing connector eval release gate. It also mutates a representative packet to prove the release gate rejects required failure classes.

## Scope

This is release-gate proof only. It does not register connectors, enable production connectors, call external APIs, expose natural-language connector workflows, or mutate target repositories.

## Run

```bash
python3 scripts/validate_eig1_connector_release_gate_breadth.py
python3 -m pytest tests/regression/test_eig1_connector_release_gate_breadth.py -q
```

On Windows PowerShell:

```powershell
python scripts/validate_eig1_connector_release_gate_breadth.py
python -m pytest tests/regression/test_eig1_connector_release_gate_breadth.py -q
```

## Output

The validator writes an `eig1_connector_release_gate_breadth_report` under:

```text
runtime-state/eig1-connector-release-gate-breadth/
```

`phase292_ready=true` means the EIG-1 release-gate breadth proof is ready for registry lifecycle breadth testing.
