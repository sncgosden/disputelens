# Exception resolver v2 — result and decision (8 October 2026)

Protocol (fixed before the run, sha256 4285ab37c33c61d126781f95625c1839b2816d8964b6fdbbe8e45a4c4a29cd34) applied unchanged. v1 left as recorded. Offline; development cases only; no model calls.

| Threshold | Result |
|---|---|
| T1: E23 S045 resolves to "list" by S044 | pass |
| T2: E15 S085 resolves to "list" by S084 | pass |
| T3: E13 S030 and S034 return ambiguous | pass |
| T4: nothing in E23 resolves to close or block | pass |
| T5: all 12 flagged passages get exactly one outcome | pass |

Distribution: resolved 2 (E23 S045, E15 S085), ambiguous 10, conflicting 0. No resolution outside T1 to T3 exists to review.

## What this means

- The change did what it was meant to: it removed the two spurious E13 resolutions and kept both correct ones.
- It is deliberately conservative. 10 of 12 flagged passages stay ambiguous. In those the retrieved section does not state what the exception waives, so the honest output is to say so.
- Two of the ambiguous passages (E23 S007 and E15 S039) are the same "No Cardholder Authorization" exceptions in a pre-arbitration section; the explicit sentence exists elsewhere in the guide but was not retrieved with that section. That is the case for fetching the parent or linked section.

## Limits

- v2 was designed after seeing v1 results on the same 12 passages, so this is a regression check; the holdout is the independent test.
- The requirement-statement form ("Listing the PAN ... is required") is specific to this guide's wording.
- Advisory only; not wired into retrieval or generation.

## Decision

Adopt v2 as the advisory resolver. Behaviour: if resolved, attach the exception to the named requirement only and say so; if ambiguous, say the exception's scope is not stated in the retrieved text instead of attaching it to a specific requirement. Next: design the parent/linked-section fetch for ambiguous cases (which section, what word budget), and test it offline on E23 S007 and E15 S039 first.
