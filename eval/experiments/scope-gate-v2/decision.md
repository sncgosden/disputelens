# Scope gate v2 (wording) — result and decision (8 October 2026)

Protocol (declared before the change, sha256 7fe5fbdec4801298cf7bfb4f936c20dd8cce5cb903a8f17a2dd1bf76f6ee403e) applied unchanged. Offline; no model call. v1 is unchanged and still reproduces (G1-G5 pass).

## Runs

- Run 1 failed W5, saved as `result-run1-failed-checker-bug.json`. Cause: my own check split the prefix at `): ` and cut the closing bracket off the section title, so "4850" looked like a bare code. The wording was correct. I fixed the check (split at the first `: `), left thresholds unchanged and reran.
- Run 2 is the recorded result: W1 to W5 all pass.

## Result

- W1: gate decisions identical to v1 (same actions, same claims withheld or conditionalised, 38 unchanged byte-identical).
- W2: every title printed appears verbatim in a heading of a flagged passage the answer cited. W3: clarifications are under 70 words and name 1 to 3 titles. W4: all outputs validate, deterministic. W5: no bare code lists.

Printed outputs (assisted judgement, not independent):

- E13 claims now start "Only if your dispute is Installment Billing Dispute-Participating Countries (Reason Code 4850): ...".
- E22: "Your question does not say which type of dispute this is. The rules I found apply only to specific disputes, for example: Installment Billing Dispute-Participating Countries (Reason Code 4850); Required Authorization Not Obtained. Which reason code or dispute type is your chargeback?"

## Honest view

Better than v1's "4808, 4850, participating countries, required authorization", which no merchant would recognise. Still imperfect: the same prefix is repeated on two E13 claims, titles are the publisher's jargon, and for the failed E22 attempt the list mixes chapter-level and subtype titles. Whether a merchant can answer "which reason code" is a research question; the code is on the acquirer's notice, which is why asking for it is reasonable. Needs merchant testing before any claim about usability.

## Decision

Adopt v2 wording for the prototype. Keep v1 for reproducibility. Next: nothing further here until merchants or the holdout test it.
