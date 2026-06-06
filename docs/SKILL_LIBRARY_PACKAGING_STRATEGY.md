# Skill Library Packaging Strategy

Status: Phase 77 strategy and executable policy.

## Purpose

The skill library needs a packaging system before it can scale toward hundreds or thousands of skills. The failure mode to avoid is a large set of loose `SKILL.md` files, eval snippets, and registry edits that cannot be imported, reviewed, versioned, retired, or tested as one unit.

The packaging strategy keeps one runtime path:

```text
pack manifest
-> skill_pack.validate
-> approval
-> skill_pack.install
-> existing registry/eval/selector gates
-> promotion only after live proof
```

## Canonical Policy

The machine-readable policy is:

```text
runtime/skill_pack_policy.json
```

Validate it:

```bash
python scripts/validate_skill_packaging_policy.py
```

The validator checks the policy against the existing registry constants and skill-pack manifest contract. If registry namespaces, strict namespace rules, or required pack fields drift, the policy gate fails.

## Package Layout

Every exported pack uses:

```text
<pack-root>/
  pack.json
  skills/
    <skill-id>/
      SKILL.md
  docs/
    ...
```

The `pack.json` file is the only import entry point. Skill bodies remain local files referenced by metadata. Runtime installation writes to:

```text
runtime/skills.json
runtime/skill_evals.json
.qwen/skills/
```

## Manifest Contract

Required fields:

```text
schema_version
kind
id
version
owner
description
namespaces
compatibility
docs
skills
eval_cases
```

`kind` must be `skill_pack_manifest`. `schema_version` must be `1`. `version` must be semantic version `x.y.z`.

All imported skills start as `draft`. Promotion to `validated` remains separate and requires live proof.

## Namespace Ownership

Route namespaces are owned at the pack level.

Rules:

- A pack must declare every route namespace used by its skills.
- Every skill owner must match the pack owner.
- Active namespace collisions with a different owner are rejected.
- `draft`, `implementation`, and `feedback` namespaces must follow the strict rules in `vllm_agent_gateway/skills/registry.py`.

Allowed namespaces are:

```text
code, config, context, data, diagnostics, docs, draft, feedback,
git, implementation, planning, test, verification
```

## Dependency Policy

Current skill packs may depend only on existing project capabilities:

- docs
- eval cases
- skill bodies
- existing workflows
- existing controller tools
- live-suite mappings

Disallowed without a separately approved roadmap phase:

- new Python packages
- new external services
- new tool IDs without tool-catalog approval
- new workflows
- fine-tuning requirements

This keeps skill packaging as metadata and procedural guidance, not a hidden runtime expansion mechanism.

## Versioning

Pack versions use semantic versioning.

Version bump rules:

```text
metadata_only -> patch
skill_body_only -> patch
eval_case_only -> patch
new_skill_or_eval_case -> minor
route_key_or_namespace_change -> major
workflow_or_tool_dependency_change -> major
retirement_or_deprecation_metadata -> minor
```

Route-key and namespace changes are major because they alter deterministic selection behavior.

## Import And Export

Exported packs include:

- `pack.json`
- skill bodies
- eval cases
- docs references

Import sequence:

1. Run `python scripts/validate_skill_packaging_policy.py`.
2. Run `python scripts/validate_skill_pack.py --pack-file <pack-root>/pack.json`.
3. Review the pack and approve only if the validation report is passed.
4. Install through `skill_pack.install` with `approval.status=approved_for_skill_pack_install`.
5. Run skill eval, scale, selector-scale, and release gates before promotion.

Install re-runs validation immediately before mutation. It records hash proof and rollback artifacts.

## Retirement

Uninstall is not supported in this phase.

Retire skill behavior by deprecating a skill through `skill.deprecate`:

- deprecated skill must exist
- replacement skill must exist
- replacement cannot be deprecated
- replacement must be compatible with workflow, route namespace, safety level, mutation policy, and approval boundary

Pack-level retirement metadata must include:

```text
reason
effective_date
replaced_by
replacement_pack
```

## Stop Conditions

Stop packaging work if any pack:

- requires manual registry edits
- bypasses `skill_pack.validate`
- installs without explicit approval
- promotes imported skills automatically
- adds a new runtime dependency
- introduces an undeclared route namespace
- creates a parallel implementation path for an existing prompt family

## Phase 77 Proof Gate

Phase 77 is complete only when:

- `runtime/skill_pack_policy.json` validates
- focused policy regression passes
- docs index has no orphan docs
- full regression passes after code changes
- the roadmap records the policy report path and validation proof
