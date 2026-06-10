# AnythingLLM Answer Usefulness

This is the Priority 0 gate that proves governed AnythingLLM responses are useful directly in chat.

The gate checks the stable baseline corpus at `runtime/baseline_corpus.json` against `runtime/anythingllm_answer_usefulness_contract.json`. It fails if an AnythingLLM response is only artifact links, hides the answer after artifacts, omits the run/source-safety markers, is truncated, or lacks enough family-specific answer detail for immediate review.

Phase 168 also makes `summary.answer` a primary answer contract. When a workflow response carries `summary.answer`, default FormatA starts with `Answer:` before router status metadata, and JSON exposes the same text through both `chat_contract.answer` and `primary_answer_contract`.

## When To Use

Run this gate when:

- closing a Priority 0 chat-quality phase
- changing default chat formatting
- changing AnythingLLM API or UI routing
- changing `summary.answer`, `chat_contract.answer`, or primary answer rendering
- rerunning stable prompt-family evaluations
- preparing founder or external tester proof

## Validation

Use local runtime proof when available:

```bash
python scripts/validate_anythingllm_answer_usefulness.py --require-artifacts --output-path runtime-state/anythingllm-answer-usefulness/anythingllm-answer-usefulness-report.json
```

For a clean clone without local `runtime-state/`, omit `--require-artifacts`. That still validates the committed contract shape and its alignment to the stable baseline corpus, but it cannot prove live captured response text.

```bash
python scripts/validate_anythingllm_answer_usefulness.py
```

## Current Scope

The gate covers stable Priority 0 entries:

- `P0-BB-001`: code quality and self-review
- `P0-BB-002`: testing and defect diagnosis
- `P0-BB-003`: tradeoffs, debt, and engineering judgment
- `P0-BB-004`: delivery and mentorship

Future prompt families must be added to the baseline corpus and this contract before they can be called stable.
