# Model Capability Profile

- Candidate: offline-phase71-baseline
- Status: warning
- Source portability report: C:\agentic_agents\runtime-state\model-portability\phase72-offline-baseline.json
- Advisory only: True

## Capabilities

| Capability | Status | Evidence | Limitations |
| --- | --- | --- | --- |
| route_stability | proven | source portability report passed; representative_l1 suite passed; classifier_failure_count=0 |  |
| output_contract_reliability | proven | source portability report passed; output_contract_failure_count=0 |  |
| semantic_answer_quality | proven | founder field prompt suite passed; model_quality_failure_count=0 |  |
| latency | unknown | source acceptance report does not include suite duration metrics | Latency is not approved for routing decisions until measured timing is recorded. |
| timeout_behavior | proven | source portability report passed; timeout_failure_count=0 |  |
| safe_apply_readiness | partially_proven | controlled_apply suite passed | Disposable-copy apply and dry-run packet proof are covered.; Real repository mutation remains approval-gated and is not automatically approved by this profile. |

## Task Policy

| Task | Status | Reason / Required Evidence |
| --- | --- | --- |
| automatic_model_selection | not_approved | Phase 78 profiles are advisory only; no automatic model selection behavior is enabled. |
| read_only_l1 | approved | route_stability; output_contract_reliability; semantic_answer_quality; representative_l1 |
| draft_only_l1 | approved | representative_l1; approval boundary remains controller-owned |
| approval_gated_l1 | conditional | representative_l1; controlled_apply; explicit approval remains required |
| l2_read_only | approved | representative_l2; route_stability; semantic_answer_quality |
| apply_prep | conditional | controlled_apply; explicit approval; disposable-copy or draft packet boundary |
| real_apply | not_approved | Later approved phase must explicitly authorize real repository mutation policy. |
