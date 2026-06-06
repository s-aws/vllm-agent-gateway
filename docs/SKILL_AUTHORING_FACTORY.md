# Skill Authoring Factory

Phase 80 keeps skill creation on one controller path: `skill.scaffold`.

The factory layer adds sidecar artifacts to the existing scaffold workflow so future L1/L2 skills can be created from one prompt-family specification without bypassing registry admission, coverage governance, eval gates, or docs review.

## Design

The factory does not create a second implementation path.

`skill.scaffold` still creates the draft `SKILL.md`, batch manifest, eval case, batch validation report, validation checklist, scaffold report, and run state. Phase 80 adds:

- a planned prompt coverage entry
- an eval skeleton with four required gates
- a docs stub
- an example stub
- a fail-closed regression test skeleton
- an authoring factory report

These artifacts live under the disposable scaffold run directory. Runtime registries and target repositories are not changed.

## Required Gates

Every scaffolded skill must prove:

- routing: the natural prompt reaches the expected workflow and route evidence
- artifact contract: the expected artifact is produced or intentionally refused
- natural-language chat output: the chat answer gives immediate user-facing substance, not only file paths
- prompt coverage: the installed coverage entry validates against workflow, route rule, skill, tool, eval, docs, and expected artifacts

The generated pytest skeleton fails closed until those gates are wired. This is deliberate; scaffold output is not proof.

## Governance

Factory output inherits the existing skill governance path:

- skill IDs must match the existing lowercase hyphenated naming rule
- route keys are checked by the existing batch/registry validation path
- route namespaces must be supported by the registry namespace policy
- version starts at `0.1.0`
- lifecycle state remains `draft`
- docs refs are validated before the scaffold is marked ready
- promotion state remains `not_promoted_by_scaffold`

## Stop Conditions

Do not promote or install a scaffold when:

- batch validation reports `do_not_admit`
- route namespace is unsupported
- output artifact is unknown
- docs refs are missing
- generated coverage cannot be made `implemented` without missing skill, tool, route-rule, eval, or docs references
- live gateway or AnythingLLM proof is required but not available

## Phase 80 Proof Shape

A complete Phase 80 proof includes:

- focused scaffold regression
- Bash live validator through direct controller, explicit gateway, workflow-router gateway, and AnythingLLM when available
- dry-run scaffold artifact inspection in a disposable output directory
- fail-closed generated test skeleton checks
- unchanged `runtime/skills.json`
- unchanged `runtime/skill_evals.json`
- unchanged `runtime/prompt_skill_coverage.json`
- docs index pass
- full regression pass
- protected fixture hash proof
