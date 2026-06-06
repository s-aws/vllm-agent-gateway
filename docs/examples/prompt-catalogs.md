# Prompt Catalog Examples

## Validate The Founder Field Catalog

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_prompt_catalog.py \
  --output-path runtime-state/prompt-catalogs/manual-founder-field-v1.json
```

Expected final marker:

```text
PROMPT CATALOG PASS
```

## Validate Prompt Routing Matrix

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_founder_field_prompt_matrix.py \
  --output-path runtime-state/founder-field-tests/manual-prompt-matrix.json
```

Expected final marker:

```text
PROMPT MATRIX PASS
```

## Inspect Catalog Cases

```bash
python3 scripts/validate_founder_field_prompt_matrix.py --list-cases
```

The output includes each original prompt and each refined variant with expected workflow, expected router rule, source case ID, and variant kind.

## Add A Prompt Case

1. Add the case to `runtime/prompt_catalogs/founder_field_v1.json`.
2. Include `case_id`, `tags`, `prompt`, `target_root`, `expected_workflow`, `expected_rule`, markers, and `change_history`.
3. Add `refined_prompt` and `prompt_risk` together when the original wording has known ambiguity.
4. Run `scripts/validate_prompt_catalog.py`.
5. Run `scripts/validate_founder_field_prompt_matrix.py`.
6. Run the relevant live field or V1 release-candidate gate before treating the case as product-ready.
