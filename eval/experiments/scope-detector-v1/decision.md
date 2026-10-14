# Scope detector v1 — result and decision (8 October 2026)

Protocol (fixed before the run, sha256 0a54ad9e5edfde588c2fe7c5a3296eb336dd89bb0dc4283745260ca64c4b2047) was applied unchanged. Offline; development cases only; no model calls.

| Threshold | Result |
|---|---|
| T1: all 6 known defective passages flagged (E13, E22) | 6/6, pass |
| T2: no flags on controls E10, E30, E46 | none, pass |
| T3: at most 3 of 34 applicability-2 cases flagged | 2/34 (E14, E18), pass |

Cases flagged overall: E13, E14, E18, E22, E23.

Reading the flags:
- E13 and E22: the known specialised-scope defects (4850 and 4808 procedures cited without that scope established).
- E18: expected false flag. The question names the dispute ("Refund Not Processed") but not its code, so the code in the heading looks unestablished.
- E23: same cause. The question says "No Cardholder Authorization", which is reason code 4837, but the code is not written in the question.
- E14: the question asks about code 4853; the cited passage sits under a heading listing 4850/4854. Possibly a genuine scope slip the assisted review rated 2; needs a source check, not assumed either way.

Honest limits:
- T1 is not independent evidence: the rule was written after the E13/E22 headings were examined. The informative results are T2 and T3.
- The detector is advisory. It cannot confirm a merchant is in a participating country, and no flag is not proof of applicability.
- Two of the three non-defect flags come from dispute names versus codes. A name-to-code map is the obvious v2 change; it must be declared as a new protocol, not tuned on these results.

Decision: keep v1 as an advisory flag (surface "scope not established" for human or downstream handling). Do not use it to exclude evidence or change generation. Next: a v2 protocol with a reviewed dispute-name-to-code map, evaluated before any generation experiment.
