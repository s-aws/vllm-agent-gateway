# Founder Field Tests

This field test checks whether the V1 harness behaves like a usable product from AnythingLLM, not just from direct controller calls.

It runs natural-language prompts through the AnythingLLM workspace API, with AnythingLLM pointed at the workflow-router gateway `http://127.0.0.1:8500/v1`. Each prompt has a baseline target, expected workflow, required chat-visible markers, semantic answer markers, forbidden mutation markers, and a refined prompt when the original wording has ambiguity risk.

## What This Proves

- natural prompts do not require manual skill injection
- AnythingLLM can reach the local model through the workflow-router gateway
- the controller selects the expected workflow
- chat responses include immediately reviewable FormatA content
- protected frozen fixtures are not mutated
- misses are recorded with a concrete prompt suggestion
- semantic answer quality is checked separately from generic FormatA markers
- refined prompts are preserved for tester-facing prompt improvement

## Prompt Set

The current suite contains 34 prompts:

- `P01` through `P21`: read-only L1/L2 code investigation and code context prompts
- `P22`: task decomposition
- `P23` through `P25`: draft-only implementation-prep prompts
- `P26`: disposable-copy apply proof
- `P27` through `P34`: Batch D skill prompts for handler branch tracing, table-schema-only lookup, runtime-entrypoint disambiguation, and change-boundary summary on both frozen fixtures

The governed prompt definitions, expected router rules, tags, semantic markers, forbidden markers, refined prompts, and change history live in [runtime/prompt_catalogs/founder_field_v1.json](runtime/prompt_catalogs/founder_field_v1.json). The runner script [scripts/run_founder_field_prompt_eval.py](scripts/run_founder_field_prompt_eval.py) loads that catalog instead of owning separate prompt literals.

The current V1 acceptance gate also runs this suite through `scripts/validate_v1_acceptance.py`.

## Run

From Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/run_founder_field_prompt_eval.py \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --timeout-seconds 900
```

Expected final marker:

```text
FOUNDER FIELD PASS
```

Reports are written under:

```text
runtime-state/founder-field-tests/
```

Each run writes both JSON and Markdown:

- JSON: complete machine-readable result, prompt, expected workflow, output-contract status, semantic-quality status, missing markers, forbidden markers, text hash, run ID, refined prompt, prompt risk, and fixture state
- Markdown: founder-review table with initial differences, semantic status, miss suggestions, and refined prompts

When launching Bash from PowerShell, WSL may not inherit `ANYTHINGLLM_API_KEY` unless `WSLENV` is set:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
bash -lc 'cd /mnt/c/agentic_agents && python3 scripts/run_founder_field_prompt_eval.py --timeout-seconds 900'
```

## Offline Matrix

Validate the catalog shape before a live field test:

```bash
python scripts/validate_prompt_catalog.py
```

Expected final marker:

```text
PROMPT CATALOG PASS
```

Run this before a live field test when classifier wording has changed:

```bash
python scripts/validate_founder_field_prompt_matrix.py
```

Expected final marker:

```text
PROMPT MATRIX PASS
```

The matrix validates the original prompt catalog plus refined prompt variants. It checks expected workflow and primary deterministic router rule so phrase-priority conflicts are caught before live AnythingLLM runs.

## Interpreting Misses

A failed prompt does not automatically mean the local model is bad. Categorize the miss first:

- **Routing miss:** wrong selected workflow
- **Output miss:** right workflow but missing chat-visible answer fields
- **Semantic miss:** right workflow and FormatA shape, but missing required answer concepts or containing forbidden mutation concepts
- **Evidence miss:** answer lacks expected files, tests, commands, or source refs
- **Prompt ambiguity:** prompt wording permits more than one reasonable interpretation
- **Apply-boundary miss:** mutation proof or approval language is unclear

Fix routing, output, and semantic misses in the harness when the prompt target is clear. For prompt ambiguity, keep the original prompt result documented and add the refined prompt suggestion to the report instead of hiding the ambiguity.

## Baseline Source

The first baseline pass was evaluated by a contextless subagent against the prompt list. It identified likely miss risks and prompt-tightening suggestions before the prompts were run through AnythingLLM.

The Phase 56 review report is [docs/V1_FOUNDER_FIELD_TEST_RESULTS.md](docs/V1_FOUNDER_FIELD_TEST_RESULTS.md).
