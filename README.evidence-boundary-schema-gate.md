# Evidence Boundary Schema Gate

Phase 189 prevents malformed evidence artifacts from rendering as successful chat answers.

Use this when changing code-investigation artifacts, inline answer rendering, schema lookup, change-surface summaries, or any validator that accepts chat-visible evidence.

## What It Guards

The first governed surfaces are:

- `data_model_lookup`
- `change_surface_summary`

These were selected because previous Priority 0 work exposed two high-risk failure modes:

- persisted schema evidence mixed with runtime dictionary/cache fields
- change-boundary answers implying implementation readiness or placing the same file in conflicting touch/no-touch buckets

## Behavior

The gate runs in the shared inline-artifact answer path used by FormatA and JSON.

If a governed artifact is valid, chat output renders normally and JSON includes:

```json
{
  "inline_answer_contract": {
    "evidence_boundary_status": "passed",
    "evidence_boundary_errors": []
  }
}
```

If a governed artifact is malformed, the chat answer does not render the normal artifact answer. Instead, it renders:

```text
Evidence Boundary Gate:
- Evidence boundary status: failed
- Artifact: change_surface_summary
- Blocking issues: ...
- Next action: repair the controller artifact evidence boundary before accepting this chat answer
```

## Schema Expectations

`data_model_lookup` must keep persisted schema evidence separate:

- `fields` is a list of field objects
- ready artifacts have at least one field, model file, and source ref
- field `source` must be persisted schema evidence, or the field must explicitly label its scope
- runtime dictionary/cache evidence cannot silently appear as a persisted schema field
- `mutation_policy` is `read_only_no_source_mutation`

`change_surface_summary` must keep change boundaries explicit:

- `files_to_touch`, `files_not_to_touch`, `unknowns`, `risks`, `gaps`, `verification_commands`, and `source_refs` are typed lists
- ready artifacts include a touch boundary or explicit touch unknown
- ready artifacts include a no-touch boundary or explicit no-touch unknown
- paths cannot appear in both `files_to_touch` and `files_not_to_touch`
- `implementation_status` keeps implementation behind approval
- `mutation_policy` is `read_only_no_source_mutation`

## Validation

Run focused regression:

```bash
python3 -m pytest tests/regression/test_chat_response_contract.py tests/regression/test_fixture_manager.py -q
```

Run live schema and change-surface parity through gateway and AnythingLLM:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
if (-not $key) { throw 'ANYTHINGLLM_API_KEY is not set in Windows environment' }
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_multi_repo_fixtures_live.py `
  --port-health `
  --live-anythingllm `
  --case-id coinbase-schema-lookup `
  --case-id coinbase-git-schema-lookup `
  --case-id python-service-schema-lookup `
  --case-id coinbase-change-surface `
  --case-id coinbase-git-change-surface `
  --case-id python-service-change-surface `
  --timeout-seconds 900 `
  --output-path runtime-state/evidence-boundary-schema-gate/phase189-live-report.json
```

The live runner fails schema and change-surface cases if `inline_answer_contract.evidence_boundary_status` is not `passed`.
