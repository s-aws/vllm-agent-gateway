---
name: data-model-schema-locator
description: Locate data models, database table schemas, dataclasses, fields, or columns from bounded source evidence. Use for read-only prompts asking where a model/schema lives or what fields it exposes.
---

# Data Model Schema Locator

Use after `code_investigation.plan` has evidence for a requested table, dataclass, schema, model, field, or column.

## Workflow

1. Identify the requested model, table, dataclass, field, or column.
2. Prefer canonical source schema files over generated docs.
3. Extract fields only from explicit schema or model definitions.
4. Return source files and line refs.
5. Mark partial evidence when a model file is found but fields cannot be extracted.

## Output

Return:

- target model/schema
- model files
- fields or columns
- source refs
- gaps

Do not infer fields from runtime payloads unless the artifact labels them as examples.
