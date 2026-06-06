# Skill Packaging Examples

These examples cover packaging policy and pack validation. They do not create a second skill runtime.

## Validate The Packaging Policy

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_skill_packaging_policy.py \
  --output-path runtime-state/skill-packaging-policy/latest-policy.json
```

Expected markers:

```text
SKILL PACKAGING POLICY REPORT ...
SKILL PACKAGING POLICY SUMMARY ...
SKILL PACKAGING POLICY PASS
```

## Validate A Pack

```bash
python3 scripts/validate_skill_pack.py \
  --pack-file runtime-state/example-pack/pack.json \
  --output-path runtime-state/skill-packs/example-pack-validation.json
```

Expected markers:

```text
SKILL PACK REPORT ...
SKILL PACK SUMMARY ...
SKILL PACK PASS
```

## Direct Controller Validation

```json
{
  "workflow": "skill_pack.validate",
  "schema_version": 1,
  "pack_path": "runtime-state/example-pack/pack.json"
}
```

## Approved Install Shape

```json
{
  "workflow": "skill_pack.install",
  "schema_version": 1,
  "pack_path": "runtime-state/example-pack/pack.json",
  "approval": {
    "status": "approved_for_skill_pack_install",
    "scope": "skill_pack_install",
    "runtime_registry_append": true,
    "skill_body_install": true,
    "approval_refs": ["founder-review:example-pack"]
  }
}
```

Install re-runs validation before mutation and writes rollback instructions.

## Review Order

1. Validate `runtime/skill_pack_policy.json`.
2. Validate `pack.json`.
3. Review namespaces and route keys.
4. Confirm no new dependency is hidden in the pack.
5. Install only with explicit approval.
6. Run skill eval, scale, selector-scale, and live release gates.
7. Promote imported draft skills only after proof.
