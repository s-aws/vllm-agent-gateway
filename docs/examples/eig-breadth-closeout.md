# EIG Breadth Closeout Examples

Run the Phase 296 closeout:

```bash
python3 scripts/validate_eig_breadth_closeout.py
```

Expected success marker:

```text
EIG BREADTH CLOSEOUT PASS
```

Expected summary shape:

```json
{
  "coverage_missing_count": 0,
  "failed_phase_report_count": 0,
  "missing_doc_count": 0,
  "missing_runtime_file_count": 0,
  "phase_report_count": 7,
  "source_connector_registry_changed": false,
  "status": "passed"
}
```

Run live workflow-router proof for the Phase 295 natural connector prompts:

```bash
python3 scripts/validate_eig_breadth_closeout.py \
  --live-runtime \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --output-path runtime-state/eig-breadth-closeout/phase296-live-validation.json
```

Run live workflow-router plus AnythingLLM proof:

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

Run focused tests:

```bash
python3 -m pytest tests/regression/test_eig_breadth_closeout.py -q
python3 -m pytest tests/regression/test_eig_runtime_breadth_chat.py tests/regression/test_controller_service.py::test_workflow_router_chat_natural_connector_fixture_returns_inline_result_without_registry_mutation -q
```

Do not treat an offline pass as production connector readiness. Offline closeout proves the deterministic local-stub evidence chain. Live gateway and full regression proof are still required before claiming phase closeout.
