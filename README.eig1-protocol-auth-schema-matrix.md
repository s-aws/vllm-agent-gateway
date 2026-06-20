# EIG-1 Protocol Auth Schema Matrix

This feature validates the Phase 290 EIG-1 protocol, auth, and schema classification matrix.

It proves that connector admission and mediation behavior is explicit instead of accidentally accepting or executing unsupported combinations.

## What It Covers

- `local_stub` is the only executable protocol.
- `https_json` and `mcp_mediated` are validation-only and fail at mediation with `connector_protocol_not_executable`.
- unsupported protocols are rejected.
- `none_for_stub`, `service_read_only`, and `oauth_user_scope` auth combinations are accepted or rejected deterministically.
- required fields, optional booleans, integers, arrays, objects, unknown arguments, missing arguments, and malformed argument types have explicit tests.
- deep nested object property validation is documented as deferred rather than silently treated as complete.

## Run

```bash
python3 scripts/validate_eig1_protocol_auth_schema_matrix.py
python3 -m pytest tests/regression/test_eig1_protocol_auth_schema_matrix.py -q
```

On Windows PowerShell:

```powershell
python scripts/validate_eig1_protocol_auth_schema_matrix.py
python -m pytest tests/regression/test_eig1_protocol_auth_schema_matrix.py -q
```

## Output

The validator writes an `eig1_protocol_auth_schema_report` under:

```text
runtime-state/eig1-protocol-auth-schema-matrix/
```

The report is ready for Phase 291 only when `phase291_ready=true`.
