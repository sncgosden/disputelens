# Exception fetch v2 — result and decision (8 October 2026)

Protocol (fixed before the run, sha256 ecbb0a1aaaffab0cc20f80418e93a8684de569350d0d53fa93f41d6328469654) applied unchanged. Offline; development cases only; no model calls; holdout not read. v1 is left as recorded.

## Result: all six thresholds pass (T1–T6)

- Relatedness is now measurable from the publisher's section hierarchy (v1: 0 for every pair). The Listing sentence ranks first for E23 S007 and E15 S039 and names "list".
- Every fetch is the sentence only: 48 words (v1 window: 129). One candidate per passage; the 4 non-applicable passages are not searched.
- Every returned candidate is labelled "same section, different step" (shared depth 3: it lives under *No Cardholder Authorization*, Issuer Chargeback; the passages sit under Pre-arbitration or Change of Reason Code) and marked "possibly related, scope not confirmed". Nothing is labelled resolved.
- Eviction cost of a 100-word reserved clarification budget, never touching a passage the saved answer cites: E13 headroom 232, evict 0; E23 headroom 92, evict 8 words (one uncited passage, S046, 233 words); E15 headroom 22, evict 78 words (one uncited passage, S085, 180 words).

## What it does not show

1. The hierarchy gives the same label (same section, different step) for the passages where the sentence is the right referent (E23, E15) and for those where it is unconfirmed (E13 compelling evidence, E23 S024). It measures reach, not governance. Governance remains a source-review question; the fetch must surface the sentence as "possibly related", never as a resolution.
2. The pass is cheap to state and cheap to over-read: thresholds were designed after reading E23, E15 and fetch v1, tuned on 10 passages from one guide. The holdout is the independent test.
3. Evicting an uncited passage is not free of risk. S085 (E15) is in the same reason-code section and mentions the CAT 2 branch; it was uncited, not irrelevant. A selection rule for what to evict is a product decision, not solved here.
4. A bug found while running: the first eviction pass took the smallest passages first and evicted four passages for 8 words. The protocol says "smallest sufficient set", so I corrected the ordering to fewest passages (largest uncited first) and added a test. Results above are from the corrected code; the protocol is unchanged.

## Decision

Accept v2 as advisory only. Next: wire nothing into retrieval or generation. Treat the one-sentence fetch plus a 100-word reserve as the candidate design for flagged answers, and test it on the holdout only at the final evaluation. A 5-call regeneration test needs new bounded authorisation.
