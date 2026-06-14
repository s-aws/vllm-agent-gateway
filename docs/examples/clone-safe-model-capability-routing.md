# Clone-Safe Model Capability Routing Examples

Run a static clone-safe routing check:

```bash
python3 scripts/validate_clone_safe_model_capability_routing.py \
  --allow-missing-clean-handoff-report
```

Rerun the clean handoff after the active profile has moved out of `runtime-state/`:

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --output-path runtime-state/phase235/phase235-clean-clone-release-handoff-report.json \
  --markdown-output-path runtime-state/phase235/phase235-clean-clone-release-handoff-report.md \
  --prepare-snapshot \
  --run-commands \
  --run-live-minimal \
  --timeout-seconds 240
```

Close Phase 235:

```bash
python3 scripts/validate_clone_safe_model_capability_routing.py
```

Expected summary fields:

```text
profile_path_uses_runtime_state=false
clean_handoff_runtime_seed_count=0
decision=clone_safe_routing_ready
```
