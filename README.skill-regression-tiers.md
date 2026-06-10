# Skill Regression Tiers

Phase 81 defines explicit validation tiers for skill-library work.

The source of truth is `runtime/skill_regression_tiers.json`. The catalog is validated by:

```bash
python scripts/validate_skill_regression_tiers.py
```

The tier catalog composes existing validators and release-gate profiles. It does not create a second release system.

## Tiers

- `offline`: static registry, eval, selector, prompt coverage, docs, and focused regression proof.
- `controller`: controller-owned workflow and chat-rendering unit proof.
- `gateway`: Bash-hosted localhost proof through `8000`, `8300`, `8500`, `8400`, `8205`, and both frozen Coinbase fixtures, without AnythingLLM.
- `anythingllm-api`: AnythingLLM workspace API proof through the workflow-router gateway.
- `anythingllm-ui`: browser-rendered AnythingLLM UI proof.
- `fixture-mutation`: disposable-copy mutation and protected fixture proof.
- `release-candidate`: full product proof with static checks, mutation proof, live gateway, AnythingLLM API, both frozen fixtures, and full regression.

## Minimum Tier By Change Type

Use the catalog instead of guessing:

```bash
python scripts/validate_skill_regression_tiers.py --output-path runtime-state/skill-regression-tiers/current.json
```

Then inspect `runtime/skill_regression_tiers.json`:

- docs-only or prompt-coverage changes: `offline`
- controller workflow or scaffold changes: `controller`
- gateway/router/live chat-output changes: `gateway`
- AnythingLLM API or founder-field prompt changes: `anythingllm-api`
- UI-rendered AnythingLLM changes: `anythingllm-ui`
- mutation harness, controlled apply, fixture manager, tool execution: `fixture-mutation`
- release, cross-cutting runtime, router policy, model portability, skill scale: `release-candidate`

Code changes require the verification tier that matches the change blast radius. Use focused tests during iteration; full regression is mandatory for release-candidate, cross-cutting runtime, shared controller/router/formatter, skill-library-scale, model-portability, or otherwise unbounded changes. Workflow-local controller changes should run full regression once at phase close.

Examples: [docs/examples/skill-regression-tiers.md](docs/examples/skill-regression-tiers.md).
