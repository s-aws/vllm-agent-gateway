# Chat-Visible Output Usefulness Refresh

Phase 202 closes the M2 chat-visible answer-contract milestone with live proof.

It consumes the Phase 201 deterministic contract-enforcement report, a live output-format parity run through the workflow-router gateway and AnythingLLM, and the governed AnythingLLM answer-usefulness report.

## What It Proves

- Default `format_a` and requested `json` outputs preserve equivalent answer content.
- Gateway and AnythingLLM both pass the same output-format parity cases.
- Both frozen Coinbase fixtures are covered.
- Useful answer content appears in chat before artifact links.
- Source mutation and fixture mutation proof remain clean.
- Featured port-health proof is present, every probe passes, and the full expected label/URL set is present.
- Answer-usefulness proof was generated with artifact verification and every entry's checked cases match its expected cases.
- Phase 203 can start only after M2 reports `m2_ready=true`.

## Required Live Commands

Run the live parity refresh:

```bash
python3 scripts/validate_output_format_parity_live.py \
  --output-path runtime-state/phase202/phase202-output-format-parity-live.json \
  --timeout-seconds 900
```

Run the answer-usefulness report:

```bash
python3 scripts/validate_anythingllm_answer_usefulness.py \
  --require-artifacts \
  --output-path runtime-state/phase202/phase202-answer-usefulness-report.json
```

Then run the Phase 202 closeout:

```bash
python3 scripts/validate_chat_visible_output_usefulness_refresh.py
```

Expected passing marker:

```text
PHASE202 CHAT VISIBLE OUTPUT USEFULNESS REFRESH PASS
```

## Boundary

This phase validates live output and usefulness. It does not change routing, skill selection, or evidence ranking. Those move into M3 and M4.
