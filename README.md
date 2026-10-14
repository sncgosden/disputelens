# DisputeLens: Verifiable Chargeback Guidance

A RAG portfolio product for small merchants who need to understand a dispute request, find applicable guidance and verify each answer against its source. The product covers shops, subscriptions, travel and services. Product scope, decision rules and trade-offs are the author's; implementation and source review were done with AI assistance (see How this was built).

## The short version

**Problem.** A merchant asks a dispute question and gets an answer that cites a real passage but states a rule for a different reason code, program or subtype. That is worse than no answer, because the merchant cannot see the mismatch.

**What I built.** A retrieval pipeline over the Visa and Mastercard guides and four payment providers, grounded answers with checked citations, and a scope control that sits outside the model after a prompt-only version failed.

**What I found.**
- Valid citations did not prevent wrong-scope answers: a source-based review of seven priority cases found three problems that passed the citation check.
- A word-overlap fix for needless clarifications passed its first test, then failed an attack set I wrote against it (8 of 12 questions slipped through). I rejected it.
- A local-embedding replacement passed its thresholds only narrowly and did not rescue the case that started the work.
- On 12 fresh Mastercard questions the scope gate changed 9 of 12 answers. On my own ratings 19 of 20 decided flags were needless. The open question is whether withholding is the right response at all; I propose disclosing scope beside each claim and testing it with merchants.

**What is not established.** Every label and review so far is mine or AI-assisted, not independent. Sample sizes are 12 to 45. Independent labelling is the next step.

**How I worked.** Each experiment has a protocol with thresholds written and hashed before it ran, in `eval/experiments/<name>/`, with the result and decision beside it. Failures are kept and not re-scored. Every paid run was capped in advance; spend per run is recorded in each experiment folder.

## How this was built

This project was built with AI coding assistance. OpenAI Codex wrote most of the implementation and did the source checks on the evaluation questions; Claude drafted the synthetic questions and is the answer model under test. The author set the product scope, wrote the decision rules and thresholds before each experiment ran, chose what to adopt or reject, and approved every paid model call. Where an AI assisted a review, the files say so, and no label in this repository is described as independent unless it is.

## Implemented as of 6 October 2026

- Reusable LM Studio and Claude clients. Qwen 4B, Nomic embeddings and Claude connection tests passed.
- Official-source snapshots with URLs, retrieval dates, edition metadata and SHA-256 fingerprints.
- All 67 pages of Visa's June 2024 merchant guide and all 1,153 pages of Mastercard's 13 May 2025 guide.
- Stripe dispute responses, Adyen dispute flow and Visa workflows, Square UK disputes, and PayPal UK Seller Protection.
- Six separate fictional policies for controlled version, ambiguity and conflict tests. Superseded sources remain identifiable.
- PDF, HTML and Markdown extraction, common document records, headings and page locators. PDF layout spacing and table-like blocks are retained; sampled pages have been checked visually.
- 6,667 evidence blocks. Two heading-aware chunk layouts: 1,818 chunks at 400 words/40-word overlap and 2,900 at 250/40, retaining all evidence with parent and neighbour links.
- Sixty synthetic questions drafted with Claude and source-checked with Codex: 45 development and 15 reserved holdout. Both layouts contain every referenced gold passage.
- Executable applicability checks for provider, scheme, region, real/fixture separation and superseded policies.

The larger layout still contains 44 intact chunks over its word target. Token-capacity checks and any safe splitting are required before embedding; truncating them silently would lose policy conditions. Whole-guide ingestion is complete, while comprehensive PDF table reconstruction is not claimed.

## Evaluation and provenance

Active cases live in `eval/expanded/`. Fifty-four cases use real policy and six use controlled fixtures. Split membership was assigned before drafting. Gold facts were checked against source passages by an AI assistant (Codex) under the author's direction. This is not independently human-labelled data.

`source-review.json` logs factual corrections and split hashes. `claude-drafting-usage.json` records eight paid drafting calls, including two discarded source-correction batches, costing approximately **$0.66** at checked Sonnet 5.5 rates. Original drafts and API responses are kept locally; raw responses are ignored by Git.

The original 10/5 case set and small-corpus generated files are preserved as baseline history. Future experiments must use the expanded corpus and 45/15 files consistently. Gold-text-to-chunk mapping checks preservation; it is not a retrieval score.


**Reproduce (offline, no model calls).**

```
python -m pytest -q --ignore=tests/test_expansion.py
python -m disputelens.scope_detector --version 2
python -m disputelens.scope_gate --version 2
python -m disputelens.scope_gate --version 4
python -m disputelens.exception_fetch_v2
python -m disputelens.quote_match
python -m disputelens.scope_detector_v3 --nearmiss
python -m disputelens.holdout_final --stage check
```


## Local project layout

- `data/source-manifest.json`: source metadata and reproducible paths.
- `data/expansion-sources.json`: official additional-source selection.
- `data/raw/`: downloaded snapshots and fingerprint receipts, local only.
- `data/parsed-expanded/`, `data/normalized-expanded/`, `data/chunks-expanded/`: active generated corpus, local only.
- `eval/expanded/`: questions, source review, usage and completion receipt.
- `src/disputelens/`: ingestion, chunking, clients, applicability and validation modules.
- `tests/`: targeted client, chunking and expansion checks.
- `docs/project-scope.md`: product plan and measurement gates.
- `eval/experiments/`: one folder per experiment (protocol, result, decision).
- `eval/stress/`: labelled detector stress sets.
