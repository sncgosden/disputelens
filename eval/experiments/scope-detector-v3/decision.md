# Scope detector v3 — result and decision (8 October 2026)

Protocol (declared after the holdout exposed E16 and after the stress-set labels were hashed, before any detector ran on the stress set; sha256 aeb04bde6897d8a0403a5bb5f980f1573550f41b73222d23592dc54f2ded57b2) applied unchanged. Stress set sha256 7538ab1d7cb6d98f39024516de5abbbc4b73d16c1e15396bc598ae956a79f527. Offline; no model call; the spent holdout was not used for validation. Separate module `scope_detector_v3.py`; frozen `scope_detector.py` untouched.

## Result: T1 to T5 pass

- T1: v3 flags 12 of 12 unscoped rows (v2: 12).
- T2: v3 falsely flags 2 of 12 scoped rows (S07 digital-goods under 25, S08 travel cancelled-and-not-refunded), at the limit of the threshold.
- T3: v2 falsely flagged 7 of 12 scoped rows; v3 cuts that to 2.
- T4: on the 40 valid development answers v3 flags exactly the passages v2 does: E13 (S002, S019) and E22 (S043, S044, S048, S049); nothing else changes.
- T5: five unit tests pass, including that describing one subtype never clears another subtype's codes.

## What this does and does not show

1. The real finding is about v2: when a question describes the subtype in ordinary words, v2 flagged 7 of 12 (58 percent) as scope-unestablished. That over-refusal rate would have bitten in production far more often than the holdout's single E16 suggests.
2. T1 is a weak test. Every unscoped row is also flagged by v2 and would be flagged by a detector that flags everything; the information is in T2 and T3. The unscoped rows contain no tricky cases (a generic question that happens to share a word with a subtype); a harder set is needed before claiming v3 does not under-flag.
3. Labels and questions are mine, written after I had seen E16; 24 rows; word overlap at 50 percent is an arbitrary proxy for "the question identifies this subtype". The 2 remaining false flags show the proxy misses when the title is mostly numbers or terms the question paraphrases ("flight booking never refunded" for "Travel/Entertainment Services Cancelled/Returned and a Refund was Not Processed").
4. Detector-level only: the gate is not rewired, so no end-to-end claim.

## Decision

Adopt v3 as the candidate detector for the next evaluation, behind gate v2 wording. Not yet wired into scope_gate. Required before any adoption claim: a harder unscoped set (near-miss questions), an independent labeller, and a fresh Mastercard evaluation set with real model answers.

## Known case (reported, not validation)

E16, the holdout false positive: its cited passage S002 is flagged by v2 (4850, 4853, 4854) and cleared by v3. The rule was designed after seeing E16, so this shows the fix does what it was built to do, not that it generalises.

## Superseded (same day)

The near-miss attack (eval/experiments/scope-detector-v3-nearmiss) found that v3 clears 8 of 12 near-miss questions. The "adopt v3 as the candidate detector" decision above is withdrawn; v2 remains the default. The stress-set results above stand as measured.
