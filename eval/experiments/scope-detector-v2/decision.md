# Scope detector v2 — result and decision (8 October 2026)

Protocol (fixed before the run, sha256 a402efff4d1548c0631afb40380f2f6a995fad4f4ad5dea3c7b41791f52eb771) applied unchanged. v1 left as recorded. Offline; development cases only; no model calls.

| Threshold | Result |
|---|---|
| T1: all 6 known defective passages still flagged | 6/6, pass |
| T2: no flags on controls E10, E30, E46 | none, pass |
| T3: at most 1 of 34 applicability-2 cases flagged | 0/34, pass |
| T4: v2 flags are a subset of v1 flags | pass |

Flagged cases: E13, E22 only (the two known specialised-scope defects).

Every removed flag was inspected: E14 S073 (the passage is the 4853 family section the question asks about; question also names "cardholder dispute chargeback"); E18 S011 (question names "Refund Not Processed", a heading in the passage path); E23 S014, S044, S045 (question names "No Cardholder Authorization", a heading in the path). Each question genuinely identifies the section.

Limits:
- v2 was designed after seeing v1 results on the same 45 cases, so this is a regression check, not independent validation. Independent evidence can only come from the final holdout run.
- The detector does not catch E23's real defect (an exception broadened beyond listing); that is an exception-binding problem, not a scope-qualifier problem.
- A zero false-flag rate on 34 cases is expected after targeted fixes and says little about new sources or phrasing.

Decision: adopt v2 as the advisory scope signal. It remains advisory: not wired into retrieval or generation, and it never excludes evidence. Next: define the product behaviour for a flagged answer (ask the merchant for the reason code, or state the scope assumption) before any generation experiment, then address exception binding separately.
