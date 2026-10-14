# Scope invariance v1 — result and decision (8 October 2026)

Protocol (declared before the check was written, sha256 a97fbfad8bee7daaecf1606b009fb55ef0ba764fc869b55be4b148c92e56fc55) applied unchanged. Offline; no model call; holdout not read. Overall: **fail by the letter (I2 and I3)**; I1 and I4 pass. I do not re-score with corrected thresholds.

## What the data showed

- The refund rule is not an E22-specific passage. The sentence "the issuer must not continue the dispute for the refunded amount…" appears in 36 of 38 "Refund previously issued" sections across 4 of the Chapter 2 reason-code families, with identical wording; the documentation requirement, both exceptions and the refund definition recur in 36 to 38 sections. E22's gold passage (Stand-in/X-Code, page 85) is one arbitrary instance. A merchant who does not name a reason code gets the same rule in whichever section applies.
- I1 pass: all four E22 baseline claims are scope-invariant (36 to 38 sections, 4 families). I4 pass: the other 38 answers are byte-identical, outputs validate, deterministic, and E13 under the invariance-aware gate equals its v2 output.
- I2 fail (threshold mis-specified): I required every E13 quote to match at most 3 sections. One quote, "Supporting Documents: None.", matches 75 sections (boilerplate). The design rule is claim-level (every flagged citation must be invariant), and at claim level E13 is correct: claims 2 and 3 are not invariant because the Chargeback Reference Number quotes match 1 section each.
- I3 fail (wrong assumption): I believed the Mainland China fee-collection sentence in E22's gold paragraph was section-specific. It matches 35 sections; it is boilerplate too. So my chosen negative control was not a negative control. Real narrow quotes exist (E13's reference-number quotes: 1 section; the MoneySend refund quote: 3 sections) and the check correctly says "not invariant" for them, but I have not pre-declared them as controls, so that counts as observation, not a pass.

## Effect when applied (reported, not thresholded)

- E22 baseline: fail-closed under gate v2 (4 claims, 188 words withheld); under invariance-aware gate, all 4 claims are kept with the note "The guide gives this same wording in 36 reason-code sections; check your own reason code for additional conditions."
- E22 regeneration attempt: 3 of 4 claims kept; claim 4 stays conditional because its MoneySend quote matches only 3 sections.

## Limits that matter

Identical sentences are weak evidence that the whole rule is identical: neighbouring conditions can differ by section (the failed regeneration noted Addendum Dispute has different consequences), boilerplate sentences like "Supporting Documents: None." are invariant for no useful reason, and the thresholds (20 sections, 4 families) were chosen by me from the counts I had just seen. Not independent; holdout is the test.

## Decision

1. Keep gate v2 (fail closed) as the control. Do not adopt the invariance exemption yet: it would turn a safe refusal into a confident answer on evidence that is still sentence-level.
2. Write a v2 protocol before any further change: claim-level thresholds, controls declared before looking, an extra check that surrounding conditions do not differ (compare the following sentence set across sections), and a boilerplate filter.
3. E22 gold-scope item: reframed. The gold is an arbitrary instance of text repeated across about 36 sections, so the defect is "gold names one section for a scope-independent rule", not "gold names the wrong rule". A versioned gold change (list equivalent instances or mark the case scope-invariant) is proposed, not made; frozen gold stays unchanged.
