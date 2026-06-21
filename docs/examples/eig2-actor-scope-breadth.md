# EIG-2 Actor Scope Breadth Examples

Run the Phase 293 validator:

```bash
python3 scripts/validate_eig2_actor_scope_breadth.py
```

Run the focused regression:

```bash
python3 -m pytest tests/regression/test_eig2_actor_scope_breadth.py -q
```

Write a report to a specific path:

```bash
python3 scripts/validate_eig2_actor_scope_breadth.py \
  --output-path runtime-state/eig2-actor-scope-breadth/manual-eig2-report.json
```

Expected success marker:

```text
EIG2 ACTOR SCOPE BREADTH PASS
```

The report should show:

```json
{
  "status": "passed",
  "summary": {
    "operation_scope_assignment_count": 4,
    "actor_scope_case_count": 7,
    "actor_context_negative_case_count": 4,
    "read_without_write_allowed": true,
    "write_without_read_allowed": true,
    "cross_connector_scope_denied": true,
    "scope_denials_have_recovery": true,
    "phase294_ready": true
  }
}
```

The knowledge/document connector is intentionally recorded as `not_scoped_service_read_only` in the policy. Do not add fake OAuth user scopes to that archetype just to satisfy EIG-2 breadth; Phase 293 covers scoped work-tracking and structured business-record operations.
