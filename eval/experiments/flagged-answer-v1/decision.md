# Flagged-answer v1 — result (8 October 2026)

Protocol sha256 634d43ae4d6ad7e164c1c684… (file hash at run) applied unchanged. Approved: 2 free token counts + 2 Claude Sonnet 5.5 calls, cap 0.30 USD, no retries, stop on first failure.

## Result: not passed — stopped after the first call

- Token counts: E13 18,683 and E22 15,986 input tokens; reserved maximum 0.2422 USD (within cap).
- E13 call: 11.8 s, 18,683 in / 1,109 out (682 thinking), cost 0.0485 USD. The output failed the structural check (M1): claim 1's second citation quoted "fraud-related", but the source layout reads "fraud- related". The model silently repaired the hyphenation, and the strict quote matcher rejects it. Recorded as failed, not retried, not scored.
- E22 was not run: the protocol says stop on first failure. Total spend 0.0485 USD of 0.30. The E22 reservation was never made.

## What the unscored output shows (diagnostic only, not a pass)

The raw response is saved. Read by eye, not scored: claim 1 keeps the established core rule (first installment under 4837, later ones under 4850) with citations to the unflagged S010; claim 2 puts the S019 reference-number duty behind "Only if … participating countries" with its citation; missing_information asks for the one scope fact. That is the intended behaviour. It does not count: M1 failed, one sample, same assistant's reading, and E13 is a case the detector was tuned on.

## Finding

The scope notice did not cause the failure, but it shows a separate fragility: long pasted quotes break on layout hyphenation ("fraud- related"). The validator is the right safety (it caught a changed quote) but the cost is a failed answer. Options, not yet decided: shorter quotes (the prompt already asks 5-25 words); a validator that normalises layout hyphenation, versioned separately; or accept and retry in production. Not changed here.

## Decision

Keep v1 as recorded (failed, M1). Remaining allowance is 0.25 USD of the 0.30 cap, but continuing with E22 alone would break the declared stop rule, so it needs your explicit say-so as a separately labelled continuation. No further call is authorised.

## Continuation: E22-only run (user-authorised after the E13 failure; stop rule relaxed on his instruction, labelled in the record)

E22: 15.8 s, 15,986 in / 2,147 out (1,336 thinking), cost 0.0534 USD. Total spend across both calls 0.1019 USD of 0.30 cap.

| Criterion | Result |
|---|---|
| M1 structural | pass |
| M2 no unconditional flagged claim | FAIL: claims 1-4 all cite flagged passages with no conditional marker |
| M3 clarification names reason code / dispute type | pass (missing_information asks for it) |
| M5 source review (assisted, same assistant) | FAIL: all four claims state a refund rule as the merchant's rule |

**Why:** the notice listed the four passages the first answer had cited (S043, S044, S048, S049). The model dropped them and cited three others carrying the same "Refund previously issued" wording: S020 (reason code 4808, Transit First Ride Risk), S002 (4853/4850/4854, Recurring Transaction), S015 (4808, Stand-in or X-Code). All three are scope-bound, so the detector flags them too. The "Refund previously issued" text recurs under many reason-code sections, so telling the model about four passages just moved it to the next four. It also ignored rule 4 (if no established source answers, return needs_clarification) and returned "partial" with unconditional claims, while listing the missing reason code in missing_information: a correct question attached to a wrong-scope answer.

**Overall flagged-answer-v1: fail.** E13: M1 fail (cosmetic quote hyphenation, unscored but promising by eye). E22: M2 and M5 fail. One sample per case.

## Decision and what it implies

1. A prompt notice listing flagged IDs is not enough. Listing every flagged passage is not the answer either (27-52 per pack), and the model ignored an explicit instruction.
2. The detector must be the gate, not an advisory input to the model: run it on the new answer's cited passages; if every claim is flagged, fail closed with a deterministic needs_clarification response asking for the reason code (no generated text); if some are flagged, drop or relabel those claims as conditional by template. This puts the control outside the model. It needs its own declared protocol (scope-guard family) and is cheap to test offline on the 45 saved answers.
3. Separately: the quote validator needs a versioned decision on layout hyphenation.

No further paid calls authorised. Remaining allowance 0.198 USD is not a licence to continue.
