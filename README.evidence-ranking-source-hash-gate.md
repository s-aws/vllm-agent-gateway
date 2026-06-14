# Evidence Ranking Source Hash Gate

Phase 207 adds deterministic evidence-ranking and source-hash proof before live M4 evidence-quality reruns.

The gate extends the existing `code_investigation.plan` evidence ranking behavior. It does not add a parallel retrieval path. It validates that direct or strong evidence outranks weak or supporting matches and that every cited source reference has verifiable file-level and line-level SHA-256 proof.

## What Changed

- Long exact behavior or symbol queries now score higher than short broad underscore tokens.
- Source evidence no longer receives enough base weight to outrank a more specific direct test hit by default.
- Explicit path hints help ranking only after evidence score; a weak hinted path must not outrank stronger direct evidence.
- The Phase 207 validator computes file and line hashes for cited evidence refs and fails missing, stale, or unverifiable line/query proof.
- Negative controls prove that weak broad evidence, weak hinted evidence, and repeated weak hinted matches stay below direct behavior evidence.

## Inputs

- `runtime/evidence_ranking_source_hash_gate_policy.json`
- `runtime-state/phase206/phase206-evidence-relevance-audit-pack-report.json`
- `runtime-state/evidence-relevance-ranking/phase182-live-report.json`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

## Outputs

- `runtime-state/phase207/phase207-evidence-ranking-source-hash-gate-report.json`
- `runtime-state/phase207/phase207-evidence-ranking-source-hash-gate-report.md`

## Validation

Run these commands from Bash/WSL. The policy intentionally references `/mnt/c/...` frozen fixture roots, so native Windows Python is not the canonical validation surface for this gate.

```bash
python3 scripts/validate_evidence_ranking_source_hash_gate.py
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_evidence_ranking_source_hash_gate.py tests/regression/test_evidence_relevance_ranking.py -q
```

Expected passing marker:

```text
PHASE207 EVIDENCE RANKING SOURCE HASH GATE PASS
```

Phase 208 should rerun the Phase 206 prompts through gateway and AnythingLLM and compare live answers against the audit pack.
