# Evidence Relevance Audit Pack

Phase 206 creates the M4 evidence-quality audit pack.

This is not a ranking repair and does not change retrieval behavior. It defines the contextless audit cases, blind-baseline evidence expectations, scoring rubrics, prior proof dependencies, and current gap classifications that later evidence-ranking and live-rerun phases must use.

## What It Covers

- Code investigation evidence for the beginning point of a behavior.
- Related-test discovery evidence and coverage gaps.
- Validation-command selection evidence for smallest, medium, and broad commands.
- Change-boundary analysis evidence for files to touch, files not to touch, risks, unknowns, and verification commands.

Each case defines direct, strong, supporting, weak, and irrelevant evidence so a reviewer can distinguish proof from broad keyword matches.

## Inputs

- `runtime/evidence_relevance_audit_pack_policy.json`
- `runtime/prompt_catalogs/founder_field_v1.json`
- `runtime-state/evidence-relevance-ranking/phase182-live-report.json`
- `runtime-state/phase205/phase205-route-stability-holdout-replay-report.json`

## Outputs

- `runtime-state/phase206/phase206-evidence-relevance-audit-pack-report.json`
- `runtime-state/phase206/phase206-evidence-relevance-audit-pack-report.md`

Examples live in [docs/examples/evidence-relevance-audit-pack.md](docs/examples/evidence-relevance-audit-pack.md).

## Validation

```bash
python3 scripts/validate_evidence_relevance_audit_pack.py
```

Expected passing marker:

```text
PHASE206 EVIDENCE RELEVANCE AUDIT PACK PASS
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_evidence_relevance_audit_pack.py -q
```

## Acceptance

The gate fails if a case lacks a governed category, source-catalog link, complete evidence tiers, a 100-point rubric, line-level evidence expectations, safety boundaries, governed gap classifications, prompt-family alignment with Phase 205 route proof, or passing source reports.

The source proof dependencies are identity-locked to:

- Phase 182 evidence relevance ranking live report.
- Phase 205 route stability holdout replay report.

Phase 207 should use this audit pack to add deterministic evidence ranking and source-hash gates.
