# Clone-Safe Model Capability Routing

Phase 235 makes model-capability routing usable from a clean checkout by moving the active routing profile dependency out of `runtime-state/`.

The workflow router still fails closed. The change does not enable automatic model selection, real apply, or broader mutation. It only makes the current approved local model profile available from committed runtime files so a clean snapshot or future clone can route supported read-only prompts without manually copying local runtime-state artifacts.

## Runtime Files

- Routing policy: `runtime/model_capability_routing.json`
- Clone-safe profile: `runtime/model_capability_profiles/phase100-current-profile.json`
- Validation policy: `runtime/clone_safe_model_capability_routing_policy.json`

The routing policy must point to `runtime/model_capability_profiles/`, not `runtime-state/`.

## Validate

Static gate:

```bash
python3 scripts/validate_clone_safe_model_capability_routing.py \
  --allow-missing-clean-handoff-report
```

Full Phase 235 gate after rerunning clean handoff:

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --output-path runtime-state/phase235/phase235-clean-clone-release-handoff-report.json \
  --markdown-output-path runtime-state/phase235/phase235-clean-clone-release-handoff-report.md \
  --prepare-snapshot \
  --run-commands \
  --run-live-minimal \
  --timeout-seconds 240

python3 scripts/validate_clone_safe_model_capability_routing.py
```

The full gate must show `clean_handoff_runtime_seed_count=0`.
