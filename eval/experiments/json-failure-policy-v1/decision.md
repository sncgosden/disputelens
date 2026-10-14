# Malformed-JSON failures (E56 class): policy decision, no code change (8 October 2026)

## Evidence
- Holdout: 1 of 15 answers (E56) was unparseable; 14 parsed. Raw text kept in `answers/E56.json`. The break is at character 369: after a complete quote the model wrote `","}],{"id":...`, i.e. a stray key-less fragment and a closed array in the wrong place.
- No other saved answer set in the repo stores raw text for a syntax failure, so the rate is 1 in 15 on this model, not a measured rate. Treat it as "can happen", not "happens 7% of the time".

## Options considered
1. **Repair the string in code (rejected).** The intended structure of E56 is ambiguous: the fragment could mean a second citation for the same claim, a new claim, or garbage. Any repair would decide, silently, what the model meant. That breaks the property that every claim shown has a citation the model actually wrote and the validator actually checked.
2. **Schema-constrained output from the API (preferred, untested).** The malformed shape cannot be produced if the response must match the answer schema. Needs a paid test and a check that quote validation still behaves the same.
3. **One retry on a syntax-only failure (acceptable fallback).** Fresh generation, same prompt, logged as a second attempt, cost counted. Content failures (wrong quote, unknown ID) are never retried; the validator was right and a retry would hide a model error.
4. **Show the user a failure (current behaviour).** Safe, costs a re-ask. Remains the default.

## Decision
Keep option 4 as shipped behaviour. Do not repair strings. Next experiment, when a paid-call budget is approved: replay the failing prompt hash for E56 and a small mixed set under option 2, and report parse-failure count, validator pass rate and cost against an unconstrained control. Pre-declare it before running. Separate syntax failures from content failures in reporting from now on, since they have different remedies.

## Why this is a product call
Reliability and integrity pull against each other here: a repair step would raise the answered rate and weaken the guarantee users are relying on. I chose the guarantee, and recorded what would change my mind (schema-constrained output with an unchanged validator).
