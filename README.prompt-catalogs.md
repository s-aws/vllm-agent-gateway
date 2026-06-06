# Prompt Catalogs

Prompt catalogs are governed fixtures for natural-language field tests and prompt-matrix validation.

They keep prompt cases out of validator script literals so a tester or future agent can review case IDs, tags, expected workflow, expected router rule, semantic markers, refined prompts, and change history in one place.

## Current Catalog

The current V1 founder field catalog is:

```text
runtime/prompt_catalogs/founder_field_v1.json
```

It contains:

- `P01` through `P34` founder field prompts
- classifier expectations for each case
- chat-visible output markers
- semantic answer markers
- forbidden mutation markers
- refined prompts for ambiguity-risk cases
- tags for fixture type, level, skill, and safety boundary
- catalog-level and case-level change history

## Validation

Run the catalog validator before live field testing:

```bash
python scripts/validate_prompt_catalog.py
```

Expected final marker:

```text
PROMPT CATALOG PASS
```

Run the classifier matrix after catalog or router wording changes:

```bash
python scripts/validate_founder_field_prompt_matrix.py
```

Expected final marker:

```text
PROMPT MATRIX PASS
```

## Governance Rules

- Add or change prompt cases in the catalog fixture, not in field-test scripts.
- Every case must have a stable case ID, tags, expected workflow, expected router rule, markers, and change history.
- Refined prompts must include a prompt-risk explanation.
- Prompt changes that affect routing must pass the prompt matrix before live AnythingLLM tests.
- Prompt changes that affect field-test acceptance must pass the V1 release-candidate gate before being treated as product-ready.

## Consumers

- `scripts/run_founder_field_prompt_eval.py` loads the catalog for live AnythingLLM field tests.
- `scripts/validate_founder_field_prompt_matrix.py` loads the catalog for offline route/rule checks.
- `scripts/validate_prompt_catalog.py` validates catalog structure and writes a report under `runtime-state/prompt-catalogs/`.
