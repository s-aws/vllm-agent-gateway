# Route Stability Holdout Replay Examples

Run offline preflight:

```bash
python3 scripts/validate_route_stability_holdout_replay.py
```

Run live gateway and AnythingLLM replay after localhost `8000`, `8300`, `8400`, and `8500` are healthy and AnythingLLM is pointed at the workflow-router gateway:

```bash
export ANYTHINGLLM_API_KEY="<local key>"
python3 scripts/validate_route_stability_holdout_replay.py --live --timeout-seconds 900
```

Expected live summary:

```text
PHASE205 ROUTE STABILITY HOLDOUT REPLAY SUMMARY ... "passed_response_count": 74 ... "route_drift_count": 0 ...
PHASE205 ROUTE STABILITY HOLDOUT REPLAY PASS
```

Inspect the report:

```bash
python3 -m json.tool runtime-state/phase205/phase205-route-stability-holdout-replay-report.json
```

The live report must show `33` target cases, `4` holdout cases, `74` total responses, surfaces `gateway` and `anythingllm`, both frozen Coinbase fixture roots, non-unknown run IDs, and `phase206_ready=true`.
