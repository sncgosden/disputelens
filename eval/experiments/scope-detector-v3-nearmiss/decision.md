# Scope detector v3 near-miss attack — result and decision (8 October 2026)

Protocol (declared before any detector ran on the rows; sha256 bc69dbdc35fb19011dad6c7bf1a2a4325bfecb71911685f8643272c9e22f59e2), near-miss labels sha256 52a484c215c868896e6cef2b7c148961d645c0e57045ea228d68de1d3ed962d5. Offline; no model call. Result: **N1 fails, N2 passes. v3 is not adopted as it stands.**

## Result

- N1 fail: v3 clears 8 of 12 near-miss rows (N01 refund, N02 recurring, N03 complete, N04 currency, N05 counterfeit, N06 refund posted, N07 more than once, N12 surcharge) against a limit of 3. A question that shares one word with a subtype title is treated as having identified the subtype.
- N2 pass: v2 flags all 12 (clears 0).
- N12 was a surprise: I had expected 'surcharge' to be too thin a match, but the title's content words reduce to two (improper, surcharge), so one hit is 50 percent.

## The trade-off, from the sweep (reported, selected-on-seen-data caveat applies)

| share | min hits | scoped false flags /12 | unscoped flagged /12 | near-miss cleared /12 |
|---|---|---|---|---|
| 0.34 or 0.5 | 1 | 2 | 12 | 8 |
| 0.67 or 1.0 | 1 | 3 | 12 | 2 |
| any | 2 | 4 | 12 | 0 or 1 |
| v2 (no description rule) | - | 7 | 12 | 0 |

At the safest operating points that still help (share 0.67 or 1.0, one hit) the near-miss clears fall to 2, but E16 is flagged again (its title has two content words and the question contains one). So with word overlap the fix for E16 and the safety against near-misses pull in opposite directions; the improvement over v2 is real (7 to 3 false flags) but smaller than v3 suggested, and I cannot get E16 cleared without accepting about 8 of 12 near-miss clears.

## Decision

1. Keep v2 as the default detector. It over-flags described-subtype questions (7 of 12 in my set) but never lets a near-miss through, and a needless clarification is the cheaper error.
2. Do not use share 0.67 as "v4" without its own declaration: it is selected on labels I have already seen.
3. Word overlap is the wrong instrument. A semantic check is the next candidate: embed the question and each subtype title with the project's local embedding model, and call the subtype established only if the question is closest to that subtype by a margin over its best sibling. It needs the user's machine and a calibration/test split of my labelled rows (calibrate on pairs.json, test once on nearmiss.json). To be declared before running.
4. The honest summary for the product: reducing needless clarification and avoiding wrong-scope answers trade off, and the right place to fix it is a better "which subtype is meant" signal, not tighter string rules.
