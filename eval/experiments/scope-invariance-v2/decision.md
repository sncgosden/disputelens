# Scope invariance v2 — result and decision (8 October 2026)

Protocol (declared after reading v1's results, before any v2 code, sha256 2df6360772335716240a524e9d9be25cb70bfdc8fce00e1c172fc07f5306446e) applied unchanged. Offline; no model call; holdout not read. Passed first run. Not independent; J1 and J2 are regression checks on cases I had already read.

## Result: J1 to J4 pass

- J1: E22 baseline claims 1 to 3 (refund-resolves rule, two exceptions, documentation requirement) are claim-invariant: 36 to 38 sections, 4 families, following text identical in 92 to 100 percent of sections. Claim 4 (definition of refund) also passes (reported).
- J2: E13 claims on S002 and S019 are not claim-invariant (their substantive quotes match 1 section each) and E13 under gate v4 equals gate v2 byte for byte.
- J3 (non-vacuity, the least circular test): across all Chapter 2 text there are 83 repeated sentences (12 or more words, 20 or more sections, 4 or more families). The context-stability check accepts 62 and rejects 21, so it discriminates both ways. Examples it rejects: "The Central Site Business Date of the disputed transaction is counted as day zero." and "The chargeback was processed past the time frame specified for the chargeback." (the same sentence is followed by different conditions in different sections).
- J4: the other 38 answers are byte-identical, outputs validate, deterministic.

## Reported (J5)

- The refund-rule sentence is followed by the same 25 words in all 36 sections that contain it ("Upon completion of all of the chargeback cycles, … Mastercard will likely rule in favor of the acquirer."). The 2 refund-headed sections that lack it are both Issuer Submission of a Pre-arbitration Case sections, a different step. So the rule holds in every "Acquirer Second Presentment / Refund previously issued" section: 36 of 36. The failed regeneration's remark that Addendum Dispute has different consequences is not supported by this window; it may still differ elsewhere in that section.
- Words kept that gate v2 withheld: E22 baseline 188 (all four claims kept, with the note); E22 regeneration attempt 117 (3 of 4 claims; claim 4 stays conditional because its MoneySend quote matches only 3 sections).

## Honest limits

A stable 25-word window is not proof the whole rule is the same. All five thresholds (20 sections, 4 families, 75 percent, 8 words, 25 words) are mine. Passing J1 and J2 is partly expected because they were designed after the cases were read. Only J3 and the holdout say anything about generalisation.

## Decision

Keep gate v2 (fail closed) as the default control. Keep gate v4 as the documented candidate exemption: it recovers the 188-word E22 answer safely on development data while E13 is unchanged. Whether it is adopted depends on the holdout and an independent reviewer, in that order. Proposed, not made: versioned E22 gold change recording the refund rule as scope-invariant across the 36 second-presentment sections.
