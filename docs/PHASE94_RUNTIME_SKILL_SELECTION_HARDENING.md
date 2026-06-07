# Phase 94 Runtime Skill Selection Hardening

Phase 94 makes workflow, skill, and tool selection auditable enough for smaller local models and natural clients. The controller still uses deterministic routing and registry metadata as the authority. The local model can provide advisory classification evidence, but it cannot promote a deterministic unsupported request into a supported workflow.

## Contract

Every workflow-router route decision now includes `selection_audit`:

- `selection_policy`: metadata-only selection policy, minimum confidence, fail-closed flag, and manual-injection flag.
- `selected`: selected workflow, confidence, confidence reasons, route rules, evidence sources, and prompt-skill coverage entry IDs.
- `coverage_matches`: matching entries from `runtime/prompt_skill_coverage.json`.
- `workflow_candidates`: selected and rejected workflow candidates with counts.
- `skill_candidates`: selected and rejected skill candidates with counts and `body_reads_during_selection`.
- `tool_candidates`: selected and rejected tool candidates with counts.

Default `format_a` chat output includes a `Skill Selection:` block with confidence, coverage entries, selected skills/tools, rejected candidate counts, and grounding markers. JSON output exposes the same data through `selection_explanation`.

## Case Catalog

The governed Phase 94 case list lives at `runtime/skill_selection_hardening_cases.json`.

It covers:

- ready L1 related-test selection
- ready L1 callers/usages selection
- ready L2 runtime-error diagnosis selection
- fail-closed ambiguous prompt
- fail-closed unsupported non-development prompt
- fail-closed conflicting read-only plus immediate mutation prompt

Each ready case asserts selected workflow, route rules, expected skills, expected tools, rejected candidates, coverage entry IDs, and stable repeated signatures. Each fail-closed case asserts no selected workflow, low confidence, no selected skills/tools, blocker reason, and no request preview.

## Validation

Offline direct validation:

```bash
python scripts/validate_skill_selection_hardening.py \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Live Bash validation through the workflow-router gateway, local model, controller, and AnythingLLM:

```bash
python scripts/validate_skill_selection_hardening.py \
  --live-gateway \
  --live-anythingllm \
  --model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

The live validator runs repeated gateway checks and one AnythingLLM pass per case by default. It records run IDs, route signatures, chat marker proof, controller run lookup proof, and protected fixture state checks.

Focused regression:

```bash
python -m pytest tests/regression/test_skill_selection_hardening.py -q
python -m pytest tests/regression/test_chat_response_contract.py -q
python -m pytest tests/regression/test_controller_service.py::test_workflow_router_selection_audit_is_stable_across_repeated_runs -q
```

Full regression gate for non-agent code changes:

```bash
python -m pytest tests/regression/ -v
```

For runtime-facing changes, prefer running the full regression and live validator from Bash because Windows clients have previously timed out waiting for body bytes from Bash-hosted localhost services.
