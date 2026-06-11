# Multi-Fixture Prompt Parity

Phase 187 proves that supported prompt families behave consistently across the protected Coinbase fixtures and non-Coinbase generalization fixtures.

Use this when a workflow, skill, router rule, output contract, or evidence formatter changes in a way that could work on the Coinbase repo but fail elsewhere.

## What It Checks

The live parity matrix runs representative prompts through the workflow-router gateway, and optionally through AnythingLLM, for these fixture groups:

- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- Python service generalization fixture
- Node CLI generalization fixture
- Go HTTP service generalization fixture

The current matrix covers:

- code explanation
- schema lookup
- request/data flow mapping
- change-surface identification
- configuration lookup
- table read/write lookup

Each result records routing, selected workflow, selected skills/tools, expected artifact, route hint, task class, layout status, source refs, fixture mutation proof, and repository-layout limitations.

## Parity Decisions

The parity matrix separates failures into two classes:

- `fixture_specific_deltas`: one fixture or client failed while the same prompt family passed elsewhere. Treat this as fixture coverage, repo-layout, or evidence-retrieval drift.
- `shared_workflow_deltas`: every case in the prompt family failed. Treat this as a shared router, workflow, skill, or output-contract failure.

Do not promote a prompt-family repair unless the affected target case and holdouts pass.

## Commands

Gateway-only validation:

```bash
python3 scripts/validate_multi_repo_fixtures_live.py \
  --port-health \
  --timeout-seconds 900 \
  --output-path runtime-state/multi-fixture-prompt-parity/phase187-gateway-report.json
```

Gateway plus AnythingLLM validation from Windows PowerShell:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_multi_repo_fixtures_live.py `
  --port-health `
  --live-anythingllm `
  --timeout-seconds 900 `
  --output-path runtime-state/multi-fixture-prompt-parity/phase187-anythingllm-report.json
```

The AnythingLLM command expects AnythingLLM to target the workflow-router gateway at `http://127.0.0.1:8500/v1`.

## Acceptance

Phase 187 is accepted when:

- the report status is `passed`
- `summary.client_case_count` is `30` for the AnythingLLM run
- `summary.prompt_family_count` is `6`
- `parity_matrix.status` is `passed`
- fixture mutation checks remain clean
- unresolved deltas are converted into roadmap proposals instead of ignored

## Limitations

This matrix proves routing and answer-contract parity for selected representative prompts. It does not prove full language-specific AST support for Go or JavaScript. The report explicitly records current layout limitations for those fixtures.
