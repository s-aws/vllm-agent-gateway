# Approval Continuation Robustness Examples

## Ask For A Reviewable Edit First

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, make a small documentation edit to README.md. Add a note saying Phase 97 continuation marker. Show the proposed edit before applying.
```

Expected response markers:

```text
Approval:
- State: waiting_for_approval
- Type: packet_design
```

## Approve Exact Packet Design

```text
Approve packet design for run workflow-router-YYYYMMDDTHHMMSSffffffZ. Use packet operations: [{"kind":"append_text","path":"README.md","content":"\n<!-- Phase 97 continuation marker -->\n"}]
```

Expected response markers:

```text
Approval:
- State: finished
- Type: packet_design
```

The response should also include downstream draft artifacts and `source_changed=false`.

## Duplicate Approval

Send the same approval message again.

Expected failure marker:

```text
approval_already_consumed
```

## Deny Approval

```text
Deny packet design approval for run workflow-router-YYYYMMDDTHHMMSSffffffZ.
```

Expected failure marker:

```text
approval_denied
```

## Scope Change Refusal

```text
Approve packet design for run workflow-router-YYYYMMDDTHHMMSSffffffZ. Use packet operations: [{"kind":"append_text","path":"README.md","content":"\n<!-- marker -->\n"}] Apply the change to source now.
```

Expected failure marker:

```text
approval_scope_changed
```

## Validator Commands

```bash
python3 scripts/validate_approval_continuation_robustness.py \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-direct.json
```

```bash
python3 scripts/validate_approval_continuation_robustness.py \
  --skip-direct \
  --live-gateway \
  --port-health \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-gateway.json
```

```bash
python3 scripts/validate_approval_continuation_robustness.py \
  --skip-direct \
  --live-anythingllm \
  --port-health \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-anythingllm.json
```
