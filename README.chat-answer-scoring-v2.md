# Chat Answer Scoring V2

Phase 192 consolidates chat-answer quality scoring into one governed report. It compares blind-baseline delta evidence against local chat answers and produces repeatable scores, classifications, gap categories, and repair-target guidance.

This gate does not replace live gateway or AnythingLLM proof. It makes the existing proof easier to interpret before the next repair or release decision.

## What It Scores

The scorer reads:

- `runtime-state/phase178/phase178-blind-baseline-delta-report.json`
- `runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json`
- `runtime-state/phase191/phase191-prompt-family-drift-detection-report.json`
- `runtime/chat_answer_scoring_v2_policy.json`

Each case is scored across:

- routing
- evidence relevance
- correctness
- answer completeness
- source references
- format adherence
- safety boundaries
- user-visible usefulness

## Run

```bash
python3 scripts/validate_chat_answer_scoring_v2.py
```

The command writes:

- `runtime-state/phase192/phase192-chat-answer-scoring-v2-report.json`
- `runtime-state/phase192/phase192-chat-answer-scoring-v2-report.md`

## Current Interpretation

The current Phase 192 report passes with no failed cases. The current scored cases are advisory because the Phase 178 evidence already marked evidence detail and prompt wording as advisory. That is not a release blocker by itself, but it tells the next agent where targeted answer-quality repair should focus if the same issue repeats in holdouts or founder feedback.

## Passing Standard

The report must have:

- `status=passed`
- no failed stable delta cases
- blind baseline collected before local output
- no active catalog-blocking prompt drift from Phase 191
- known pass, advisory, and fail examples classified correctly
- source answer artifacts present and hash-verified
- report rebuild validation with no hidden edits
