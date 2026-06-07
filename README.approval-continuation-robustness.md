# Approval Continuation Robustness

Approval continuation robustness is the workflow-router capability that makes natural "approve this plan" follow-ups hard to misuse.

It applies to packet-design continuations only. The referenced source run must still be waiting for `packet_design` approval, the continuation must name the run ID, the target path must match the source run, and the request must stay draft-only.

## When To Use It

Use this when a tester receives a chat-visible approval state like:

```text
Approval:
- State: waiting_for_approval
- Type: packet_design
```

The continuation should explicitly name the run and provide exact packet operations:

```text
Approve packet design for run workflow-router-... .
Use packet operations: [{"kind":"append_text","path":"README.md","content":"\n<!-- reviewed -->\n"}]
```

## Output Contract

Successful continuations return chat-visible approval state:

- `State: finished`
- `Type: packet_design`
- next action text
- downstream draft implementation-prep artifacts
- `source_changed=false`

Failure cases fail closed:

- duplicate approval: `approval_already_consumed`
- denied approval: `approval_denied`
- stale approval: `approval_expired`
- wrong run state: `approval_not_pending`
- target or apply-scope change: `approval_scope_changed`

Through the workflow-router gateway, these failures are returned as OpenAI-style chat messages so AnythingLLM can show the reason instead of a generic provider error.

## Validation

The governed case catalog is:

```text
runtime/approval_continuation_robustness_cases.json
```

Run direct validation:

```bash
python3 scripts/validate_approval_continuation_robustness.py \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-direct.json
```

Run live gateway validation from Bash:

```bash
python3 scripts/validate_approval_continuation_robustness.py \
  --skip-direct \
  --live-gateway \
  --port-health \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-gateway.json
```

Run AnythingLLM validation after the API key is visible to Bash:

```bash
python3 scripts/validate_approval_continuation_robustness.py \
  --skip-direct \
  --live-anythingllm \
  --port-health \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-anythingllm.json
```

The live validators cover localhost model `8000`, workflow-router gateway `8500`, controller `8400`, featured role ports, AnythingLLM when enabled, `/mnt/c/coinbase_testing_repo_frozen_tmp`, and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.

## Safety Constraints

- Approval is bound to the referenced run ID.
- The continuation target must match the source run target.
- Packet-design approval cannot become source apply.
- Duplicate and denied approvals cannot be reused.
- Frozen fixture hashes, tree digest, and git status must remain unchanged.
