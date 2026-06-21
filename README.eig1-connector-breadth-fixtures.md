# EIG-1 Connector Breadth Fixtures

This feature validates the Phase 289 connector breadth fixture pack for EIG-1.

It proves the governed connector framework is not limited to the original `ticketing_stub` sample by validating three deterministic local connector archetypes:

- work tracking,
- knowledge/document lookup,
- structured business-record lookup.

## When To Use It

Use this gate when changing connector manifests, connector catalog validation, connector mediation, or EIG-1 roadmap proof.

It does not call real external APIs, perform real OAuth token exchange, expose raw MCP tools, register production connectors, or mutate target repositories.

## Inputs

- `docs/EIG1_CONNECTOR_ARCHETYPE_BREADTH_MATRIX.md`
- `runtime/eig1_connector_breadth_fixtures.json`
- existing connector catalog and mediation modules:
  - `vllm_agent_gateway/connectors/catalog.py`
  - `vllm_agent_gateway/connectors/mediator.py`
  - `vllm_agent_gateway/connectors/identity.py`

## Output

The validator writes an `eig1_connector_breadth_report` JSON artifact under:

```text
runtime-state/eig1-connector-breadth/
```

The report includes manifest validation summaries, positive invocation summaries, negative-control outcomes, and replay-safe audit summaries. It must not retain raw fixture argument values.

## Run

```bash
python3 scripts/validate_eig1_connector_breadth.py
python3 -m pytest tests/regression/test_eig1_connector_breadth.py -q
```

On Windows PowerShell:

```powershell
python scripts/validate_eig1_connector_breadth.py
python -m pytest tests/regression/test_eig1_connector_breadth.py -q
```

## Pass Criteria

The gate passes only when:

- all three archetypes are present,
- all valid manifests pass `connector_catalog.validate`,
- at least one read operation exists per archetype,
- at least one write-class dry-run operation exists across the set,
- positive invocations run through `connector.invoke`,
- unknown connector, disabled connector, unknown operation, unsupported argument, missing argument, unsafe write, non-local-stub execution, raw MCP, and direct model-tool bypass controls fail closed,
- audit summaries avoid raw auth subject and raw argument storage,
- runtime registry and target repository mutation flags remain false.

## Next Phase

Phase 290 expands protocol, auth, and schema classification. It should reuse this fixture pack and the existing connector catalog/mediation paths rather than adding a second connector framework.
