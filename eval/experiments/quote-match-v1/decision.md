# Quote match v1 — result and decision (8 October 2026)

Protocol (declared before the matcher was written, sha256 4b48122234501f13a328c9149ee36b8a3a7c39ad25359c6c33e58916760e03b4) applied unchanged. Offline; no model call. `validate_answer` is unchanged (hash recorded before and after); the tolerant matcher is a separate module, `quote_match.py`.

## Result: H1, H2, H4, H5 pass

- H1: the E13 flagged-answer-v1 raw answer, which failed on "fraud-related" versus "fraud- related", validates with the tolerant matcher; every other check unchanged.
- H2: all 40 baseline answers pass strict and tolerant with identical per-citation results; the hyphen rule was never needed for any of them.
- H3 (reported): none of the 5 failed baseline attempts becomes valid. E06, E21, E54: "answered status cannot list unanswered parts"; E55: malformed JSON; E17: still a wording mismatch not caused by hyphenation (cause not investigated here).
- H4: six synthetic mutations (changed word, changed number, removed "not", two stitched sentences, altered letter next to a hyphen) are all rejected.

## What it means

The hyphen artefact is real but rare in the data: one live instance (E13 in the regeneration test), none in 45 baseline attempts. The change is therefore low value and low risk. The rule only ignores whitespace after a hyphen on both sides, so a quote cannot gain or lose a letter or word. It costs nothing to adopt, but it is a change to a frozen safety check and should be made as a separate, versioned production decision, not folded into this experiment.

## Decision

Recommend adopting the tolerant matcher in the next versioned production change, with the same negative controls as regression tests. Do not change production now. E17's mismatch is a separate open question.
