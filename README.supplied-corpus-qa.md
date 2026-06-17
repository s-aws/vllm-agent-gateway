# Supplied Corpus QA

Phase 280 makes supplied-corpus question answering a first-class workflow-router capability.

Use it when a user pastes structured text into chat and asks questions that must be answered only from that supplied text. The route does not require a repository `target_root`, does not inspect source files, and does not mutate anything.

## When To Use It

Use supplied-corpus QA for prompts that include:

- inline text supplied in the current chat message
- `SECTION NN -- Title` style sections or similarly clear segmentation
- explicit wording such as `Based only on the supplied corpus`
- read-only questions over the supplied facts

Supported answer behaviors include:

- cross-section synthesis
- later-fact precedence and superseded fact detection
- boundary stitching for values split across adjacent sections
- simple deterministic cost calculations
- ordered extraction
- contradiction and blocker handling

## Boundary

This is not repository investigation, file upload parsing, PDF ingestion, fine-tuning, raw 500k prompt serving, or a general RAG redesign. It is a bounded inline-corpus QA path inside the existing workflow-router gateway.

Normal coding prompts without a target path still fail closed with `missing_target_root_for_coding_request`.

## Runtime Path

Natural clients should send the prompt through the workflow-router gateway:

```text
http://127.0.0.1:8500/v1
```

Windows AnythingLLM may need the WSL network URL printed by `start-agent-prompt-proxies.sh` instead of `127.0.0.1` if Windows localhost forwarding hangs.

## Artifacts

Successful supplied-corpus QA runs write:

```text
supplied-corpus-qa-answer.txt
supplied-corpus-qa-extraction.json
```

The chat response is answer-first. Artifact links are supporting evidence, not the primary user experience.

## Validation

Static and direct-router validation:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_supplied_corpus_qa_generalization.py
```

Live workflow-router gateway validation:

```bash
python3 scripts/validate_supplied_corpus_qa_generalization.py \
  --live-gateway \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --model-base-url http://127.0.0.1:8000/v1
```

Live AnythingLLM validation:

```bash
python3 scripts/validate_supplied_corpus_qa_generalization.py \
  --live-gateway \
  --anythingllm \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace
```

The validator covers five unseen fixtures: precedence, boundary stitching, ordered facts, numeric calculation, and contradiction handling.

The original adversarial stitching fixture remains a separate hard gate:

```bash
python3 scripts/validate_adversarial_context_stitching.py --live-gateway
```

Examples: [docs/examples/supplied-corpus-qa.md](docs/examples/supplied-corpus-qa.md).
