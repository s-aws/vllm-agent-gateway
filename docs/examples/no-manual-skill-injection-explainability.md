# No Manual Skill Injection Explainability Examples

Run the offline gate before live proof:

```bash
python3 scripts/validate_no_manual_skill_injection_explainability.py
```

Run one live gateway-only case while debugging:

```bash
python3 scripts/validate_no_manual_skill_injection_explainability.py --live --skip-anythingllm --case-id P01 --allow-partial --timeout-seconds 900
```

Run the full live Phase 204 gate:

```bash
python3 scripts/validate_no_manual_skill_injection_explainability.py --live --timeout-seconds 900
```

Inspect the generated report:

```bash
python3 -m json.tool runtime-state/phase204/phase204-no-manual-skill-injection-explainability-report.json
```

The live report should show `gateway` and `anythingllm` surfaces, selected workflow/skills/tools for each case, rejected-candidate counts, and no protected fixture mutation.
