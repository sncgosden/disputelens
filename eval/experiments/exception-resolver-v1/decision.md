# Exception resolver v1 — result and decision (8 October 2026)

Protocol (fixed before the run, sha256 5abd9b270d46e145e26bb50f4d577785ab272061197ba6faf8a039f902b2832c) applied unchanged. Offline; development cases only; no model calls.

## Threshold result

| Threshold | Result |
|---|---|
| T1: E23 S045 resolves to the single stem "list" | resolved to list, by S044, pass |
| T2: no E23 passage resolves to close or block | none, pass |
| T3: every flagged passage gets exactly one outcome | 12 of 12, pass |

## Outcome distribution (12 flagged passages, 5 cases)

- Resolved: 4 (E23 S045; E15 S085; E13 S030 and S034)
- Ambiguous: 8 (no sibling sentence names a requirement, or the exception items carry no distinctive tokens)
- Conflicting: 0

## Source review of resolved passages outside E23 (required by the protocol)

- E15 S085 resolved by S084: correct. S084 states "Listing the PAN on the Stand-in Account File is required when the card was issued in the Latin America and the Caribbean region", the same explicit sentence that settles E23.
- E13 S030 and S034 "resolved" by each other: spurious. The sentence matched is one of the exception items itself (Germany BIN "...when the issuer's stand-in parameters are set to zero..."). It mentions the Stand-in file as part of the exception condition, not as the requirement being waived. So the resolver cannot distinguish an exception item from a requirement statement.

Honest reading: the thresholds pass, but outside E23 only 1 of 3 resolutions is correct. Not safe to rely on.

## Where the real coverage is

The explicit-referent sentence exists in the same section for the "No Cardholder Authorization" section (E23, E15). In the pre-arbitration "compelling evidence" sections (E13, E23 S024, E15 S007) and in the "Goods or Services" sections the evidence does not state it, so the honest product output is "ambiguous: state the ambiguity or fetch the parent section".

## Decision

- Keep the order: bind from sibling evidence only when the sibling sentence is a requirement statement; otherwise state the ambiguity (do not guess).
- Do not wire the v1 resolver into any pipeline: it can mislabel an exception condition as a requirement.
- v2 protocol (declare before running): require the resolving sentence to be a requirement statement (the stem is the grammatical subject, for example "Listing the PAN ... is required/not required"), and exclude sentences that belong to an exception item list. Test again on the same 12, with E13 S030 and S034 required to return ambiguous.
- Neighbour fetch (adding retrieved context for ambiguous cases) is not tested yet; it needs the chunk store and a word-budget design.
