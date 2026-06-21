# EIG Breadth Closeout

Status: Phase 296.

This feature aggregates the EIG-1 connector breadth and EIG-2 identity/scope proof chain into a contextless closeout packet.

The closeout gate reruns Phase 289-295 validators, checks required docs and runtime fixtures, confirms status coverage for the approved connector archetypes, and proves the source `runtime/connectors.json` does not mutate during validation.

## Files

- `runtime/eig_breadth_closeout_policy.json`: required docs, runtime files, milestones, phases, and coverage markers.
- `vllm_agent_gateway/acceptance/eig_breadth_closeout.py`: closeout aggregator.
- `scripts/validate_eig_breadth_closeout.py`: CLI wrapper.

## Validation

Offline closeout:

```bash
python3 scripts/validate_eig_breadth_closeout.py \
  --output-path runtime-state/eig-breadth-closeout/phase296-validation.json
```

Live workflow-router closeout:

```bash
python3 scripts/validate_eig_breadth_closeout.py \
  --live-runtime \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --output-path runtime-state/eig-breadth-closeout/phase296-live-validation.json
```

Live workflow-router plus AnythingLLM closeout:

```bash
python3 scripts/validate_eig_breadth_closeout.py \
  --live-runtime \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --include-anythingllm \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --anythingllm-workspace my-workspace \
  --controller-base-url http://127.0.0.1:8400 \
  --output-path runtime-state/eig-breadth-closeout/phase296-live-anythingllm-validation.json
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_eig_breadth_closeout.py -q
python3 -m pytest tests/regression/test_eig_runtime_breadth_chat.py tests/regression/test_controller_service.py::test_workflow_router_chat_natural_connector_fixture_returns_inline_result_without_registry_mutation -q
```

Full regression required at phase close:

```bash
python3 -m pytest tests/regression/ -v
```

## Closeout Standard

Phase 296 is complete only when:

- Phase 289-295 validators pass.
- Required EIG docs and runtime fixtures exist and are indexed.
- Required coverage markers are present for work tracking, knowledge/document lookup, business-record lookup, read operations, write dry-run operations, positive cases, negative controls, protocol/auth/schema, release gate, registry lifecycle, actor scope, approval replay, and natural-language chat.
- Source `runtime/connectors.json` remains unchanged.
- Live workflow-router proof passes for the exposed natural connector prompts when the runtime stack is available.
- AnythingLLM proof passes for the exposed natural connector prompts when the API key and reachable AnythingLLM API address are available.
- Focused connector/EIG regression passes.
- Docs index validation passes.
- Full Bash regression passes.

## Known Limits

This closeout proves the approved deterministic local-stub breadth slice. It does not prove real external connector execution, enterprise-specific connectors, production OAuth token exchange, raw MCP access, Kubernetes deployment, production PII handling, or arbitrary natural-language connector invocation.
