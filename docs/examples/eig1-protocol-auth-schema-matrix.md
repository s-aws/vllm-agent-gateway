# EIG-1 Protocol Auth Schema Matrix Examples

Run the Phase 290 validator:

```bash
python3 scripts/validate_eig1_protocol_auth_schema_matrix.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_eig1_protocol_auth_schema_matrix.py -q
```

Expected success marker:

```text
EIG1 PROTOCOL AUTH SCHEMA PASS
```

Expected summary shape:

```json
{
  "status": "passed",
  "summary": {
    "protocol_case_count": 4,
    "auth_case_count": 6,
    "schema_case_count": 13,
    "only_executable_protocol": "local_stub",
    "non_executable_protocols_fail_at_mediation": true,
    "phase291_ready": true
  }
}
```
