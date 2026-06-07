# Phase 92 Feedback Triage

Phase 92 turns tester and blind-review feedback into either current-path fixes or explicit future roadmap work. This is not a prompt-tuning phase; accepted issues require artifact evidence and validation.

## Evidence Sources

- Stable handoff smoke: `runtime-state/stable-handoff/phase91-bash-stable-smoke.json`
- Phase 92 first-time doctor: `runtime-state/first-time-user-doctor/phase92-feedback-triage-doctor.json`
- Live AnythingLLM onboarding proof: `runtime-state/external-tester-onboarding/phase92-feedback-triage-onboarding-live.json`
- Live V1 acceptance proof: `runtime-state/v1-acceptance/phase92-feedback-triage-v1-acceptance.json`
- Feedback triage artifact: `runtime-state/feedback-triage/phase92-feedback-triage.json`
- Recursive blind-testing report: `runtime-state/recursive-blind-testing/phase92-feedback-triage-recursive-report.json`

The no-context blind review was used as finding input only. Final accept/reject decisions came from deterministic artifacts, code inspection, focused regression, and live Bash/AnythingLLM validation.

## Current-Phase Fixes

`P92-001`: no-gap feedback was incorrectly classified as missing.

Root cause: natural feedback parsing treated explicit text such as `missing: none for V1 acceptance` as a real missing item. This created false `useful + missing` classifications and wrong next actions.

Fix: `workflow_feedback.record` now treats no-op missing segments as empty, and V1 acceptance rejects synthetic missing classifications for no-gap feedback.

Proof:

```powershell
python -m pytest tests\regression\test_v1_acceptance.py tests\regression\test_external_tester_onboarding.py tests\regression\test_controller_service.py::test_workflow_router_chat_natural_feedback_missing_none_stays_positive -q
```

Live proof: `runtime-state/v1-acceptance/phase92-feedback-triage-v1-acceptance.json` passed with useful-only feedback records through both gateway and AnythingLLM.

`P92-002`: onboarding proof did not capture chat-visible output markers.

Fix: live onboarding reports now include `visible_response` and `feedback_response` evidence with marker status, missing marker list, bounded text samples, and SHA-256 hashes.

Proof: `runtime-state/external-tester-onboarding/phase92-feedback-triage-onboarding-live.json`.

`P92-003`: the git-enabled frozen fixture warning was unclear.

Fix: stable handoff docs now explain that Bash can show a line-ending dirty baseline for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`. The warning is not a blocker when watched hashes and protected fixture checks remain unchanged.

Proof: `README.stable-handoff.md`, `docs/examples/stable-handoff.md`, and the Phase 92 first-time doctor report.

## Future Roadmap Items

`P92-004`: generate exact packet operations from an approved investigation.

Disposition: accepted, but deferred to Phase 96. Pulling this into Phase 92 would expand the phase from feedback triage into implementation-prep workflow design.

`P92-005`: legacy feedback artifacts lack modern context fields.

Disposition: accepted as a report boundary. Legacy records may inform trends, but current release-pass proof must use structured records with `feedback_context`, classifications, next action, and route evidence.

`P92-006`: prompt diversity is still too narrow for broad product confidence.

Disposition: accepted for Phase 93 and Phase 94. Phase 93 expands the natural-language capability gap backlog; Phase 94 hardens repeated-run skill selection.

## Rejected Item

`P92-R001`: possible protected fixture mutation.

Disposition: rejected. The deterministic evidence does not support it. The live reports passed protected fixture checks, and watched protected file hashes stayed unchanged. The git-enabled fixture warning is documented as a line-ending baseline issue, not a source mutation.

## Phase 92 Close Criteria

Phase 92 is complete when these pass:

- recursive policy validation
- recursive feedback triage report validation
- focused regression for feedback parsing, onboarding evidence, and V1 acceptance feedback context
- docs index validation
- live Bash V1 acceptance through localhost model, controller, gateway, AnythingLLM, and both frozen fixtures
- full regression after code changes
- `git diff --check`

The next phase is Phase 93: Natural-Language Capability Gap Backlog.
