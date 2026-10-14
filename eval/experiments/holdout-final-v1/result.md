# Holdout final v1 — result (8 October 2026)

Protocol sha256 a5db01e43953f6c1d4a77706021a809aa0c08fa2181f58cb638aaa9e98cd495e, frozen-file hashes matched at run time, preconditions recorded from Sebastian's "ok go". **The holdout is now spent.** Outputs: data/indexes/holdout-final/a5db01e43953f6c1d4a77706021a809a/ (identity, retrieval, packs, answers, arms, reports). Holdout file sha256 9f653c7b58565f679d4f18ca54bf843278685358847f8c48eff98dfc83d73ae0.

## What ran

Retrieval and context building on all 15 cases; 15 Claude Sonnet 5.5 calls, no retries (reserved maximum 1.6610 USD, actual 0.4430 USD, within the 2.00 cap). Latency median 3.4 s, p90 (nearest rank) 4.6 s over n=15. Local models not run, as declared.

## Thresholds

| | Result |
|---|---|
| P4 structurally valid answers (at least 12 of 15) | pass: 14 of 15. E56 failed on malformed JSON (a stray `}` inside the citations list), unrelated to scope |
| P1 zero wrong-scope claims left as unconditional instructions after arm B | pass: 0 of 14 valid answers, by my assisted review. See "What this does not show" |
| P2 arm B changes at most 2 answers that have no scope problem | pass: 1 (E16) |
| P3 zero exempted claims in arm C that depend on unestablished scope | pass: 0 exempted; arm C equalled arm B in all 14 |

## Arms

Arm A: 14 answers as generated. Arm B and C: 13 unchanged, 1 fail-closed (E16, 106 words withheld). The invariance exemption never fired.

## E16 is a false positive

The question describes the exact subtype (colour/size not as described, return policy not honoured) and the answer applies the matching "Goods or Services Were Either Not as Described or Defective" section. The detector flagged the family heading's codes (4853/53/4850/4854) because the question never prints the heading in words ("not as described" is not the whole title) and names no code. This is the same family-heading weakness that produced the E14 false flag in development, which v2 only partly fixed (it needs the question to contain the whole heading). Under arm B a merchant would have been asked for a reason code they did not need to supply. Per the no-tuning rule I am not changing the detector against this case; a fix is a new version tested on new cases.

## What this does not show

1. **Detector recall was not tested.** By my reading none of the 14 valid answers contains a wrong-scope claim. Only 3 of 15 cases are Mastercard (E16, E20, E24) and the other 12 come from Visa, Adyen, Square, PayPal, Stripe or fictional fixtures whose headings carry no reason codes, where the detector has nothing to read. So P1 and P3 passed with no true positive to catch. The holdout confirms the gate does not harm clean answers (13 of 14 untouched) and shows one false positive; it does not show the gate catches errors on unseen data.
2. The scope detector reads Mastercard heading structure only; other sources are not covered by it at all.
3. Review was assisted by me, one pass, not independent. I read answers against the cited headings and against the holdout gold claims; I did not re-verify every quotation's meaning.
4. 15 cases, one generation each: counts, not rates.

## Reported (P5, not thresholded)

- Completeness against holdout gold claims (assisted): 13 of 14 valid answers cover every gold claim. E16 covers 2 of 3 (it omits the requirement that the email come directly from the cardholder, the same sentence E17's wrong-ID citation tried to quote). E56 has no valid answer. E60 (not in sources) correctly returns insufficient_evidence.
- Retrieval over 14 cases with gold (E60 has none): passage recall@5 0.929, recall@20 1.000, NDCG@5 0.849, NDCG@20 0.867; one miss at 5 (E24, found by rank 20). Development: recall@5 86.4%, @20 97.8%. Reported separately, not pooled.
- Tolerant quote matcher: not needed for any holdout answer (no hyphen failure); E56's failure is a JSON syntax error it would not fix.

## Decision

1. The gate is safe on clean answers and costs one needless clarification on a family-heading case. Its safety value remains unproven on unseen wrong-scope data because the holdout did not contain any.
2. Keep gate v2 as the default control; do not adopt the invariance exemption (never exercised).
3. Highest-value follow-ups, all on new data, not this holdout: (a) a detector version that reads the matched subtype section, not just the family heading, tested on new Mastercard cases; (b) new Mastercard stress cases that include genuine unscoped questions, since the holdout lacked them; (c) JSON repair or a structured-output mode for the E56 failure class; (d) an independent reviewer.
4. The holdout cannot be reused to validate any change.
