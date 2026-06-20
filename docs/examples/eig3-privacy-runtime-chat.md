# EIG-3 Privacy Runtime Chat Examples

Run the live Phase 302 proof:

```bash
python3 scripts/validate_eig3_privacy_runtime_chat.py \
  --anythingllm-api-base-url http://100.100.12.45:3001 \
  --output-path runtime-state/eig3-privacy-runtime-chat/phase302-validation.json
```

Run the gateway-only proof when AnythingLLM is not available:

```bash
python3 scripts/validate_eig3_privacy_runtime_chat.py \
  --skip-anythingllm \
  --output-path runtime-state/eig3-privacy-runtime-chat/phase302-gateway-only.json
```

Run the offline validator shape check:

```bash
python scripts/validate_eig3_privacy_runtime_chat.py \
  --no-live \
  --skip-anythingllm \
  --output-path runtime-state/eig3-privacy-runtime-chat/phase302-offline-shape.json
```

Focused regression:

```bash
python -m pytest \
  tests/regression/test_eig3_privacy_runtime_routing.py \
  tests/regression/test_eig3_privacy_runtime_chat.py \
  -v
```

The live report is local runtime state and should not be committed.
