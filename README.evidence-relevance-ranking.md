# Evidence Relevance Ranking

Phase 182 hardens how read-only investigation answers rank evidence.

The goal is not more output. The goal is better ordering: direct behavior evidence should appear before broad keyword matches, source/test refs should carry inspectable relevance metadata, and chat answers should label direct, strong, supporting, or weak evidence.

## What It Covers

- Shared ranking for evidence file records in `code_investigation.plan`.
- Line-reference ranking inside each evidence file.
- Request-flow step ranking so direct handler branches outrank path-sorted broad matches.
- Change-surface summaries that expose relevance labels in chat.
- Synthetic negative controls plus live gateway and AnythingLLM validation on both frozen Coinbase fixtures.

## Validation

Synthetic gate:

```bash
python3 scripts/validate_evidence_relevance_ranking.py \
  --output-path runtime-state/evidence-relevance-ranking/phase182-synthetic-report.json \
  --markdown-output-path runtime-state/evidence-relevance-ranking/phase182-synthetic-report.md
```

Live gate:

```bash
python3 scripts/validate_evidence_relevance_ranking.py --live \
  --output-path runtime-state/evidence-relevance-ranking/phase182-live-report.json \
  --markdown-output-path runtime-state/evidence-relevance-ranking/phase182-live-report.md
```

If WSL does not inherit the Windows `ANYTHINGLLM_API_KEY`, pass it explicitly from PowerShell:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_evidence_relevance_ranking.py --live
```

## Acceptance

The gate fails when:

- a broad source keyword match outranks exact behavior evidence
- a broad line match outranks an exact symbol line in the same file
- request-flow evidence is sorted by path before a direct handler branch
- live chat output omits relevance labels
- watched frozen fixture files change

Policy lives in `runtime/evidence_relevance_ranking_policy.json`.
