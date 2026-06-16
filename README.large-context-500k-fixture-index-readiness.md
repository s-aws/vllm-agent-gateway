# Large-Context 500k Fixture And Index Readiness

This gate proves the accepted fixture and governed metadata-first index are large enough for the 500k-token project usability candidate before stale-index rejection and live 500k validation run.

It uses the existing Phase 259 readiness path for corpus inventory, corpus/index safety, protected fixture fingerprinting, and context-index bootstrap. Phase 271 does not create a second indexing workflow; it raises the readiness threshold to `500000` and requires Phase 270 candidate-governance proof first.

## What This Proves

- Phase 270 passed and the 500k candidate target is approved but not stable.
- The existing Phase 259 readiness path still passes.
- Corpus estimated tokens meet or exceed `500000`.
- Indexed estimated tokens meet or exceed `500000`.
- The index remains metadata-only and does not store source text or rejected content.
- Protected Coinbase fixture fingerprints are checked by the delegated Phase 259 path.

## Command

```bash
python3 scripts/validate_large_context_500k_fixture_index_readiness.py
```

To reuse existing Phase 214, Phase 216, and Phase 217 reports instead of bootstrapping them:

```bash
python3 scripts/validate_large_context_500k_fixture_index_readiness.py --reuse-existing-reports
```

Expected marker:

```text
PHASE271 LARGE CONTEXT 500K FIXTURE INDEX READINESS PASS
```

## Scope Boundary

This phase does not call vLLM, the workflow-router gateway, the controller, or AnythingLLM.

Live 500k proof starts only after Phase 272 stale-index rejection passes. Raw 500k prompt serving remains unsupported unless a separate proof gate validates model config, vLLM settings, hardware memory, latency, and blind-baseline answer quality.
