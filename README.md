# DisputeLens: Verifiable Chargeback Guidance

A RAG portfolio product for small merchants who need to understand a dispute request, find applicable guidance and verify each answer against its source. The product covers shops, subscriptions, travel and services. Product scope, decision rules and trade-offs are the author's; implementation and source review were done with AI assistance (see How this was built).

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

## Status as of 8 October 2026

Retrieval, context construction, grounded generation, a development evaluation and a one-shot holdout are complete. Everything below is reproducible from saved artefacts; each experiment has a protocol written before it ran in `eval/experiments/<name>/protocol.json`, with results and a decision note beside it. Negative results are kept.

**Pipeline.** Heading-aware chunks (400 words, 40 overlap), Nomic embeddings in a local Qdrant index, section-scoped hybrid retrieval (vector plus BM25, reciprocal rank fusion), a frozen 6,000-word context pack with citation labels, and a grounded JSON answer that must cite pack labels with exact quotations. Answers are checked structurally (labels exist, quotes match the source text); that check does not establish that a claim is true or that the cited rule applies.

**Retrieval (development, 45 cases).** Passage recall@5 86.4 percent, recall@20 97.8 percent. Holdout (14 cases with gold): recall@5 0.929, recall@20 1.000, NDCG@5 0.849. Reported separately, not pooled. Reranking with a local model was evaluated and rejected.

**Generation.** Hosted Claude Sonnet 5.5, 45 development answers: 40 structurally valid, about $0.03 each, about 3.6 seconds. Local Qwen 4B produced 6 valid answers in 12 attempts at about 280 seconds each; Qwen 9B timed out. Neither exposes a way to switch off hidden reasoning. Local models were therefore not run on the holdout.

**What the review found.** A source-based, assistant-assisted review (not independent) of seven priority development cases found three that meet the bar, two where a rule for a reason-code subtype was applied without the question establishing that subtype (E13, E22), one where an exception was broadened and conditions omitted (E23), and one honest partial answer caused by a retrieval gap (E18). Passing the structural citation check did not prevent these.

**Controls built on that finding (all offline, all with declared thresholds).**

- Scope gate (`scope_detector.py`, `scope_gate.py`): reads the headings of the passages an answer cites; if a cited passage belongs to a reason code or named program the question never established, the claim is prefixed "Only if your dispute is ..." or, if every claim is affected, the answer becomes a clarification question. A prompt-only version of this control failed (the model switched to other scope-bound passages and ignored the instruction), which is why the control sits outside the model.
- Invariance exemption (`scope_invariance.py`, gate version 4): when a quoted sentence appears in at least 20 sections across at least 4 reason-code families with the same following text, the claim is kept with a note instead of withheld. The E22 refund rule appears identically in 36 of 36 second-presentment sections. Candidate only; default stays fail-closed.
- Exception fetch (`exception_fetch_v2.py`): finds the requirement a list-wide exception refers to and costs it in context words. Advisory; hierarchy proximity does not prove it governs the exception.
- Tolerant quote match (`quote_match.py`): ignores whitespace after a hyphen caused by PDF layout; six mutation controls still fail. Not applied to the production validator.
- Detector v3 (`scope_detector_v3.py`): a word-overlap rule to reduce needless clarifications was rejected after near-miss questions slipped through (8 of 12). v2 remains the default.

**Holdout (15 cases, spent).** 14 of 15 answers structurally valid (one malformed JSON); the gate left 13 of 14 unchanged and failed closed on one case, which was a false positive; no wrong-scope claim was found among the 14 by assisted review. Only 3 of 15 holdout cases are Mastercard, the only source whose heading structure the detector reads, so the holdout did not test whether the gate catches real scope errors. Cost $0.44. Details: `eval/experiments/holdout-final-v1/result.md`.

**Fresh Mastercard set (9 October 2026).** Twelve new Mastercard questions, written before retrieval, 12 calls, $0.55 of a $1.00 cap, no retries (`eval/experiments/mastercard-fresh-v1/`). All 12 answers were structurally valid. Gate v2 changed 9 of 12 answers (8 clarification questions, 1 conditional); the semantic detector flagged the same 25 of 28 claims as v2. The claim ratings in `labels-assisted.json` are the author's and assisted, not independent, so no detector decision is drawn; the protocol's decision rule needs an independent labeller (`rating-packet.md`, `labels.template.json`). In those ratings 19 of 20 decided flags were needless, which points at the response (withholding) and not only the threshold. Disclosing scope beside each claim is untested.

**Known limits.** One guide dominates the scope work; labels and reviews are assistant-assisted, not independent; sentence-level repetition is evidence, not proof, that a rule is identical across sections; exception binding and answer completeness are not controlled; sample sizes are 15 to 45 cases.

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

Retrieval and generation commands need LM Studio with the Nomic embedding model, the local Qdrant index and, for Claude, `CLAUDE_MODEL` and `ANTHROPIC_API_KEY` in the ignored `.env`. `tests/test_expansion.py` reads the holdout and is excluded from routine runs.

Provider applicability and private tenant authorization are separate. A Stripe merchant must not receive Adyen workflow rules. Shared scheme guidance requires a known matching scheme; regional qualifications stay attached. Differences across providers are not automatically contradictions. The planned tenant tests use trusted account identity and separate private fixtures.

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

Credentials, downloaded source originals, indexes and local planning files are excluded from Git.

LM Studio runs inference on the laptop. GitHub hosts the code, not a running model server.
