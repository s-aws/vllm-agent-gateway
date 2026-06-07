# Phase 95 Context Retrieval Upgrade

Phase 95 makes context-source selection a workflow-router artifact instead of an implied downstream behavior.

## Implemented

- Added deterministic source-family selection for `ast_index`, `text_search`, `config_lookup`, `test_lookup`, and `curated_relationship_lookup`.
- Added `context_source_audit` to route decisions and as a standalone artifact.
- Added `selected_context_sources`, layout status, and gap count to workflow-router summaries.
- Added `Context Sources:` to default chat output and `context_explanation` to JSON/chat contract output.
- Added unsupported layout blocking through `unsupported_repository_layout`.
- Added `runtime/context_retrieval_upgrade_cases.json`.
- Added `scripts/validate_context_retrieval_upgrade.py`.

## Proof Artifacts

- Live gateway and port-health report: `runtime-state/context-retrieval-upgrade/phase95-context-retrieval-gateway.json`
- Live AnythingLLM report: `runtime-state/context-retrieval-upgrade/phase95-context-retrieval-anythingllm.json`
- Bash full regression: `python3 -m pytest tests/regression/ -v` returned `460 passed, 4 skipped, 23 deselected`

## Acceptance Coverage

- Representative prompts select source families without tool naming.
- Context artifacts include source, budget, evidence files, and gaps.
- Both frozen Coinbase fixtures are checked for protected hash/git stability.
- A generated non-Coinbase fixture validates that source-family routing is not Coinbase-specific.
- Unsupported empty layouts fail closed before downstream execution.
