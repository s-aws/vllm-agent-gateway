# Chunked Investigation Executor Contract

Phase 222 defines the contract for a future `large_context.chunked_investigation` executor.

The current router can select `chunked_investigation` for multi-step large-corpus prompts, but before Phase 222 that strategy was intentionally blocked because no executor contract existed. This phase defines the behavior, artifacts, source proof, safety boundaries, and live validation gates needed before implementation.

## What It Defines

- The executor stays inside the existing workflow-router read-only large-context path.
- It reuses the metadata-first index, retrieval evidence validation, and artifact paging contracts.
- It decomposes a multi-step corpus question into bounded evidence stages.
- It requires source refs, hashes, freshness, stage records, claim mapping, unresolved steps, and answer-first chat.
- It forbids raw prompt stuffing, a new chat endpoint, vector-search replacement, protected fixture mutation, and artifact-only answers.

## Contract Artifacts

The future executor must produce a canonical `chunked_investigation_report` plus structured plan, stage, evidence, page, and final-answer records. Each material final-answer claim must trace through a claim map to source evidence.

## Validation

```bash
python3 scripts/validate_chunked_investigation_executor_contract.py
python3 -m pytest tests/regression/test_chunked_investigation_executor_contract.py -q
```

## Artifacts

- Policy: `runtime/chunked_investigation_executor_contract_policy.json`
- Validator: `scripts/validate_chunked_investigation_executor_contract.py`
- Report: `runtime-state/phase222/phase222-chunked-investigation-executor-contract-report.json`
- Markdown report: `runtime-state/phase222/phase222-chunked-investigation-executor-contract-report.md`

Examples: [docs/examples/chunked-investigation-executor-contract.md](docs/examples/chunked-investigation-executor-contract.md)
