# Context Retrieval Upgrade

The context retrieval upgrade is the workflow-router contract for deciding which context source families a request needs before a downstream workflow gathers file content.

It is not a new parallel implementation path. The router records source-family intent, then the existing `code_investigation.plan`, `code_context.lookup`, and `execution_planning.plan` workflows perform bounded read-only work through the same approved tools.

## When To Use It

Use this when validating natural workflow-router prompts through AnythingLLM or the workflow-router gateway. The user should not need to name tools like `git_grep`, `structure_index`, or `codegraph_context`; the router selects source families from the request.

The supported source families are:

- `ast_index`: bounded structure and symbol discovery
- `text_search`: exact-string search plus selected file reads
- `config_lookup`: configuration and environment-variable lookup
- `test_lookup`: related test and verification-command discovery
- `curated_relationship_lookup`: callers, callees, imports, and dependency relationships

## Output Contract

Every workflow-router decision now includes:

- `route_decision.context_source_audit`
- a standalone `context_source_audit` artifact
- `selected_context_sources` in the route decision and summary
- `controller_request_preview.context_sources` for ready routes
- a chat-visible `Context Sources:` block in default `format_a`
- `context_explanation` in JSON output through the chat contract

The audit records selected and rejected source families, reasons, mapped tool IDs, expected artifact keys, fixed budgets, bounded layout scan results, evidence file samples, and gaps.

Unsupported layouts fail closed with `unsupported_repository_layout` and a next action instead of falling back to broad scanning.

## Validation

Direct and live validation use the governed case catalog:

```text
runtime/context_retrieval_upgrade_cases.json
```

Run direct validation:

```bash
python3 scripts/validate_context_retrieval_upgrade.py
```

Run Bash live validation through the workflow-router gateway and all featured ports:

```bash
python3 scripts/validate_context_retrieval_upgrade.py \
  --live-gateway \
  --port-health \
  --output-path runtime-state/context-retrieval-upgrade/phase95-context-retrieval-gateway.json
```

Run AnythingLLM validation after setting the API key:

```bash
python3 scripts/validate_context_retrieval_upgrade.py \
  --skip-direct \
  --live-anythingllm \
  --output-path runtime-state/context-retrieval-upgrade/phase95-context-retrieval-anythingllm.json
```

The live validator covers both protected frozen Coinbase fixtures and a generated non-Coinbase fixture under `runtime-state/context-retrieval-upgrade/fixtures/`.

## Safety Constraints

- Source-family selection is deterministic and metadata-only.
- The router records intent; downstream workflows do the bounded reads.
- Protected frozen fixture files are hash-checked during live gateway and AnythingLLM validation.
- The generated non-Coinbase fixture is disposable validation data under project runtime state.
- Unsupported repository layouts are blocked before downstream read-only execution.
