# Large-Context 384k Usability Acceptance Contract

This gate defines what must be true before the project can claim a usable 384k-token project product.

The contract does not prove live runtime behavior by itself. It fixes the acceptance target that later phases must execute:

- answer-first chat output through the workflow-router gateway and AnythingLLM
- blind-baseline-first scoring with holdout reruns
- retrieval, artifact paging, summarization, refusal, and chunked-investigation coverage
- fixture/index readiness before live acceptance
- stale-index rejection before live acceptance
- metadata-only source retention and no rejected-content storage
- no raw 384k prompt stuffing claim
- no 1M+ expansion work in the current product target

## Command

```bash
python3 scripts/validate_large_context_384k_usability_acceptance_contract.py
```

## Pass Marker

```text
PHASE258 LARGE CONTEXT 384K USABILITY ACCEPTANCE CONTRACT PASS
```

## Phase Order

The accepted path is contract first, then fixture/index readiness, then stale-index rejection before live acceptance. Founder docs, clean-clone replay, release decision, and stable handoff happen only after the live gate has useful chat-visible evidence.

This ordering is intentional: a live smoke can look successful while still relying on stale or unsafe derived index state.
