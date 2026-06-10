# AGENTS.md - Session Entry Point

This project runs on Windows 11 + VS Code. The live controller/gateway stack is Bash-hosted, so prefer Bash-side validation for localhost runtime tests.

## Hard Constraints

- Single code path per behavior; do not introduce parallel implementations.
- Use enums from existing enum modules where the codebase already provides them; do not add magic strings to shared behavior.
- Respect existing module locks and thread-safety boundaries.
- Use the verification tier that matches the change blast radius. Focused tests are required during iteration; full regression is required at phase close for shared controller/router/formatter behavior, cross-cutting runtime behavior, release-candidate work, or any change whose affected surface cannot be bounded confidently.
- Runtime-facing workflow changes must be tested against localhost `8000`, all controller/gateway featured ports, AnythingLLM when applicable, `/mnt/c/coinbase_testing_repo_frozen_tmp`, and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Protected frozen fixture source files must remain unchanged unless a disposable-copy test explicitly mutates a copy.

## Canonical Roadmap

Read `docs/ACTIONABLE_WORKFLOW_ROADMAP.md` first. It is the source of truth when it conflicts with older roadmap, skill, controller, gateway, or AnythingLLM planning docs.

Always work the lowest-numbered incomplete roadmap phase unless the user explicitly changes scope. Scope expansion requires founder approval and a roadmap update before implementation.

## Persistent Project Memory

Priority 0 is chat quality development and testing. All other work is secondary unless it directly supports improving or validating chat quality against the current local model, skills, and tools.

Priority 0 chat-quality testing uses a blind-baseline-first process by default:

1. Give the natural-language prompt to a bounded contextless blind agent before showing it any local-model output.
2. Ask that blind agent for the ideal answer shape, must-have facts, evidence expectations, safety boundaries, and scoring rubric.
3. Run the same prompt through the local stack, including the workflow-router gateway and AnythingLLM when applicable.
4. Compare the local response against the blind baseline for routing, evidence, correctness, completeness, output format, and user-visible usefulness.
5. Repair the smallest controller, workflow, skill, tool, or formatter gap and rerun the target prompt plus holdouts.

Blind structural audits remain useful, but they do not replace blind-baseline comparison for chat-answer quality.

Priority 1 is adding or improving skills and tools that cover gaps found while improving Priority 0.

Priority 2 is maintaining a logical set of future roadmap phases and raising concerns when a phase deviates from the original product goal.

Priority 3 is making the local model consistently demonstrate the engineering tenets listed in the canonical roadmap. Future phases should move one or more tenets toward contextless-agent auditability.

## Structured Development Rule

For every non-trivial change, follow this cycle and document the result:

1. Define the problem and user-visible failure.
2. Gather evidence from code, artifacts, tests, or live runtime behavior.
3. Identify root cause and reject plausible wrong explanations when they matter.
4. Define the smallest acceptable design that preserves the single code path rule.
5. Implement with focused scope.
6. Verify with the smallest defensible gate for the change class, then broaden only as blast radius requires.
7. Inspect artifacts and protected fixtures for mutation or missing proof.
8. Update docs and roadmap state so a contextless future agent can continue from the correct next step.

Do not treat a prompt tweak as a fix unless controller artifacts and live localhost `8000` tests prove it on both frozen Coinbase fixtures.

## Verification Gate Requirements

- Documentation, roadmap, prompt catalog metadata, or agent-instruction-only changes: validate formatting/links or targeted validators as applicable; regression may be skipped.
- Leaf validation scripts, isolated acceptance policies, or narrow tests: run the focused unit/regression tests and validator commands that cover the changed file.
- Workflow-local controller changes: run focused controller/regression tests, live prompt proof when runtime-facing, and full regression once at phase close.
- Shared controller, router, formatter, tool-selection, model-routing, mutation, fixture, or approval behavior: run focused tests first, then full Bash regression before completion.
- Runtime-facing behavior: run focused tests, live Bash validation through the relevant localhost ports, AnythingLLM proof when applicable, both frozen fixture checks, and full Bash regression before completion.
- Cross-cutting, release-candidate, model-portability, skill-library-scale, or unbounded-blast-radius changes: always end with full Bash regression.

Default full Bash regression command:

```bash
python3 -m pytest tests/regression/ -v
```
