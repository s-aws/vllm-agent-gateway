# Evidence Relevance Audit Pack Examples

Validate the Phase 206 audit pack:

```bash
python3 scripts/validate_evidence_relevance_audit_pack.py
```

Run the focused regression:

```bash
python3 -m pytest tests/regression/test_evidence_relevance_audit_pack.py -q
```

Inspect the generated report:

```bash
python3 -m json.tool runtime-state/phase206/phase206-evidence-relevance-audit-pack-report.json
```

The report should show four audit cases, the four M4 evidence categories, zero blocking gaps, and `phase207_ready=true`.
