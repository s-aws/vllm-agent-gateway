# Prompt Family Drift Detection

Phase 191 adds a governed drift gate for Priority 0 chat quality. It checks whether founder-style natural-language prompts still map to the intended prompt families, workflows, skills, tools, corpus roles, and verification gates.

Use this gate before adding new prompt families, expanding founder field tests, or starting expensive live AnythingLLM runs. It separates prompt wording drift from missing capability so the next action is explicit: prompt governance update, workflow repair, new skill/tool proposal, unsupported-scope backlog, or no repair.

## What It Checks

- `runtime/prompt_catalogs/founder_field_v1.json`
- `runtime/prompt_skill_coverage.json`
- `runtime/prompt_corpus_governance_v2.json`
- `runtime/holdout_prompt_bank.json`
- `runtime/founder_test_prompt_pack.json`
- governed Phase 191 drift probes in `runtime/prompt_family_drift_detection_policy.json`

Each catalog prompt and drift probe is classified as:

- `in_coverage`: maps to implemented prompt-family coverage.
- `holdout`: maps to implemented coverage and is reserved as independent proof for at least one governed prompt family. Some prompts can also be targets for a different family; the report shows `target_for_families`, `holdout_for_families`, and `holdout_independence_status` so this is auditable.
- `partial_drift`: related to the product goal but missing a required layer.
- `out_of_coverage`: outside the current coding-agent release scope.

## Run

```bash
python3 scripts/validate_prompt_family_drift_detection.py
```

The command writes:

- `runtime-state/phase191/phase191-prompt-family-drift-detection-report.json`
- `runtime-state/phase191/phase191-prompt-family-drift-detection-report.md`

## Passing Standard

The report must have:

- `status=passed`
- zero active catalog `partial_drift` or `out_of_coverage` cases
- separate catalog and drift-probe decision counts so synthetic probe drift is not confused with live catalog drift
- every drift probe classified with an explicit next action
- every holdout record includes family-level target/holdout relationship evidence
- source artifact hashes for every governed input
- report rebuild validation with no hidden edits

This gate does not call the local model. It protects the prompt-family catalog and coverage map before live local-model validation.
