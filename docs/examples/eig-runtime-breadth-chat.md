# EIG Runtime Breadth Chat Examples

Run the Phase 295 direct validator:

```bash
python3 scripts/validate_eig_runtime_breadth_chat.py
```

Expected success marker:

```text
EIG RUNTIME BREADTH CHAT PASSED
mode=direct
case_count=3
passed_case_count=3
failed_case_count=0
source_connector_registry_changed=False
phase296_ready=True
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_eig_runtime_breadth_chat.py -q
python3 -m pytest tests/regression/test_controller_service.py::test_workflow_router_chat_natural_connector_fixture_returns_inline_result_without_registry_mutation -q
```

Run live workflow-router proof:

```bash
python3 scripts/validate_eig_runtime_breadth_chat.py --base-url http://127.0.0.1:8500/v1
```

Run AnythingLLM API proof:

```bash
python3 scripts/validate_eig_runtime_breadth_chat.py \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --anythingllm-workspace my-workspace \
  --controller-base-url http://127.0.0.1:8400
```

Example natural prompt:

```text
Using the local connector fixture, look up the work item status. Read only. Return the result and audit summary.
```

Expected chat answer fragments:

```text
Connector Result:
- Connector: work_tracking_stub.lookup_work_item
- Status: completed
- Authorization: allowed
- Result: priority=medium; status=open; title=Synthetic work item ready for review
- Audit: decision=allowed; approval_state=not_required; raw_auth_subject_stored=False; raw_arguments_stored=False
- Runtime registry mutation: false
- Target repository mutation: false
```

Do not add fixture connectors to the source `runtime/connectors.json` to make this proof pass. Phase 295 intentionally uses a disposable runtime catalog so EIG admission, registry, and duplicate controls remain meaningful.
