# Current-Model Compatibility Examples

## Run Current Matrix

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_current_model_compatibility_matrix.py \
  --require-artifacts \
  --output-path runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.json \
  --markdown-output-path runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.md
```

Expected result:

```text
CURRENT MODEL COMPATIBILITY PASS
```

## Review JSON

Start with:

```text
summary.model_profile_status
summary.supported_prompt_family_count
summary.anythingllm_compatibility_status
summary.known_failure_mode_count
matrix.prompt_families[]
matrix.output_formats[]
matrix.skill_tool_support
matrix.known_failure_modes[]
matrix.known_boundaries[]
blockers[]
```

Current expected state:

```text
model_profile_status=warning
supported_prompt_family_count=33
anythingllm_compatibility_status=supported
known_failure_mode_count=14
blockers=[]
```

The `warning` profile status is expected because latency is still monitored. It is not a chat-quality blocker by itself.

## Review Markdown

Open:

```text
runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.md
```

Use the Markdown for quick review. Use the JSON for exact source refs and full prompt-family rows.

## Failure Review

If the gate fails, inspect:

```text
blockers[].code
blockers[].source_id
blockers[].message
errors[]
```

Do not fix a failed matrix by editing the matrix output. Rerun or repair the source gate that owns the blocker.
