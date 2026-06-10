# Output Format Parity

Output format parity proves that the default chat format and JSON output expose the same useful answer, evidence markers, safety boundary, and run traceability for stable Priority 0 prompts.

The active case catalog is `runtime/output_format_parity_cases.json`. It references stable blind-baseline prompt families instead of embedding ad hoc prompts:

- code quality and self-review
- defect diagnosis
- engineering judgment
- delivery and mentorship

Each family covers both frozen Coinbase fixtures:

- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

## When To Use

Run this gate when:

- changing the controller chat renderer
- changing JSON output format behavior
- changing stable Priority 0 prompt contracts
- preparing a founder-testing release gate
- investigating a report that JSON output is artifact-only or less useful than default chat

## Contract

For each governed case, the gate sends the same prompt through:

- workflow-router gateway default output
- workflow-router gateway JSON output
- AnythingLLM default output
- AnythingLLM JSON-requested output

The validator fails if:

- JSON does not parse
- JSON lacks `chat_contract`
- JSON lacks `inline_answer_contract`
- JSON selects the wrong workflow
- JSON omits the expected answer heading, artifact kind, or safety marker
- the JSON inline answer body is not present in the default chat answer body
- either frozen fixture mutates
- AnythingLLM proof is missing

## Validation

Use Bash-side validation for the live stack:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_output_format_parity_live.py \
  --output-path runtime-state/output-format-parity/phase124-output-format-parity-live.json \
  --timeout-seconds 900
```

Expected clean result:

```text
OUTPUT FORMAT PARITY REPORT PASSED
```

The report is written under `runtime-state/output-format-parity/` and is local-only.

## Relationship To Older JSON Checks

`scripts/validate_workflow_router_chat_contract_live.py` proves one code-explanation JSON contract path. This Phase 124 gate is broader: it validates representative stable Priority 0 families and compares JSON inline answer content against the default chat answer content.
