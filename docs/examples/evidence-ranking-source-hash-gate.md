# Evidence Ranking Source Hash Gate Examples

Run the Phase 207 gate:

```bash
python3 scripts/validate_evidence_ranking_source_hash_gate.py
```

Run the focused regression:

```bash
python3 -m pytest tests/regression/test_evidence_ranking_source_hash_gate.py tests/regression/test_evidence_relevance_ranking.py -q
```

Inspect the generated report:

```bash
python3 -m json.tool runtime-state/phase207/phase207-evidence-ranking-source-hash-gate-report.json
```

The report should show four passing cases, three passing negative controls, at least four source hashes, zero errors, and `phase208_ready=true`.

For each cited source reference, inspect `source_proofs` for:

- `sha256`: whole-file hash for the cited path.
- `line_sha256`: hash of the cited line.
- `line_contains_query=true`: proof that the cited line still contains the query used for ranking.

The negative controls should show `core/stealth_order_manager.py` as the top evidence path even when broad, hinted, or repeated hinted `core/order_engine.py` evidence is present.
