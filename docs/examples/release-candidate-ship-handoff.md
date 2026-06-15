# Release-Candidate Ship Handoff Examples

Run the handoff gate:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_release_candidate_ship_handoff.py
```

Inspect the generated local report:

```bash
jq '.summary, .release_proof.decision_source, .release_channel.stable_readiness' \
  runtime-state/release-candidate-ship-handoff/phase247/phase247-release-candidate-ship-handoff-report.json
```

Expected source markers:

```text
Decision: ship
Decision source commit: bb0c6b0
Gateway run: workflow-router-20260614T225336875601Z
AnythingLLM run: workflow-router-20260614T225345166828Z
```

If the gate fails, repair the exact stale proof, stable-channel, roadmap, or documentation marker listed in `errors`. Do not rerun live proof only to mask stale committed handoff metadata.
