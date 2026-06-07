# Semi-Well-Defined Prompt Examples

Run the offline Phase 110 catalog and route gate:

```bash
python scripts/validate_semi_well_defined_prompts.py \
  --output-path runtime-state/semi-well-defined-prompts/manual-offline.json
```

Run one focused case through the gateway only:

```bash
python scripts/validate_semi_well_defined_prompts.py \
  --live \
  --client gateway \
  --case-id P01 \
  --output-path runtime-state/semi-well-defined-prompts/manual-p01-gateway.json
```

Run one focused case through AnythingLLM:

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"

python3 scripts/validate_semi_well_defined_prompts.py \
  --live \
  --client anythingllm \
  --case-id P02 \
  --output-path runtime-state/semi-well-defined-prompts/manual-p02-anythingllm.json
```

Run the full live suite from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"

python3 scripts/validate_semi_well_defined_prompts.py \
  --live \
  --timeout-seconds 900 \
  --output-path runtime-state/semi-well-defined-prompts/manual-live.json
```

Review the Markdown report next to the JSON report. A passing run must show:

- `route_failed=0`
- `boundary_failed=0`
- `live_failed=0`
- mean score at or above the bounded recursive stable threshold
- no protected fixture state changes

Prompt suggestions in the report are only miss guidance. They are not accepted as proof unless a later live run passes.
