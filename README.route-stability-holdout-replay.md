# Route Stability Holdout Replay

Phase 205 proves that route, skill, and tool selection remains stable after Phase 204 no-manual-skill-injection hardening.

The gate replays the exact Phase 204 target prompts from the Phase 204 live report and governed semi-well-defined holdout cases through the existing workflow-router gateway and AnythingLLM. It compares target route signatures exactly against the Phase 204 baseline and compares holdouts against exact policy signatures that must remain aligned with the current selection matrix.

A route signature is:

- selected workflow
- route rules
- selected skills
- selected tools

Live closeout requires `74` passing responses: `33` Phase 204 target cases plus `4` holdout cases across `gateway` and `anythingllm`. It also requires both frozen Coinbase roots, non-unknown run IDs, zero route drift, and no fixture mutation.

## Inputs

- `runtime/route_stability_holdout_replay_policy.json`
- `runtime-state/phase204/phase204-no-manual-skill-injection-explainability-report.json`
- `runtime-state/phase203/phase203-workflow-skill-tool-selection-matrix-report.json`
- `runtime/prompt_catalogs/founder_field_v1.json`
- `runtime/prompt_catalogs/semi_well_defined_v1.json`

## Outputs

- `runtime-state/phase205/phase205-route-stability-holdout-replay-preflight-report.json`
- `runtime-state/phase205/phase205-route-stability-holdout-replay-report.json`
- `runtime-state/phase205/phase205-route-stability-holdout-replay-report.md`

## Commands

Offline preflight:

```bash
python3 scripts/validate_route_stability_holdout_replay.py
```

Live closeout:

```bash
export ANYTHINGLLM_API_KEY="<local key>"
python3 scripts/validate_route_stability_holdout_replay.py --live --timeout-seconds 900
```

Expected closeout marker:

```text
PHASE205 ROUTE STABILITY HOLDOUT REPLAY PASS
```

## Boundary

Phase 205 is a route-signature stability gate. It does not add a selector, does not run implementation, and does not broaden workflow tool permissions. If route drift appears, the result should become a repair proposal for the smallest selector, skill, tool, or prompt-catalog gap rather than a silent route-rule expansion.
