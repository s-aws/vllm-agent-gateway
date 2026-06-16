# Project Milestones

Status: Approved.

These milestones define the durable product checkpoints for the project objective. They are not implementation phases. A phase is a work unit; a milestone is a product state that can be tested, trusted, and used to make the next decision.

The objective is to build a local-model coding-agent harness that can take semi-well-defined natural-language software engineering requests, route them through the gateway/controller, select deterministic skills and tools without manual prompt injection, gather bounded evidence, return useful chat-visible answers, preserve safety boundaries, and produce repeatable validation proof.

The objective also includes large-context usability. The active release target is usable 384k-token projects through indexing, retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing. Work above 384k tokens, including 1M+ project usability, is paused until the 384k product target has a stable usable tester handoff and the founder explicitly approves a post-384k milestone. Raw 384k-token or larger prompts are experimental until a dedicated proof gate validates model config, vLLM settings, hardware memory, latency, and blind-baseline answer quality.

## Milestone Gates

| Milestone | Product State | Done Means | Required Proof |
| --- | --- | --- | --- |
| M1: V1 Founder Beta Closeout | Complete. Current approved read-only chat workflows are ready for broader founder testing. | Phase 199 passes and the current release candidate can be tested by a contextless founder/tester. | Phase 195-198 proof chain valid, Phase 199 closeout valid, full regression green, AnythingLLM path verified, frozen fixtures clean. |
| M2: Chat-Visible Answer Contract | Supported prompts return useful information directly in chat. | Answers are not artifact-only and preserve default and requested output formats. | Blind-baseline comparison, output-format parity, JSON/default parity, no unresolved critical or high findings. |
| M3: Workflow/Skill/Tool Selection Reliability | Natural prompts route correctly without manual skill injection. | The router selects the right workflow, skills, and tools and explains selected/rejected candidates where required. | Prompt matrix across L1/L2 families, selected/rejected skill/tool explanation, holdout reruns, route-surface proof. |
| M4: Evidence Quality And Relevance | Answers cite the right files, tests, artifacts, and limitations. | Evidence is relevant, confidence-labeled, and not padded with weak or unrelated references. | Evidence relevance scoring, source hash proof, contextless audits, local-model reruns. |
| M5: Multi-Repo Generalization | The harness works beyond the original Coinbase fixtures. | Representative prompts pass across different repository structures and languages. | Coinbase git and non-git fixtures plus at least 2-3 structurally different repos passing representative prompts. |
| M6: Large-Context Usability Baseline | 384k-token projects are usable without raw prompt stuffing. | The framework can answer useful questions over a very large corpus through context strategy. | Corpus index, retrieval-first answers, chunked investigation, artifact paging, answer-quality proof over a fixture that is at least 384k estimated tokens. |
| M7: Context Ceiling Benchmark | The real local-model context limits are known. | The project records measured prompt limits, latency, memory, and failure modes. | Benchmarks at 32K, 64K, 128K, and 256K with quality scores and failure classification. |
| M8: Context Strategy Router | The controller chooses the right context strategy. | Requests route to direct context, retrieval, chunking, summarization, artifact paging, or refusal based on size and task. | Deterministic routing tests for small, medium, huge, ambiguous, and unsupported context requests. |
| M9: Founder Feedback Repair Loop | Field feedback reliably becomes accepted, rejected, deferred, or blocking work. | Founder notes and trial misses become traceable decisions with owner paths and rerun gates. | Feedback intake reports, rejected-note proof, rerun gates, no untracked advisory drift. |
| M10: Safe Implementation Prep | The agent can create bounded implementation plans without protected-source mutation. | Plans identify exact scope, operations, approval gates, and verification before mutation. | Approval gates, disposable-copy proof, exact operation validation, rollback proof. |
| M11: Controlled Apply Pilot | Small approved changes can be applied safely outside protected fixtures. | The framework can mutate permitted targets with diff proof and rollback. | Mutation sandbox, structured diff proof, tests, rollback, no parallel implementation paths. |
| M12: Skill Library Scaling Gate | New small skills can be admitted, tested, versioned, and retired without destabilizing routing. | Skill growth remains deterministic and governed. | Skill authoring pipeline, registry readiness, eval gates, conflict detection, prompt coverage map. |
| M13: Runtime Reliability And Recovery | Restarted vLLM, gateway, controller, and AnythingLLM recover predictably. | A tester can restart the stack and continue normal chat workflow testing. | Post-restart readiness, health drift, greeting path, AnythingLLM session isolation, port checks. |
| M14: Release Packaging And Onboarding | A contextless tester can install, start, test, and provide feedback without session history. | The project can be handed to a new tester without private chat context. | Getting-started docs, doctor command, release notes, setup validation, clean-clone proof. |
| M15: Deferred Post-384k Expansion Gate | Post-384k project usability or raw long-context prompting is either separately approved for future work or explicitly rejected as unsupported for the current release. | The project has an evidence-backed decision before expanding beyond the 384k-token project target, after the 384k product target has a stable usable tester handoff. | Founder approval, model/vLLM context report, memory/latency benchmark, smoke prompt, blind-baseline quality pass, and non-regression against the 384k objective. |
| M16: Corpus And Index Safety Governance | Large-corpus indexing and retrieval do not leak ignored, private, secret-like, stale, or unapproved content into chat or artifacts. | Any durable corpus index enforces ignore rules, allowed roots, secret-like content handling, source freshness, retention/deletion, and proof-artifact boundaries before retrieval is connected to chat. | Index safety policy, negative controls for ignored/private/secret-like files, stale-index rejection, source-hash proof, artifact retention/deletion proof, and no sensitive values in chat-visible output. |

## Critical Path

The primary product path is:

```text
M1 -> M2 -> M3 -> M4 -> M5 -> M16 -> M6 -> M8 -> M9 -> M12 -> M14
```

M7 supports M6 and M8 by measuring the real context ceiling. M16 is required before any durable context-index or retrieval-backed chat closeout because indexing creates persistent derived repository content. M10 and M11 are implementation-safety milestones that should not outrank Priority 0 chat quality unless the roadmap explicitly returns to safe mutation. M13 supports every runtime-facing milestone.

M15 is deferred and must not block the main objective. The current product value is making 384k-token projects usable through governed context strategy, not proving that every request should be sent as a raw long-context prompt. Do not plan or implement post-384k expansion work until the 384k product target has a stable usable tester handoff and the founder explicitly approves a post-384k milestone.

## Added Milestone Rationale

M16 was added because M6/M8 large-context work requires durable indexing and retrieval. That creates persistent derived copies of repository content and can leak ignored files, private paths, secret-like strings, stale chunks, or unapproved roots into chat and artifacts if governance is only handled inside implementation details. M16 is therefore a prerequisite safety milestone for context-index and retrieval-backed chat work, not a separate product expansion.

## Initial Roadmap Mapping

The first proposed milestone-aligned phase set is:

| Phase | Milestone | Purpose |
| --- | --- | --- |
| Phase 199 | M1 | Complete. Closed the V1 founder beta release package from the Phase 195-198 proof chain. |
| Phase 200 | M2 | Complete. Inventoried the chat-visible answer contract for every supported Priority 0 workflow. |
| Phase 201 | M2 | Complete. Added deterministic fail-closed validation for the chat-visible answer contract. |
| Phase 202 | M2 | Complete. Refreshed live default/JSON/AnythingLLM proof for answer usefulness and marked M2 ready. |
| Phase 203 | M3 | Complete. Refreshed the workflow, skill, and tool selection matrix and queued Phase 204 explainability gaps. |
| Phase 204 | M3 | Approved. Prove natural prompts work without manual skill injection and explain selection. |
| Phase 205 | M3 | Approved. Replay route-stability holdouts after selection hardening. |
| Phase 206 | M4 | Approved. Build the evidence relevance audit pack with blind baselines and scoring rules. |
| Phase 207 | M4 | Approved. Add deterministic evidence ranking and source hash gates. |
| Phase 208 | M4 | Approved. Rerun evidence-quality prompts live through gateway and AnythingLLM with holdouts. |
| Phase 209 | M5 | Complete. Selected `s-aws/staterail` as the first non-Coinbase fixture and created the governed blind-baseline prompt pack without committing or pushing to that repository. |
| Phase 210 | M5 | Complete. Ran multi-repo baseline comparison without repairs and classified the accepted `target_root_not_allowed` runtime-surface gap for `s-aws/staterail`. |
| Phase 211 | M5 | Complete. Repaired accepted multi-repo generalization blockers through the existing single paths, including startup allowed-root coverage, generalized natural query expansion, related-test discovery term selection, and code-investigation test-reference accounting; live proof passed with zero gaps and full regression passed without committing or pushing to `s-aws/staterail`. |
| Phase 212 | M5 | Complete. Reran multi-repo live proof through gateway and AnythingLLM across Staterail and Coinbase holdouts, repaired the discovered configuration-identifier route gap, and passed final live proof with zero gaps plus full regression. |
| Phase 213 | M5 | Complete. Closed M5 for the current selected repository set with accepted findings fixed, known limits recorded, and Phase 214 approved as the next large-context preparation phase. |
| Phase 214 | M6/M7 | Complete. Inventoried a deterministic local large-corpus fixture and real context-budget constraints with `248` files, `1286080` estimated tokens, current model/router limits, raw 1M prompt support explicitly unproven, and `phase215_ready=true`. |
| Phase 215 | M6/M8 | Complete. Designed and validated the retrieval-first context strategy contract with six enum-backed strategies, routing inputs, failure behaviors, negative controls, out-of-scope boundaries, and `phase216_ready=true`. |
| Phase 216 | M16 | Complete. Defined and validated corpus/index safety governance with 13 negative controls, sanitized reports, no source-text retention, no rejected-content leakage, and `phase217_ready=true`. |
| Phase 217 | M6/M16 | Complete. Added a metadata-first local context index prototype with Phase 216 safety enforcement, `241` indexed files, `457` chunks, query smoke proof, no source-text retention, and `phase218_ready=true`. |
| Phase 218 | M6 | Complete. Connected retrieval-backed evidence to chat-visible answers through the existing workflow-router path with source refs, hash proof, limitations, holdouts, and negative controls. |
| Phase 219 | M6/M8 | Complete. Added artifact paging and long-answer usability validation with answer-first chat, JSON/default parity, source continuity, fail-closed controls, and full regression proof. |
| Phase 220 | M8 | Complete. Implemented deterministic context strategy routing with all six strategies covered, chat-visible strategy metadata and rationale, fail-closed negative controls, live gateway proof, AnythingLLM proof, small-repo non-regression, contextless-audit blocker repair, and full regression proof. |
| Phase 221 | M6/M8 | Complete. Closed the first large-context usability live proof through gateway and AnythingLLM with baseline and holdout prompts, source-hash and paging proof, small-repo non-regression, repaired holdout routing gaps, and full regression proof. |
| Phase 222 | M6/M8 | Complete. Defined the executable chunked-investigation contract with strategy-only entry, bounded decomposition, metadata-first retrieval reuse, canonical report fields, claim mapping, source/hash proof, negative controls, gateway/AnythingLLM validation surfaces, and Phase 223 readiness. |
| Phase 223 | M6/M8 | Complete. Implemented the smallest read-only chunked-investigation executor inside the existing large-context workflow-router path with answer-first chat, Phase 222-compliant artifacts, gateway proof, AnythingLLM proof, small-repo non-regression, docs proof, and full regression proof. |
| Phase 224 | M6/M8 | Complete. Improved chunked-investigation evidence diversity and claim readability so live answers cite stage-diverse source and verification evidence while preserving the existing retrieval/index/router path, safety boundaries, gateway proof, AnythingLLM proof, small-repo non-regression, and full regression proof. |
| Phase 225 | M6/M8 | Complete. Improved chunked-investigation answer synthesis so selected stage evidence renders as a bounded flow narrative with scope limits, evidence metadata, unverified edges, blind-baseline proof, gateway/AnythingLLM proof, small-repo non-regression, docs proof, and full regression proof. |
| Phase 226 | M6/M8 | Complete. Closed the current large-context strategy matrix with fresh live proof for retrieval, artifact paging, summarization, refusal, chunked investigation, direct-context small-repo non-regression, gateway/AnythingLLM surfaces, and M6/M8 release-usability. |
| Phase 227 | M9 | Complete. Rebaseline founder feedback intake against current large-context and chunked-investigation chat behavior with deterministic baseline, holdout, repair, rejected, advisory, and deferred classification, live gateway/AnythingLLM proof, no mutation, and full regression proof. |
| Phase 228 | M9 | Complete. Added rerun proof gates for accepted feedback repairs so target prompts, holdouts, blind baseline, fixture mutation checks, rejected explanations, and artifact traceability are required before closure. |
| Phase 229 | M12 | Complete. Inventoried current skill/tool coverage after M6/M8/M9, confirmed no active new runtime skill gap, kept advanced refactor deferred, and selected `FX-001` as the Phase 230 fixture/eval pilot candidate. |
| Phase 230 | M12 | Complete. Admitted `FX-001` through the existing skill/eval path with endpoint and schema lookup prompt coverage, schema-symbol artifact proof, owning skill eval-contract links, gateway and AnythingLLM live validation, admission validator proof, and full regression proof. |
| Phase 231 | M13 | Complete. Rebaselined runtime restart and recovery reliability for vLLM, gateway/proxies, controller, role ports, workflow routing, AnythingLLM, small-repo prompts, and large-context prompts. |
| Phase 232 | M14 | Complete. Refreshed onboarding and release handoff docs, added a stale-doc freshness gate, and incorporated contextless audit findings. |
| Phase 233 | M14 | Complete. Passed a contextless handoff dry run through setup validation, representative prompts, feedback capture, current proof gates, and AnythingLLM/gateway live evidence. |
| Phase 234 | M14 | Complete. Produced a disposable clean-snapshot release handoff proof with managed stack restarted from the snapshot, live AnythingLLM onboarding, fixture mutation proof, and full regression. |
| Phase 235 | M14 | Complete. Made model-capability routing clone-safe by moving the active routing profile dependency out of `runtime-state/` and proving clean handoff with `runtime_seed_count=0`. |
| Phase 236 | M14 | Complete. Proved the release candidate can be committed, pushed, cloned, started, and tested from a remote branch without active-workspace state. |
| Phase 237 | M2/M13/M14 | Complete. Rebaselined AnythingLLM fresh-chat responsiveness, including the user-reported `hi` no-response failure mode, active-stack UI proof, API proof, target settings, coding prompt proof, and fixture safety. |
| Phase 238 | M14/M9 | Complete. Prepared the release-candidate branch for contextless review with proof links, known limits, branch hygiene, generated markdown packet, and no draft PR creation. |
| Phase 239 | M2/M3/M4/M14 | Complete. Replayed Priority 0 chat-quality prompts from the remote-clone path with blind-baseline comparison, repaired chat-visible endpoint/schema evidence gaps, and passed gateway plus AnythingLLM replay with 14/14 cases and no high/critical findings. |
| Phase 240 | M5/M14 | Complete. Replayed non-Coinbase generalization from the remote-clone path across Python-service, Staterail, and Coinbase holdout prompts with gateway and AnythingLLM proof, no response gaps, and no fixture mutation. |
| Phase 241 | M6/M8/M16/M14 | Complete. Replayed large-context strategy and safety behavior from the release-candidate path with generated-corpus/index bootstrap, gateway and AnythingLLM proof, all required strategies covered, no raw 1M claim, metadata-only source retention, and no generated-corpus mutation. |
| Phase 242 | M2/M3/M4/M9/M12 | Complete. Promoted release-candidate prompt coverage into the governed baseline corpus with 20 cases, 8 holdouts, 40 gateway/AnythingLLM response summaries, Phase 239/240/241 evidence refs, focused gates, docs-index proof, and full regression. |
| Phase 243 | M9/M14 | Complete. Proved tester feedback from the release-candidate clone path becomes traceable work, including positive gateway feedback, AnythingLLM defect feedback, governed decisions, prompt hashes, route/output artifact hashes, ignored runtime-state proof, focused regression, and full regression. Caveat: model port `8000` was unavailable, so Phase 244 must include restored full-port health before a ship decision. |
| Phase 244 | M1/M14 | Complete. Aggregated the release-candidate proof chain into deterministic decision `hold` because required runtime-health probes failed while vLLM/model-backed endpoints were unavailable. |
| Phase 245 | M13/M14 | Complete. Restored release-candidate runtime health across vLLM, gateway, controller, workflow-router gateway, role ports, AnythingLLM target, and protected fixture checks. |
| Phase 246 | M1/M14 | Complete. Reran the release-candidate decision gate after runtime health was restored and reached `ship`. |
| Phase 247 | M1/M14 | Complete. Packaged the Phase 246 ship decision into committed release proof metadata, stable-channel readiness, tester docs, and a deterministic handoff validator. |
| Phase 248 | M14 | Complete. Replayed the committed ship handoff package from the remote clone at commit `138afa3` with static handoff, docs-index, and stable-channel proof. |
| Phase 249 | M13/M14 | Complete. Restored Bash/WSL command execution, captured the Windows-to-WSL localhost forwarding workaround, refreshed runtime health, and reran release decision proof. |
| Phase 250 | M14 | Complete. Replayed the pushed Phase 249 handoff state from a fresh remote clone with static handoff, docs-index, and stable-channel proof. |
| Phase 251 | M6/M7/M8/M14 | Complete. Rebaselined the current large-context objective to 384k-token project usability and added a drift gate so post-384k expansion work cannot begin before the current target has a stable usable tester handoff and explicit approval. |
| Phase 252 | M14/M6 | Complete. Replayed the pushed Phase 251 384k objective rebaseline from a fresh remote clone with Phase 251, docs-index, and stable-channel proof. |
| Phase 253 | M6/M8/M13/M14 | Complete. Proved the post-rebaseline runtime still answers through gateway and AnythingLLM while refusing raw-corpus prompt stuffing and preserving both frozen Coinbase fixtures. |
| Phase 254 | M2/M13/M14 | Complete. Proved post-reboot AnythingLLM greeting/session recovery for `hi` and same-session follow-up after the 384k rebaseline. |
| Phase 255 | M2/M13/M14 | Complete. Hardened the AnythingLLM fresh-chat validator so split Bash/Windows workflow-router URLs do not falsely fail target settings checks. |
| Phase 256 | M2/M13/M14 | Complete. Replayed full AnythingLLM fresh-chat responsiveness with UI `hi`, gateway/API `hi`, coding prompt, split target settings, and fixture proof. |
| Phase 257 | M6/M14 | Complete. Updated committed stable-channel metadata so external handoff names 384k-token project usability as the current large-context target and keeps 1M+ as future expansion. |
| Phase 258 | M2/M4/M6/M8/M14/M16 | Complete. Defined the executable 384k usability acceptance contract and required fixture/index readiness plus stale-index rejection before live acceptance. |
| Phase 259 | M6/M16 | Complete. Proved the accepted 384k-plus fixture and governed index bootstrap are ready before live 384k validation. |
| Phase 260 | M6/M8/M16 | Complete. Hardened stale-index, changed-policy, changed-source, and unsafe-evidence rejection before live 384k acceptance. |
| Phase 261 | M2/M4/M6/M8/M13/M14/M16 | Complete. Passed live 384k acceptance through gateway and AnythingLLM with Phase 258/259/260 prerequisites, Phase 221 plus Phase 223 strategy coverage, split-url target settings, blind-baseline comparison, JSON/default parity, fixture proof, and zero high/critical findings. |
| Phase 262 | M2/M4/M6/M8 | Complete. No targeted answer-quality repair was required because Phase 261 passed with zero errors, zero critical/high findings, zero failed small-repo regressions, and passing JSON/default parity. |
| Phase 263 | M14/M6 | Complete. Integrated the accepted 384k tester path into root, getting-started, stable handoff, release handoff, live-acceptance, and example docs with split-url AnythingLLM guidance, expected proof fields, artifact names, and explicit post-384k boundaries. |
| Phase 264 | M14/M6/M16 | Complete. Replayed the 384k usability proof from a fresh remote clone at commit `7355639` with clone-local static gates, live gateway proof, AnythingLLM proof, runtime-state ignored, and clean source before/after. |
| Phase 265 | M1/M6/M14 | Complete. Aggregated the 384k proof chain into release-candidate decision `ship` with fresh Phase 264 clean-clone proof at commit `6dbf8d8`, zero blockers, healthy runtime probes, and `phase266_ready=true`. |
| Phase 266 | M14/M6 | Complete. Refreshed stable handoff metadata, docs, known limits, split-url guidance, release-channel proof metadata, and post-384k pause language for the accepted 384k product target. |
| Phase 267 | M14/M6 | Complete. Replayed the pushed Phase 266 stable 384k handoff from fresh WSL clone `/tmp/agentic_agents_phase267_remote_clone_a3f4486_r2` at commit `a3f4486` with docs-index, stable release-channel, ship-handoff, 384k decision, and clean source before/after proof. |
| Phase 268 | M2/M6/M13/M14 | Complete. Ran the live stable founder smoke through AnythingLLM after restarting the stack from the active workspace; setup doctor, scoped UI E2E, fresh-chat responsiveness, and 384k live acceptance all passed. |
| Phase 269 | M6/M14 | Complete. Added the 384k completion audit with requirement-to-evidence matrix, current model context boundary, durable proof links, and complete decision for the supported 384k product path. |

## Usage Rules

- New roadmap phases should map to one or more milestones.
- Phases mapped to approved milestones are automatically approved unless the roadmap entry, founder, or current session explicitly marks them as proposed, not approved, blocked, deferred, or approval-required.
- Automatic phase approval only applies inside the mapped milestone's product state, done criteria, and required proof. It does not approve new milestones, milestone changes, unrelated features, or expanded product scope.
- A milestone is complete only when its required proof exists and can be validated by a contextless agent.
- If a proposed phase does not move a milestone forward, raise the mismatch before implementation.
- Large-context work should prefer retrieval-first and evidence-selection designs for the 384k-token project target unless M15 is explicitly reapproved and passed.
