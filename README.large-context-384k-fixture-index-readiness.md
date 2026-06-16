# Large-Context 384k Fixture And Index Readiness

This gate proves the accepted 384k-plus fixture and governed metadata-first index are ready before live 384k acceptance runs.

It composes the existing Phase 214, Phase 216, and Phase 217 gates. It does not create a second inventory, safety, or index implementation.

The gate checks:

- large-corpus estimated tokens are at least `384000`
- Phase 216 safety governance passed
- Phase 217 metadata-first index passed
- index retention remains metadata-only
- source text and rejected content are not stored
- query smokes and negative controls pass
- protected Coinbase fixture fingerprints do not change

## Command

Use Bash for the full bootstrap path:

```bash
python3 scripts/validate_large_context_384k_fixture_index_readiness.py
```

Use existing reports only when diagnosing a local platform issue:

```bash
python3 scripts/validate_large_context_384k_fixture_index_readiness.py --reuse-existing-reports
```

## Pass Marker

```text
PHASE259 LARGE CONTEXT 384K FIXTURE INDEX READINESS PASS
```

Phase 260 must still prove stale-index rejection before live 384k acceptance begins.
