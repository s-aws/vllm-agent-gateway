# Contextless Agent Audit Pack Examples

## Validate The Audit Pack

Run from the repository root:

```bash
python3 scripts/validate_contextless_agent_audit_pack.py \
  --output-path runtime-state/contextless-agent-audit-pack/phase185/phase185-contextless-agent-audit-pack-report.json
```

Expected output:

```text
CONTEXTLESS AGENT AUDIT PACK PASS
```

## Minimal Audit Record Shape

Every audit record must preserve this ordering:

```json
{
  "report_id": "example",
  "prompt_family": "related_test_discovery_direct",
  "prompt": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose validation commands. Read only.",
  "prompt_hash": "2b6b18062d618784c48e47f721d614c47d66352334e22ac9f1fa1cbaea98fee5",
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
  "blind_agent": {
    "fork_context": false,
    "session_history_allowed": false,
    "local_model_output_seen": false
  },
  "blind_baseline": {
    "created_at": "2026-06-10T23:41:00Z",
    "prompt_hash": "2b6b18062d618784c48e47f721d614c47d66352334e22ac9f1fa1cbaea98fee5",
    "ideal_answer_shape": "Verification plan with evidence-backed command tiers.",
    "must_have_facts": ["direct related test evidence is identified"],
    "evidence_expectations": ["source refs", "confidence labels"],
    "safety_boundaries": ["read only"],
    "output_expectations": ["answer-first chat output", "run id remains visible"],
    "scoring_rubric": ["100-point rubric"]
  },
  "local_run": {
    "started_at": "2026-06-10T23:51:52Z",
    "prompt_hash": "2b6b18062d618784c48e47f721d614c47d66352334e22ac9f1fa1cbaea98fee5",
    "status": "passed",
    "run_id": "workflow-router-20260610T235152234913Z",
    "route_surfaces": ["localhost_8000_model", "workflow_router_gateway", "anythingllm"],
    "response_ref": "runtime-state/anythingllm-ui/phase184-ui-replay-report.json#UI184-RTD-001",
    "route_evidence": {
      "selected_workflow": "code_investigation.plan",
      "required_markers": ["Related tests:", "direct evidence", "high confidence"]
    },
    "fixture_mutation_proof": {
      "fixture_unchanged": true,
      "proof_ref": "runtime-state/anythingllm-ui/phase184-ui-replay-report.json"
    }
  },
  "comparison": {
    "prompt_hash": "2b6b18062d618784c48e47f721d614c47d66352334e22ac9f1fa1cbaea98fee5",
    "score": 96,
    "rubric_dimensions": ["test_relevance", "command_tiers", "risk_coverage"],
    "proof_flags": ["baseline-before-local", "same-prompt", "fixture-unchanged"]
  },
  "repair_decision": {
    "status": "no_repair_needed",
    "reason": "The answer met the blind baseline."
  },
  "closure": {
    "final_status": "passed",
    "fixture_unchanged": true,
    "validation_refs": ["tests/regression/test_contextless_agent_audit_pack.py"],
    "live_stack_proof_refs": ["runtime-state/anythingllm-ui/phase184-ui-replay-report.json"]
  }
}
```

## Failure Review

Open the generated report and inspect:

- `summary.validation_error_count`
- `validation_errors[].source`
- `validation_errors[].path`
- `validation_errors[].message`

Common failures:

- the blind baseline timestamp is after the local run timestamp
- the blind agent saw local model output
- the prompt hash differs between baseline, local run, and comparison
- the local run does not include localhost `8000`, workflow-router gateway, and AnythingLLM proof
- protected fixture mutation proof is missing or failed
