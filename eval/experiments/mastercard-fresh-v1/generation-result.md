# mastercard-fresh-v1: generation result (9 October 2026)

Protocol sha256 (after the declared max-output amendment): see protocol.json. 12 questions, 12 calls, no retries, $0.552 of the $1.00 cap (worst-case reservation $0.957). Median 8.2 s, p90 10.6 s per answer (the holdout was 3.4 s and 4.6 s; these prompts are about 17,000 tokens). Not tuned on; nothing changed after this result.

## Declared checks
- G1 pass: 12 of 12 answers structurally valid (limit: at least 10).
- G2 pass: spend within cap, no retry.

## Reported, not scored (no labels yet)
- Gate v2 intervened on 9 of 12 answers: 8 failed closed to a clarifying question, 1 was conditionalised, 3 were left unchanged. Gate v4 (invariance exemption) intervened on 9 of 12 as well, but turned two fail-closed answers (F10, F11) into conditional ones.
- Claim level: 28 claims; v2 flags 25 and the semantic detector flags the same 25. They disagree on none. On fresh answers the semantic detector changed nothing.
- 5 of the 6 questions I wrote as describing a subtype (F01 to F06) were intervened on under v2 (F01 untouched).

## What I can and cannot say
- I cannot say how many of those flags were right. That needs the independent ratings in rating-packet.md. The decision rule in protocol.json stays as declared: with fewer than 3 claims rated "no" the result is inconclusive on safety.
- Two readings I can check by eye, with the caveat that I wrote the questions and am reading the answers myself:
  - F03 (ATM cash not dispensed): the pack did not contain the ATM section, so the answer cited a Point-of-Interaction Error section instead. The flag there looks correct, and the cause is retrieval, not scope.
  - F05 (designer bag was a fake): the answer cited the Counterfeit Goods section, which sits under the 4853/4850/4854 family heading. The flag looks like a false positive, and the embedding check missed it too: the nearest title to the question was the recurring-transaction section, not Counterfeit Goods. Short section titles do not carry "fake" as "counterfeit" in this embedding.
- F01 (timeshare) and F03 both ended as partial answers because the relevant section was missing from the pack. In 2 of 6 described-subtype questions the problem was retrieval recall, a separate cost from over-flagging.

## Implication, pending labels
The earlier stress sets suggested over-flagging was a real cost. On fresh questions the gate intervenes on three quarters of the answers. If the labeller rates most of those flags as unnecessary, the default (v2, fail closed) is too blunt to ship as a merchant-facing control, and the next fix is a better signal for "which subtype is meant", not a tighter threshold.

## Model's own status
The model reported 'partial' on 8 of 12 answers, 'needs_clarification' on 3 and 'answered' on 1. Most partials say a needed section was not in the pack, which points at retrieval recall and the 6,000-word pack as a second limit on answer quality, apart from scope.

## Assisted ratings, 12 October 2026 (not independent; no decision drawn)
I rated all 28 claims myself (labels-assisted.json, criteria inside the file). I wrote the questions and built both detectors, and I had already seen the per-claim flags, so this is directional evidence only. The protocol's decision rule needs an independent labeller; this result is recorded as `assisted_only_no_decision` (result-assisted.json).

- Ratings: 19 yes, 1 no, 8 unsure. The single "no" is F02 claim 2 (a Maestro-Europe rule where the question mentions no Maestro).
- Both detectors flag the same 25 claims. All 19 claims I rated "yes" were flagged, so on these ratings 19 of the 20 decided flags were needless (95 percent), and the one real wrong-scope claim was caught.
- With only 1 claim rated "no" the safety question is inconclusive under the declared rule (needs at least 3). It also means this question set barely contained wrong-scope claims, so it says little about whether the gate catches them.
- Correction to my first reading above: F03 (ATM cash not dispensed) cites the 4834 section whose condition reads "Cash was not properly dispensed by an ATM", which does answer the question. The flag is a false positive. My earlier "looks correct" was wrong.
- A gap the ratings exposed: the detector cannot see which system a section belongs to. F02 claims 3 and 4 come from Single Message System chapter 3 and answer a question that never says which system applies. They were not flagged, and I rated them unsure.
- The detector's inherited-code rule flags almost everything under the 4853/4850/4854 and 4834 families, because merchants never write reason codes. The cost lands on the users who need the answer most.

## What this suggests, to test next, not adopt
The product question is no longer which detector, but whether withholding is the right response at all. A gate that discloses the scope beside each claim ("applies to cardholder dispute chargebacks, reason code family 4853; confirm this matches your case") would keep the answer and still tell the merchant what it rests on. That trades a clarification for a visible caveat, and whether merchants read caveats is a user-research question, not something these tests can answer.
