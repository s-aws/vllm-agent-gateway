# Evidence Relevance Ranking Examples

Run the synthetic ranking gate:

```bash
python3 scripts/validate_evidence_relevance_ranking.py
```

Run the live gate through gateway and AnythingLLM:

```bash
python3 scripts/validate_evidence_relevance_ranking.py --live
```

Founder test prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify files to touch and files not to touch for a minimal safe placed_order_id stealth lookup change. Read only and stop before implementation. Lead with strongest evidence, related tests, risks, gaps, and verification commands.
```

Expected behavior:

- the answer routes to `code_investigation.plan`
- `core/stealth_order_manager.py` appears before caller or bridge surfaces
- direct or strong evidence labels appear in chat
- caller-adjacent evidence such as `core/order_engine.py` is labeled as a boundary, not the owner
- source mutation remains false
