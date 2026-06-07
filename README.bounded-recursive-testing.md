# Bounded Recursive Testing

Bounded recursive testing uses fresh no-context evaluators to find usability, routing, answer-quality, setup, safety, capability, and roadmap-drift issues. It is a governed evaluation loop over the existing harness, not a second runtime and not an automatic edit system.

Use it when a phase has working artifacts but needs outside-pressure testing before the result is treated as stable. The main value is that the evaluator does not inherit the implementation session, so it can catch unclear docs, weak chat output, missing artifacts, and overfit prompt behavior.

## Core Rule

The blind evaluator proposes findings only. Pass/fail is decided by deterministic evidence:

- route-decision artifacts
- chat-visible marker checks
- semantic marker checks
- source artifact refs
- fixture hashes
- git status
- live validation report links
- regression output
- run-artifact diff output
- failure taxonomy output

Do not accept a blind finding just because the evaluator sounds confident. Do not reject a blind finding without a written reason.

## Concrete Loop

1. Select a scenario from `runtime/recursive_blind_testing_policy.json`.
2. Run the current harness normally and capture the prompt, visible response, route decision, downstream artifacts, fixture state, and validation reports.
3. Build a blind packet with only explicit prompt text, selected artifacts, selected docs, and visible user-facing output. Do not include private session memory or patch explanations.
4. Run a fresh evaluator with `fork_context=false`.
5. Classify every finding with the governed categories and severity levels.
6. Accept or reject each finding using deterministic evidence.
7. For accepted findings, implement only the smallest current-phase tightening or add a roadmap action if the fix is future scope.
8. Rerun the target case and at least one holdout when the accepted changes are broad enough to risk overfitting.
9. Stop when convergence criteria pass or when a stop condition is hit.

## Bounds

The policy intentionally limits recursion:

- maximum `3` rounds
- maximum `12` findings per round
- maximum `8` accepted changes per round
- maximum `2` repair cycles per issue
- holdout required when accepted changes exceed the configured threshold

Round exhaustion is not convergence. A report that reaches the round limit must be marked failed or deferred, not passed.

## Scoring

Reports use a 100-point rubric:

- 20: route, workflow, skill, and tool correctness
- 20: evidence grounding and artifact quality
- 20: semantic correctness
- 15: output contract and chat-visible markers
- 10: verification command relevance
- 10: safety, approval, and mutation boundary
- 5: diagnosability

A passed report needs a total score of at least `85` and every category score at or above the configured category floor. Stable-channel use is stricter: mean score at least `90` and no required case below `85`.

## Stop Conditions

Stop the loop and classify the failure if any of these occur:

- the same critical or high finding repeats after two accepted fixes
- a target case improves while a holdout regresses
- evaluator disagreement over semantic score exceeds 10 points
- the required fix expands scope beyond the approved roadmap phase
- live localhost or AnythingLLM validation fails after an accepted change
- a protected frozen fixture changes
- the evaluator says manual skill injection is required for the product to work
- the loop reaches `max_rounds` without convergence

## Artifacts

Policy:

```text
runtime/recursive_blind_testing_policy.json
```

Validation reports:

```text
runtime-state/recursive-blind-testing/
```

Recursive reports supplied to the validator must use `kind: recursive_blind_testing_report` and include:

- scenario id
- no-context round metadata
- input refs
- blind findings
- accepted and rejected findings
- score summary
- convergence status and evidence refs

## Commands

Validate the policy:

```bash
python scripts/validate_recursive_blind_testing.py
```

Validate a specific recursive report:

```bash
python scripts/validate_recursive_blind_testing.py \
  --report runtime-state/recursive-blind-testing/<run-id>/recursive-report.json
```

Run focused regression for the policy and report contract:

```bash
python -m pytest tests/regression/test_recursive_blind_testing.py -q
```

Non-agent code changes still require:

```bash
python -m pytest tests/regression/ -v
```

## Roadmap Use

Phase 92 uses bounded recursive testing to pressure-test founder and external tester feedback triage. Future phases can use the same loop for capability gap discovery, skill selection hardening, model portability, onboarding, and eval-driven repair. A future auto-repair runner must still use the same policy and must not mutate prompt catalogs, routes, or fixtures without the roadmap approval and validation gates already required by this project.
