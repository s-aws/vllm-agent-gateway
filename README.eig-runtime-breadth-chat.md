# EIG Runtime Breadth Chat

This feature validates the Phase 295 runtime chat proof for selected EIG connector breadth fixtures.

It proves a user can ask a semi-well-defined natural-language connector prompt and receive a useful chat answer through the workflow-router surface. The route is intentionally narrow: it exposes only deterministic local connector fixtures and still runs through the existing `connector.invoke` controller mediation path.

## When To Use It

Use this gate when changing natural workflow-router routing, connector invocation formatting, connector audit summaries, operation-level scope handling, or EIG runtime chat proof.

It does not expose arbitrary connector calls, raw MCP access, direct model-to-connector tools, real external APIs, production OAuth exchange, or source/runtime registry mutation.

## Inputs

- `runtime/eig_runtime_breadth_chat_cases.json`
- `runtime/eig1_connector_breadth_fixtures.json`
- `runtime/eig2_actor_scope_breadth_policy.json`
- `runtime/connectors.json`
- `vllm_agent_gateway/controller_service/server.py`
- `vllm_agent_gateway/acceptance/eig_runtime_breadth_chat.py`

The validator builds a disposable runtime root and enables the approved local-stub connectors only for the current proof. The source `runtime/connectors.json` must remain unchanged.

## Output

The validator writes an `eig_runtime_breadth_chat_report` JSON artifact under:

```text
runtime-state/acceptance/eig-runtime-breadth-chat-report.json
```

The report includes prompt case outcomes, workflow selection, run IDs, artifact keys, blind-baseline contract criteria, and mutation-safety status.

## Run

Direct controller proof:

```bash
python3 scripts/validate_eig_runtime_breadth_chat.py
python3 -m pytest tests/regression/test_eig_runtime_breadth_chat.py -q
python3 -m pytest tests/regression/test_controller_service.py::test_workflow_router_chat_natural_connector_fixture_returns_inline_result_without_registry_mutation -q
```

Live workflow-router proof:

```bash
python3 scripts/validate_eig_runtime_breadth_chat.py --base-url http://127.0.0.1:8500/v1
```

AnythingLLM API proof:

```bash
python3 scripts/validate_eig_runtime_breadth_chat.py \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --anythingllm-workspace my-workspace \
  --controller-base-url http://127.0.0.1:8400
```

Use the Windows-reachable WSL network URL instead of `127.0.0.1` when AnythingLLM or another Windows client receives headers but times out waiting for body bytes.

If another local development server is bound to `127.0.0.1:3001`, Bash-side AnythingLLM API tests may need the AnythingLLM non-loopback address, such as the LAN or WSL-reachable address that returns `{"online":true}` from `/api/ping`.

## Pass Criteria

The gate passes only when every selected prompt:

- routes through `connector.invoke`,
- completes successfully,
- returns the connector result in chat,
- includes authorization and read-only audit facts,
- includes route and connector invocation artifacts,
- uses operation-level required scopes where applicable,
- reports no runtime registry or target repository mutation,
- stores no raw auth subject and no raw arguments in audit artifacts,
- preserves the source `runtime/connectors.json` hash.

## Current Prompt Coverage

- work item lookup through `work_tracking_stub.lookup_work_item`,
- business record lookup through `business_record_stub.lookup_business_record`,
- document search through `knowledge_lookup_stub.search_documents`.

## Next Phase

Phase 296 aggregates the EIG-1 and EIG-2 breadth evidence, adds contextless audit closeout, runs required live proofs for exposed connector prompts, and ends with full Bash regression.
