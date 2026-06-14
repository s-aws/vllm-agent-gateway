# Retrieval-Backed Chat Answer Gate

Phase 218 connects the Phase 217 metadata-first context index to the existing workflow-router chat path.

The goal is chat-visible large-corpus answers without raw prompt stuffing. The router still uses the normal `workflow_router.plan` path; it does not add a second large-context chat endpoint.

## What It Does

- Detects approved large-corpus read-only prompts.
- Uses the Phase 217 metadata-first index to select bounded evidence refs.
- Rechecks current source hash, mtime, size, ignore policy, safety policy, and context strategy before evidence reaches chat.
- Returns an answer-first `summary.answer` so AnythingLLM users see useful information immediately.
- Cites source paths, line spans, source hashes, chunk hashes, freshness, confidence, and limitations.
- Fails closed for private, ignored, credential, token, secret-like, stale, unavailable, or unapproved evidence.

## What It Does Not Do

- It does not claim raw 1M-token prompt support.
- It does not store source text in the durable index.
- It does not add artifact paging; that is Phase 219.
- It does not replace the future context strategy router; that is Phase 220.
- It does not mutate protected fixtures.

## Validation

Run the deterministic gate:

```bash
python3 scripts/validate_retrieval_backed_chat_answer_gate.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_retrieval_backed_chat_answer_gate.py -q
```

Runtime closeout still requires live proof through localhost model `8000`, the controller/gateway ports, the workflow-router gateway, and AnythingLLM when available.

Current Phase 218 closeout proof passed the deterministic validator, focused regression, docs index validation, Bash port probes for `8000`, `8300`, `8400`, `8500`, and `8205`, direct controller proof through `8400`, workflow-router gateway proof through `8500`, and AnythingLLM workspace proof through `my-workspace`.

## Artifacts

- Policy: `runtime/retrieval_backed_chat_answer_gate_policy.json`
- Validator: `scripts/validate_retrieval_backed_chat_answer_gate.py`
- Report: `runtime-state/phase218/phase218-retrieval-backed-chat-answer-gate-report.json`
- Markdown report: `runtime-state/phase218/phase218-retrieval-backed-chat-answer-gate-report.md`
- Controller module: `vllm_agent_gateway/controllers/large_context/retrieval_answer.py`

Examples: [docs/examples/retrieval-backed-chat-answer-gate.md](docs/examples/retrieval-backed-chat-answer-gate.md)
