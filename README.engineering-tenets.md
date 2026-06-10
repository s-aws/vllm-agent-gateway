# Engineering Tenet Coverage

The engineering tenet coverage gate makes the local model engineering goals measurable. It does not claim the model already satisfies every tenet. It maps each tenet to current workflows, skills, tools, eval cases, live validators, chat-visible evidence, known gaps, and contextless audit criteria.

The governed matrix is:

```text
runtime/engineering_tenet_coverage.json
```

## When To Use It

Use this gate when reviewing whether the current harness is moving toward the founder's Priority 0 goal: better chat quality for natural development requests using current skills and tools.

The matrix answers:

- which tenets have current evidence
- which tenets are only partially covered
- which tenets still need future phases
- which live validation tier is required
- what a contextless reviewer should audit

## Coverage Statuses

Supported statuses:

- `covered`
- `partially_covered`
- `not_covered`
- `not_applicable_yet`

The current matrix is conservative. Most tenets are `partially_covered` or `not_covered`; that is intentional so later phases have measurable targets.

Phase 113 moves T01, T02, and T03 to bounded `covered` status for the current `task.decompose` scope. That coverage depends on schema v3 work packages, objective acceptance criteria, oversized-task clarification behavior, the Phase 113 prompt/audit case catalog, live gateway/AnythingLLM proof, and contextless audit.

Phase 114 moves T04 and T05 to bounded `covered` status for requirements translation and estimation inside the same `task.decompose` path. That coverage depends on source business requirement traceability, derived technical requirements, explicit assumptions, rejected assumptions, estimate bands, scope drivers, revision triggers, the Phase 114 prompt/audit case catalog, live gateway/AnythingLLM proof, and contextless audit.

Phase 115 moves T06 and T07 to bounded `covered` status for incremental implementation and version-control planning inside the same `task.decompose` path. That coverage depends on isolated changesets, functional outcomes, verification commands, acceptance checks, meaningful commit messages, commit order, branch guidance, traceability artifacts, source-apply blocking, the Phase 115 prompt/audit case catalog, live gateway/AnythingLLM proof, and contextless audit.

## Validation Tiers

Supported minimum live validation tiers:

- `gateway`
- `anythingllm_api`
- `ui`
- `fixture_mutation`
- `release_adherence`
- `contextless_audit`

## Command

```bash
python scripts/validate_engineering_tenet_coverage.py \
  --output-path runtime-state/engineering-tenet-coverage/phase112-current.json
```

Expected markers:

```text
ENGINEERING TENET COVERAGE REPORT ...
ENGINEERING TENET COVERAGE SUMMARY ...
ENGINEERING TENET COVERAGE PASS
```

## Fail Rules

The validator fails when:

- a tenet ID is missing
- a tenet ID is duplicated
- a tenet text does not exactly match the roadmap tenet
- a status is unsupported
- a validation tier is unsupported
- a workflow ID is not registered in `runtime/workflows.json`
- a tool ID is not registered in `runtime/tools.json`
- a skill ID is not registered in `runtime/skills.json`
- an eval case is not a known skill eval, governed prompt-catalog case, or approved external eval gate
- a live validator script path does not exist
- a covered or partially covered entry has no workflow, skill, tool, eval case, live validator, chat-visible evidence, or contextless audit criteria
- an uncovered entry has no known gap, future phase, or audit criteria
- an entry depends on unapproved advanced-refactor work

## Review Order

1. Start with `summary.status_counts`.
2. Review `not_covered` entries before adding new feature work.
3. Review `partially_covered` entries before claiming a tenet is satisfied.
4. Use `contextless_audit_criteria` to design blind evaluator packets.
5. Update the roadmap before expanding scope beyond the approved tenet phases.
