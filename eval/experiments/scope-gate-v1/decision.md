# Scope gate v1 — result and decision (8 October 2026)

Protocol (declared before the gate was written, sha256 214b816d2f492367d882a738c139bfa0cc64c910ae8a55d7d6cb62522e32115d) applied unchanged. Offline; no model call; no cost; holdout not read.

## Result: G1 to G5 pass

- G1: no flagged-passage claim survives without the "Only if this applies to you" prefix.
- G2: exactly E13 and E22 change; the other 38 valid baseline answers are byte-identical (0 unnecessary clarifications).
- G3: E13 keeps 1 unconditional claim (the established 4837 / 4850 core) and conditionalises the 2 claims on S002/S019; E22 baseline and the failed flagged-answer-v1 E22 attempt both become needs_clarification with no claims.
- G4: all gated outputs pass the citation validator with quotes unchanged. G5: deterministic.
- G6, information withheld: E13 2 claims (100 words) moved behind a condition; E22 baseline 4 claims (188 words) and the new E22 attempt 4 claims (170 words) withheld, kept in an audit record.

## What this does and does not show

1. The pass is partly by construction. A gate that removes or conditionalises every flagged claim cannot leave one unconditional, and G2 follows from the detector result already known (it flags only E13 and E22). The meaningful claim is narrow: the failure that a prompt could not fix (E22 citing sibling scope-bound passages) is caught regardless of which passages the model picks, because the gate keys on what is cited, not on what the model was told.
2. The guarantee is only as strong as detector recall. A wrong-scope claim the detector misses passes straight through. That is what the holdout and an independent review must test.
3. The clarification wording is a template and is clumsy: for E22 it asks "Which reason code or program applies?" after listing "4808, 4850, participating countries, required authorization", which a merchant will not recognise. Better: name the section titles in plain words, or ask only for the reason code. This is a design item, not a failure.
4. Fail-closed has a cost: E22 loses its whole answer until scope is supplied (188 words withheld). Accepted in the earlier design note; measure it with real users if this is ever built.
5. Still open: exception binding (E23), completeness, quote hyphenation.

## Decision

Adopt the gate as the control for scope, replacing the prompt-notice approach, as an advisory prototype. Next: improve the clarification wording using section titles (small versioned change), and let the holdout test the detector plus gate once, at the final evaluation.
