# Semi-Well-Defined Prompt Generalization

This Phase 110 gate tests whether the current local model and harness can answer natural coding prompts that are close to real user wording, not exact governed founder-field prompts.

It is a chat-quality gate. A prompt only passes when the visible chat answer, route decision, selected workflow/skills/tools, semantic markers, score threshold, and fixture mutation proof all pass.

## What It Tests

The governed catalog lives at:

```text
runtime/prompt_catalogs/semi_well_defined_v1.json
```

The catalog contains:

- 24 natural L1/L2 coding prompts
- both frozen Coinbase fixtures
- representative Python service, Node CLI, and Go HTTP fixtures
- prompt variants with omitted `Read only` equivalents, reordered output requests, partial target descriptions, and natural phrasing that does not name internal workflows or skills
- fail-closed boundary cases for approval bypass and raw internal context requests

## Pass Rules

The validator enforces:

- no internal workflow, skill, controller JSON, or exact founder-field prompt copies in user prompts
- route decision matches the expected workflow and route rule
- visible chat output includes FormatA contract markers, expected route rule, expected artifact, and semantic answer markers
- each live result meets the bounded recursive policy case score floor
- suite mean meets the bounded recursive policy stable threshold
- prompt suggestions are recorded for misses but never turn a miss into a pass
- protected fixture watched files and git status remain unchanged during live runs

## Run Offline

Offline validation checks the catalog, deterministic route selection, and boundary cases:

```bash
python scripts/validate_semi_well_defined_prompts.py \
  --output-path runtime-state/semi-well-defined-prompts/offline.json
```

## Run Live

From Bash, with the controller/gateway stack running and AnythingLLM pointed at the workflow-router gateway:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"

python3 scripts/validate_semi_well_defined_prompts.py \
  --live \
  --timeout-seconds 900 \
  --output-path runtime-state/semi-well-defined-prompts/live.json
```

The command writes JSON and Markdown reports. Review the Markdown first for prompt, score, initial difference, and suggestion summaries.

Examples: [docs/examples/semi-well-defined-prompts.md](docs/examples/semi-well-defined-prompts.md).
