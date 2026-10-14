# Exception fetch v1 — result and decision (8 October 2026)

Protocol (fixed before the run, sha256 9cd85e620d6dc03fee7f42e55b648fae4e5ebb3f3148b75a1b6d40e180fe0ea3) applied unchanged. Offline; development cases only; no model calls.

## Runs

- Run 1 failed on an implementation bug: requirement sentences wrap across lines in the chunk text and my search split line by line, so no candidate was found. Saved as `result-run1-failed-line-split-bug.json`. The bug was fixed without changing the protocol; a unit test for wrapped lines was added.
- Run 2 (the fixed code) is the recorded result.

## Result: rejected (T1 and T2 fail)

| Threshold | Result |
|---|---|
| T1: top candidate for E23 S007 and E15 S039 lies under a "No Cardholder Authorization" heading and names "list" | fail: the candidate is the right sentence, but the chunk store's heading metadata is page-header text only ("Dual Message System Chargebacks Issuer Chargeback"), so the section check cannot pass |
| T2: every fetch window at most 120 words | fail: 129 words |
| T3: not-applicable passages are not searched | pass |
| T4: other applicable passages return a candidate or "none found" | pass |

## What the failure taught

1. The whole Mastercard guide contains exactly one chunk with a requirement statement matching these exceptions: the Listing sentences in the No Cardholder Authorization section (the same text as S044). It is the correct referent for E23 and E15. Search finds it; heading overlap cannot rank anything because the chunk store carries only page-header headings (shared score 0 for every pair).
2. The same single chunk is returned for E13 S030 and E23 S024 (compelling-evidence sections). Whether that sentence governs those exceptions cannot be established from chunk text alone. Returning it as a resolution would repeat the resolver-v1 mistake. These stay "candidate, needs review".
3. Cost is real. Context headroom (6,000 minus words used) is 232 words for E13, 92 for E23, 22 for E15. The 48-word sentence alone does not fit in E15; the 129-word window fits only E13. A fetch needs a reserved budget or an eviction rule.

## Decision

Reject v1. v2 (to be declared before running) should: (a) rank relatedness with the publisher-derived section hierarchy, not chunk headings; (b) fetch only the sentence (about 50 words) and cite it; (c) define a reserved clarification budget (about 100 words) and test what it costs in evicted evidence. Until relatedness is established, show a returned sentence as "possibly related, scope not confirmed", never as a resolution.
