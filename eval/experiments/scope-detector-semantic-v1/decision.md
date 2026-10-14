# Semantic subtype detector: result and decision (8 October 2026)

Protocol sha256 9ad8cc52371f8e2461d0637c4b78b9a4374bae39f9fe5ca725d4b282b522833d, declared before any embedding was computed. Free, local (Nomic via LM Studio). Calibrated once on pairs.json, tested once on nearmiss.json. Offline unit tests: 6 pass in the assistant's shell; S4 also requires the run on the project machine.

## Result against thresholds

| Check | Threshold | Result |
|---|---|---|
| S1 near-miss clears | at most 3 of 12 | 1 of 12 (N12) pass |
| S2 calibration | at least 11 of 12 unscoped flagged, at most 4 of 12 scoped falsely flagged | 12 of 12, 4 of 12 pass (at the limit) |
| S3 development regression | flags only E13/E22 passages v2 flags | identical (E13: S002, S019; E22: S043, S044, S048, S049) pass |
| S4 unit tests | pass | pass |

Chosen operating point: tau 0.75, delta 0.05. Embedding model cache hash recorded in chosen.json.

## Honest reading

- It passes, but narrowly and mostly by being conservative. On the 24 calibration rows only 4 ever count as "established" (S01, S07, S10, S12); all are scoped rows, and no unscoped row does. That is the property wanted, but it is fitted to these labels.
- It cuts scoped false flags from 7 of 12 (v2) to 4 of 12, so it still over-flags a third of described-subtype questions. The gain is real and modest.
- Most scoped questions fail the margin test, not the similarity test: sibling titles under the same family sit within about 0.02 cosine of each other (S02, S06, S08, S11). Short titles embed too close together for a margin rule to separate them.
- Near-miss: N12 (surcharge) was cleared, because its question genuinely sits close to the title (cosine 0.758, margin 0.11). The label calls it unscoped; the embedding disagrees with my label. Either could be right, and that is exactly the case an independent reviewer should look at.
- S2 sits exactly at its limit (4 of 4), and the grid was chosen on the same 24 rows it is scored on. Expect optimism.

## Decision

1. Semantic detector is a candidate, not adopted. v2 stays the default scope detector until a fresh Mastercard end-to-end set shows it does not let wrong-scope claims through.
2. The next test needs new questions and new Mastercard answers (paid generation, bounded approval) and an independent label of "scoped or not". Neither can be produced by the assistant without circularity.
3. E16 under the chosen detector is reported in known-e16.json (known case, designed after seeing it; not validation) once `--stage known` has been run on the project machine.

## Addendum, 9 October 2026: E16 known case
Reported, not thresholded (known-e16.json). Under the chosen detector E16 is still flagged: the nearest title to the question is "Merchant Refund Correcting Error Resulted in Cardholder Currency Exchange Loss" (cosine 0.669, margin 0.009), not the subtype the question describes, and 0.669 is below tau 0.75. The semantic detector does not rescue the case that started this line of work, which matches the reading that it is a modest, fitted improvement and not a fix.
