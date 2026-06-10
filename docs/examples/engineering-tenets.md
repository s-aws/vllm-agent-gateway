# Engineering Tenet Coverage Examples

## Validate The Current Matrix

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_engineering_tenet_coverage.py \
  --output-path runtime-state/engineering-tenet-coverage/phase112-current.json \
  --markdown-output-path runtime-state/engineering-tenet-coverage/phase112-current.md
```

Expected markers:

```text
ENGINEERING TENET COVERAGE REPORT ...
ENGINEERING TENET COVERAGE SUMMARY ...
ENGINEERING TENET COVERAGE PASS
```

## Expected Report Shape

```text
kind=engineering_tenet_coverage_report
status=passed|failed
summary.tenet_count=20
summary.expected_tenet_count=20
summary.status_counts={...}
entries[].tenet_id=T01..T20
entries[].status=covered|partially_covered|not_covered|not_applicable_yet
entries[].minimum_live_validation_tier=gateway|anythingllm_api|ui|fixture_mutation|release_adherence|contextless_audit
errors=[...]
```

## Matrix Review

Use this review order before starting a tenet phase:

1. Check entries for the target phase.
2. Confirm current evidence does not overclaim coverage.
3. Confirm `known_gaps` align with the next roadmap phase.
4. Turn `contextless_audit_criteria` into bounded blind-review prompts.
5. Require live validation at or above `minimum_live_validation_tier`.

For Phase 113, start with `T01`, `T02`, and `T03`. After Phase 113, those entries should reference `task_decomposition_phase113_cases`, `task_decomposition_quality`, and `scripts/validate_task_decomposition_live.py`.

For Phase 114, start with `T04` and `T05`. After Phase 114, those entries should reference `requirements_translation_phase114_cases`, `requirements_translation_live`, `scripts/validate_requirements_translation_phase114_cases.py`, and `scripts/validate_requirements_translation_live.py`.

For Phase 115, start with `T06` and `T07`. After Phase 115, those entries should reference `incremental_implementation_phase115_cases`, `incremental_implementation_live`, `scripts/validate_incremental_implementation_phase115_cases.py`, and `scripts/validate_incremental_implementation_live.py`.
