# Skill Packaging

Skill packaging defines how project-local skills are grouped, validated, imported, installed, versioned, and retired as the library scales.

This is not a second skill runtime. Pack validation and installation reuse the existing registry, eval catalog, selector, lifecycle, and approval-gated install workflows.

## Policy File

The canonical machine-readable policy is:

```text
runtime/skill_pack_policy.json
```

Validate it:

```bash
python scripts/validate_skill_packaging_policy.py
```

Expected markers:

```text
SKILL PACKAGING POLICY REPORT ...
SKILL PACKAGING POLICY SUMMARY ...
SKILL PACKAGING POLICY PASS
```

## Package Layout

Use this layout for exported packs:

```text
<pack-root>/
  pack.json
  skills/
    <skill-id>/
      SKILL.md
  docs/
    ...
```

`pack.json` must be a `skill_pack_manifest` with the fields enforced by the existing skill-pack validator:

```text
schema_version, kind, id, version, owner, description, namespaces,
compatibility, docs, skills, eval_cases
```

Skill metadata starts as `eval_status: draft`. Promotion remains a separate proof-gated lifecycle operation.

## Namespace Ownership

Packs must declare every route namespace they use. Every skill in the pack must:

- use one declared route-key namespace
- have the same owner as the pack
- avoid active namespace collisions with skills owned by a different owner
- follow strict namespace rules for `draft`, `implementation`, and `feedback`

Allowed route namespaces are the registry namespaces in `vllm_agent_gateway/skills/registry.py`.

## Dependencies

Current packs may depend only on:

- docs
- eval cases
- skill bodies
- existing workflows
- existing controller tools
- live-suite mappings

They may not add Python packages, external services, new tool IDs, new workflows, or fine-tuning requirements without a separate approved roadmap phase.

## Versioning

Pack versions use semantic versioning.

Default bump rules:

- patch: metadata-only, skill-body-only, or eval-case-only updates
- minor: new skill or eval case
- major: route-key, namespace, workflow dependency, or tool dependency changes

## Import And Install

Validate before install:

```bash
python scripts/validate_skill_pack.py --pack-file <pack-root>/pack.json
```

Install requires the existing approval-gated workflow:

```text
skill_pack.install
approval.status=approved_for_skill_pack_install
approval.scope=skill_pack_install
runtime_registry_append=true
skill_body_install=true
```

Install re-runs validation before mutation and writes rollback artifacts.

## Retirement

Uninstall is not supported yet. Retire skills through `skill.deprecate` with a valid replacement. A deprecated skill must declare replacement metadata, and the replacement must exist and not be deprecated.

## Safety

- No pack may bypass eval, registry, selector, or release-gate checks.
- No pack may create a parallel workflow or tool path.
- No pack install may run without explicit approval.
- No pack install promotes skills to validated automatically.
