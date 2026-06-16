# Large-Context 500k Answer-Quality Repair

This gate closes targeted 500k answer-quality repair after live acceptance.

The current Phase 273 proof has zero critical or high findings, so Phase 274 records `no_repair_required`. If Phase 273 later exposes accepted critical or high findings, this gate fails until the smallest targeted controller, workflow, skill, tool, or formatter repair is implemented and the affected prompt plus holdouts are rerun.

## What This Proves

- Phase 273 live 500k acceptance passed.
- Phase 273 reported zero critical or high blind-baseline findings.
- No targeted 500k answer-quality repair is required before clean-clone replay.
- 500k is still a candidate target, not the stable baseline.

## Command

```bash
python3 scripts/validate_large_context_500k_answer_quality_repair.py
```

Expected marker:

```text
PHASE274 LARGE CONTEXT 500K ANSWER QUALITY REPAIR PASS
```

Expected decision:

```text
no_repair_required
```

## Scope Boundary

This phase does not call vLLM, the workflow-router gateway, the controller, or AnythingLLM. It consumes the Phase 273 live report and either closes as no repair required or blocks on accepted answer-quality findings.
