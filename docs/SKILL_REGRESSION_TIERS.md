# Skill Regression Tiers

Phase 81 makes skill-library validation explicit.

Before this phase, the project had strong validators but the choice of which validator to run for a given change was scattered across roadmap notes, README sections, and prior session memory. The tier catalog gives contextless contributors and agents one place to look.

## Source Of Truth

- Catalog: `runtime/skill_regression_tiers.json`
- Validator: `scripts/validate_skill_regression_tiers.py`
- Code: `vllm_agent_gateway/skills/regression_tiers.py`

The catalog defines seven tiers in increasing order:

1. `offline`
2. `controller`
3. `gateway`
4. `anythingllm-api`
5. `anythingllm-ui`
6. `fixture-mutation`
7. `release-candidate`

Each tier declares:

- purpose
- change types for which it is the minimum tier
- runtime requirements
- command list
- fixture roots where applicable

## Drift Rules

The validator fails if:

- a required tier is missing or out of order
- a command references a missing script or regression path
- a change type in a tier is missing from `change_type_minimums`
- gateway or AnythingLLM tiers lose localhost port requirements
- fixture and release tiers lose either frozen Coinbase fixture
- fixture mutation loses disposable mutation proof
- release candidate loses `scripts/validate_skill_release_gate.py --profile release-candidate`
- release candidate loses full regression

## Release Candidate Contract

The release-candidate tier must keep:

- localhost `8000`
- gateway `8300`
- workflow-router gateway `8500`
- controller `8400`
- role port `8205`
- AnythingLLM API proof
- both frozen Coinbase fixtures
- disposable mutation proof
- full regression

AnythingLLM UI is a separate tier because it is useful for tester-visible rendering proof but is not required for every release-candidate skill-library gate until the roadmap explicitly changes that boundary.

## Phase 81 Proof Shape

A complete Phase 81 proof includes:

- tier catalog validation pass
- focused tier regression pass
- docs index pass
- prompt coverage validation pass
- full regression pass after code changes
- protected fixture mutation proof

Phase 82 extends the fixture tier with `node-cli-generalization` and `scripts/validate_multi_repo_fixtures_live.py`, which proves prompt behavior across both frozen Coinbase fixtures and a non-Coinbase JavaScript/Node CLI fixture.
