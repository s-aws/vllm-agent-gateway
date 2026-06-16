# Large-Context 384k Stale-Index Rejection

This gate proves the 384k retrieval path can fail closed when the index cannot be trusted.

It validates controlled disposable cases for:

- stale source hash
- changed ignore policy
- changed safety policy
- missing indexed source
- retrieval answer with all evidence rejected by freshness or policy checks
- unsafe private, ignored, credential, token, or secret-like evidence requests

## Command

```bash
python3 scripts/validate_large_context_384k_stale_index_rejection.py
```

## Pass Marker

```text
PHASE260 LARGE CONTEXT 384K STALE INDEX REJECTION PASS
```

This phase must pass before the live 384k acceptance validator. A live answer that uses stale or unsafe derived index state is a product failure, even if it returns fluent chat text.
