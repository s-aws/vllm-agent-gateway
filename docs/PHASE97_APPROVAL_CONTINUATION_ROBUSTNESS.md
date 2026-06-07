# Phase 97 Approval Continuation Robustness

Phase 97 hardens natural approval continuations so packet-design approval cannot be reused, redirected, or silently expanded into apply scope.

## Implemented

- Bound packet-design approval continuations to the referenced source run target.
- Rejected natural-language target mismatches in approval messages.
- Rejected approval messages that try to convert draft packet design into source apply.
- Added deterministic `approval_continuation_packet_prep` execution-planning path for exact packet-operation continuations.
- Kept direct controller errors fail-closed with explicit error codes.
- Converted workflow-router gateway controller approval errors into OpenAI-style chat responses for AnythingLLM-visible failure reasons.
- Added `runtime/approval_continuation_robustness_cases.json`.
- Added `vllm_agent_gateway.acceptance.approval_continuation_robustness` and `scripts/validate_approval_continuation_robustness.py`.
- Added `README.approval-continuation-robustness.md` and `docs/examples/approval-continuation-robustness.md`.

## Proof Artifacts

- Direct report: `runtime-state/approval-continuation-robustness/phase97-approval-direct.json`
- Live gateway report: `runtime-state/approval-continuation-robustness/phase97-approval-gateway.json`
- Live AnythingLLM report: `runtime-state/approval-continuation-robustness/phase97-approval-anythingllm.json`

## Acceptance Coverage

- Pending L1 packet-design approval can be continued exactly once.
- Continuation uses explicit packet operations and deterministic downstream draft planning.
- Duplicate approval fails closed with `approval_already_consumed`.
- Denied approval fails closed with `approval_denied`.
- Wrong-run approval fails closed with `approval_not_pending`.
- Target mismatch and source-apply scope changes fail closed with `approval_scope_changed`.
- Gateway failure responses are chat-visible and include approval state, type, failure reason, error code, and next action.
- Protected fixture state remains unchanged.

## Current Proof

- Focused regression passed for Phase 97 validator, controller guards, deterministic continuation, and gateway error chat conversion: `7 passed`.
- Direct validator passed: `runtime-state/approval-continuation-robustness/phase97-approval-direct.json`.
- Live Bash gateway validator passed on both frozen Coinbase fixtures with all featured port-health checks: `runtime-state/approval-continuation-robustness/phase97-approval-gateway.json`.
- Live AnythingLLM validator passed on both frozen Coinbase fixtures with all featured port-health checks: `runtime-state/approval-continuation-robustness/phase97-approval-anythingllm.json`.
- Docs index check passed with no orphan docs: `expected_count=113`, `orphaned_docs=[]`.
- Full Bash regression passed: `471 passed, 4 skipped, 23 deselected`.

## Known Limits

- Phase 97 does not apply changes to source repositories.
- Real source apply remains outside scope.
- Disposable-copy apply remains Phase 98.
