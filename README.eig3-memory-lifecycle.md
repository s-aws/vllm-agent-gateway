# EIG-3 Memory Lifecycle

Status: Phase 300.

This feature validates governed memory lifecycle behavior before persistent memory can influence chat, retrieval, or connector decisions.

It does not add a production memory store. It uses synthetic records to prove the lifecycle policy for:

- scope,
- purpose,
- source provenance,
- retention and expiration,
- deletion,
- inspection,
- hidden-memory rejection,
- stale-source rejection,
- wrong-actor and wrong-session isolation,
- raw sensitive memory rejection.

## Files

- `runtime/eig3_memory_lifecycle_fixtures.json`: synthetic lifecycle fixture pack.
- `vllm_agent_gateway/acceptance/eig3_memory_lifecycle.py`: validator.
- `scripts/validate_eig3_memory_lifecycle.py`: CLI wrapper.

## Validation

```bash
python scripts/validate_eig3_memory_lifecycle.py \
  --output-path runtime-state/eig3-memory-lifecycle/phase300-validation.json
```

Expected result:

- `status=passed`
- `record_count=8`
- `allowed_record_count=1`
- `denied_record_count=7`
- `phase301_ready=true`
- no raw memory content retained in the report

## Safety Boundary

Reports store record IDs, decisions, reasons, content hashes, and lifecycle metadata. They do not store raw memory content.

Runtime memory influence is not enabled by this phase.
