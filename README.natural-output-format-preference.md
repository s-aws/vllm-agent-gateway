# Natural Output Format Preference

Natural output format preference proves that users can request the default human-readable chat format or JSON through normal language, without manually injecting controller fields.

The active case catalog is `runtime/natural_output_format_preference_cases.json`. It references the governed output-format parity corpus instead of duplicating prompts.

The currently governed formats are only `format_a` and `json`. New formats must be added to the controller enum and this same response pipeline before documentation or tests can claim support.

## When To Use

Run this gate when:

- changing output-format selection
- changing workflow-router chat rendering
- changing AnythingLLM routing through the gateway
- validating a founder report that JSON requests are ignored or default chat became machine-readable

## Contract

For each governed case, the live gate proves:

- default gateway chat returns FormatA
- natural gateway text such as `plain English` returns FormatA
- natural gateway text such as `Return JSON.` returns strict JSON without explicit `output_format` or `response_format` fields
- explicit gateway `output_format=json` still returns strict JSON
- OpenAI-compatible `response_format={"type":"json_object"}` still returns strict JSON
- default AnythingLLM chat returns FormatA
- natural AnythingLLM text such as `plain English` returns FormatA
- natural AnythingLLM text such as `Return JSON.` returns strict JSON
- JSON preserves the same inline answer contract, evidence markers, safety boundary, and run traceability as default chat
- JSON preserves `summary.answer` parity through `chat_contract.answer` and `primary_answer_contract` when the default FormatA response starts with a primary `Answer:` section
- neither frozen Coinbase fixture mutates

## Validation

Use Bash-side validation for the live stack:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_natural_output_format_preference_live.py \
  --output-path runtime-state/natural-output-format-preference/phase144-natural-output-format-preference-live.json \
  --timeout-seconds 900
```

Expected clean result:

```text
NATURAL OUTPUT FORMAT REPORT PASSED
```

The report is written under `runtime-state/natural-output-format-preference/` and is local-only.

## Relationship To Output Format Parity

Output format parity proves that FormatA and JSON preserve the same answer body. This gate proves the selector itself works from natural user text through both gateway and AnythingLLM, while keeping explicit API selectors as holdouts.
