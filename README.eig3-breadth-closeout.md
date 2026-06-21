# EIG-3 Breadth Closeout

Status: Phase 303.

This feature aggregates the EIG-3 synthetic privacy and memory-safety proof chain into a contextless closeout packet.

The closeout gate checks that Phase 297-302 docs and runtime fixtures exist, reruns Phase 298-302 validators, and records whether live runtime proof was included. Full regression is still required before Phase 303 is considered closed because the work touches router, runtime chat, privacy policy, and acceptance behavior.

## Files

- `runtime/eig3_breadth_closeout_policy.json`: required docs, runtime files, milestones, and phases.
- `vllm_agent_gateway/acceptance/eig3_breadth_closeout.py`: closeout aggregator.
- `scripts/validate_eig3_breadth_closeout.py`: CLI wrapper.

## Validation

Live closeout with gateway and AnythingLLM:

```bash
python3 scripts/validate_eig3_breadth_closeout.py \
  --anythingllm-api-base-url http://100.100.12.45:3001 \
  --output-path runtime-state/eig3-breadth-closeout/phase303-validation.json
```

Offline shape closeout:

```bash
python scripts/validate_eig3_breadth_closeout.py \
  --no-live-runtime \
  --skip-anythingllm \
  --output-path runtime-state/eig3-breadth-closeout/phase303-offline.json
```

Full regression required at phase close:

```bash
python3 -m pytest tests/regression/ -v
```

## Closeout Standard

Phase 303 is complete only when:

- Phase 298-302 validators pass.
- Gateway and AnythingLLM Phase 302 proof passes when runtime is available.
- Focused EIG-3 regression passes.
- Docs index validation passes.
- Full Bash regression passes.
- Any contextless audit finding is either fixed or documented as a follow-up.

## Known Limits

This closeout proves synthetic breadth coverage for EIG-3. It does not prove production DLP, real secret scanning, a real persistent memory store, or safe handling of real private user, employee, member, customer, credential, or confidential-business data.

The current leak checks are deterministic and heuristic. They catch raw fixture-token leakage and controlled unsafe routing failures, but they are not semantic DLP. They can miss transformed, partial, paraphrased, or semantically equivalent leakage. Any future real-data or production-memory milestone must add stronger detection, red-team cases, and independently computed scoring.

Offline closeout modes such as `--no-live-runtime` and `--skip-anythingllm` are useful for shape validation only. They do not satisfy the Phase 303 live runtime proof requirement.
