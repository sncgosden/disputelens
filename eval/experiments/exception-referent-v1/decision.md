# Exception-referent detector v1 — result and decision (8 October 2026)

Protocol (fixed before the run, sha256 e7bd17c16916cb1e264c1752bcd58b83056d4295f6c2e82bf014646e6900e609) applied unchanged. Offline; development cases only; no model calls.

## Finding behind it

E23's over-broad exception was not a generation slip. S045 says "This requirement does not apply when..." immediately after three listed requirements (close, block, list). Read in the retrieved passage alone, the exception could attach to all three. Only the linked complete evidence (S044) shows the exceptions waive listing only. The cause is an ambiguous referent in the evidence, so a prompt cannot fix it.

## Result

| Threshold | Result |
|---|---|
| T1: known defect (E23 S045) flagged | flagged, pass |
| T2: no flags on controls E10, E30, E46 | none, pass |
| T3: at most 3 of 34 correctness-2 cases flagged | 0/34, pass |

Only flag among cited passages: E23 S045.

Prevalence (descriptive): 12 of 3,053 retrieved passages (0.4%) match, across 5 cases (E13, E15, E18, E19, E23). The answer cited such a passage only in E23. So the pattern is rare, but it is present in retrieved context for 5 of 45 cases and the model avoided it in 4.

## Limits

- One known defect, so T1 is a single example, not recall. The rule was written after reading E23; the independent test is the holdout.
- The pattern is Mastercard-guide shaped and English; other phrasing of exceptions will be missed (false negatives are likely).
- A flag says "ambiguous referent", not which reading is right.
- E23 also has completeness gaps (LAC and Germany qualifications, CAT2 branch) that this does not address; those were traced to answer budget and are a separate matter.

## Decision

Adopt as an advisory flag. Behaviour when raised: before answering from a flagged passage, fetch its linked or neighbouring evidence (the passage that names the listing exceptions) or state the ambiguity instead of attaching the exception to a specific requirement. Not wired into retrieval or generation yet; no generation experiment run.

Next: specify the linked-evidence fetch (which neighbours, what budget) and test it offline on E23 and the other four cases where the pattern appears in retrieved context.
