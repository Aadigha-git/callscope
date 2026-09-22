# Risk assessment template (lightweight — CallScope local demo)

Map loosely to govern / map / measure / manage. Complete before
`validated → production` (T-M5-04). Categories: accuracy, fairness, hallucination,
privacy, security, availability, cost.

## Model under review

| Field | Value |
|-------|-------|
| model_version_id | |
| component / name @ revision | |
| intended use | |
| assessor | |
| date | |

## Checklist

- [ ] Accuracy risks reviewed against frozen-test gates and slice CIs
- [ ] Fairness across voices/accents considered (or titled out-of-scope)
- [ ] Hallucination / overclaim risks mapped to KB gaps + scorers
- [ ] Privacy: no raw audio to third parties; scrubber covers new secrets
- [ ] Security: Hermes toolset lockdown; policy deny paths tested
- [ ] Availability: degrade matrix (§4.11) acceptable for demo SLO
- [ ] Cost: LLM budget guard + cassette default acknowledged
- [ ] Monitoring on (Grafana live-ops + quality/drift)
- [ ] Rollback stack version recorded

## Register entries

Add rows via `RiskRegister.add(...)` (or API when exposed). Each promotion requires
`assessment_complete(model_version_id)`.

| risk_id | category | likelihood | impact | mitigation | status |
|---------|----------|------------|--------|------------|--------|
| R-SEC-LOCAL | security | L | H | Consent + toolset self-test + scrub + session cap + purge (`tests/security/`, T-M6-02) | mitigated |

## Sign-off

| Role | Name | Date |
|------|------|------|
| Assessor | | |
| Reviewer | | |
