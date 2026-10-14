# DisputeLens: Verifiable Chargeback Guidance

## Product outcome

Help a small merchant understand a dispute request, identify the applicable provider/scheme guidance and verify the answer through citations. Make missing facts, unsupported advice and unresolved conflicts visible. The terminal prototype demonstrates ingestion, retrieval diagnosis and product decisions separately from the earlier dispute-triage classification/routing project.

## Completed corpus expansion

The active manifest contains 13 documents: seven real sources and six fictional control policies. The whole Visa June 2024 guide has 67 PDF pages, rather than the previously selected four. The whole Mastercard 13 May 2025 guide has 1,153 pages. Four payment providers are represented: Stripe, Adyen (two articles), Square UK and PayPal UK.

Raw sources have URL, timestamp and fingerprint provenance. Download dates do not establish policy effective dates. Preserve transaction dates, regional exceptions, actor roles and scheme message systems when answering. A contents-page match is not sufficient evidence for a substantive rule.

The expanded extraction contains 6,667 evidence blocks, including PDF page provenance and HTML headings, lists and tables. Both 400/40 and 250/40 chunk layouts retain every block. They contain 1,818 and 2,900 chunks respectively. Parent/neighbour IDs support restoration of surrounding qualifications. Table-like PDF text stays intact with spacing, rather than inventing column relationships. Forty-four 400-word chunks exceed the target and require embedding-token checks before indexing. Selected pages were visually checked; all-page text coverage is validated, not a claim of perfect table reconstruction.

The original small generated corpus and 15 baseline questions are preserved. Expanded artifacts are separate and are the active experiment inputs.

## Evaluation design

Claude drafted 60 synthetic merchant questions from exact source excerpts. Codex checked each expected claim against the selected passage and recorded corrections. Fifty-four cases use real guidance and six use fictional controls. This is assistant-reviewed gold, with independent review still outstanding; never describe it as independently human-labelled.

Forty-five questions are development cases and 15 are reserved holdout. Every fourth case was assigned to holdout before drafting. No retrieval or answer tuning has run. Do not use holdout outcomes to select chunk size, search weights, reranker, rewrite prompt or generation model. Both chunk layouts have validated mappings for all gold evidence, including the adjacent qualifications added during source review.

Coverage includes reason codes (13.1, 4853, 4837), merchant paraphrases, duplicate charges, refunds, subscriptions, authorisation, delivery, product quality, card-present payments, digital goods, regional dates, provider fees, terminology, clarification and controlled conflicts. Natural provider differences provide wrong-provider distractors. They do not establish that applicable authoritative rules conflict. In the event of an apparent conflict, inspect scope, publication/effective dates, actor, message system and provider/merchant contract before declaring it unresolved.

Measure passage recall/precision and NDCG at five, evidence sufficiency, answer correctness, relevance, completeness, supported material claims, claim-level citation accuracy, abstention/clarification, provider leakage, stage latency and paid usage. Keep denominators and unrun/unscored counts visible. Report dev and holdout separately. Report slices by source family and exact-code/paraphrase behaviour; small slice counts cannot support strong generalisation claims.

## Implementation sequence

1. Preserve the completed ingestion, version metadata, chunking and gold review.
2. Check token capacity, oversized intact blocks and source continuation before Nomic batches. Cache embeddings by source/chunk/model/config hash and resume failures.
3. Persist vectors and evidence payloads in local Qdrant. Use common applicability guards in vector search, BM25, hybrid fusion, reranking, neighbour expansion and context.
4. Measure vector, BM25 and hybrid retrieval on all 45 dev cases. Compare 250/400 chunks without changing gold labels. Include contents pages and similar codes as natural distractors.
5. Compare hybrid with/without a local cross-encoder and one safe query rewrite. Preserve trusted provider, scheme and region outside the model. Retain negative results; complexity must improve measured outcomes.
6. Deduplicate passages, restore adjacent qualifications, prioritise evidence and respect a shared context budget. Save selected and omitted evidence with citations and stage timings.
7. Generate cited answers using Qwen 4B, Qwen 9B and Claude with identical cached contexts. Validate citation IDs and manually score actual support. All 45 dev outputs per model must be accounted for before freeze.
8. Freeze settings, evaluate the 15 holdout questions on the same three models, and score the remaining answers without retuning. A gold-context rerun diagnoses failed dev cases only and is excluded from ordinary results.
9. Demonstrate private tenant authorization with trusted identity and separate fixtures; evaluate the bounded optional second search and record a product/model decision from actual evidence.

Do not skip scoring or mark incomplete work done to meet an estimate.

## Controls and PM decisions

Public applicability filtering is implemented and tested. Private tenant isolation must be an additional independent authorization boundary, not a provider name inferred from question text. Unknown account/scheme excludes specialised sources. Superseded fixture versions must never answer as current; real snapshots must not be asserted current without evidence.

Claude drafting cost is recorded, including discarded batches. Further bulk answer calls require a visible dry-run allowance and explicit execution; no automatic paid fallback or retry. Actual local hardware/energy costs are separate from zero API charges.

The author owns the product outcome, acceptable failure behaviour, trade-offs and final model choice. Codex assisted with coding and source review. Private notes are excluded from the repository.
