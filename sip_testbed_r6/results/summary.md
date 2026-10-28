# Round-6 SIP testbed results

## Call setup (INVITE -> 200 OK at the caller; 3 Kamailio hops, linked attestations, local chain)

- BVI off: n=50, median 0.88 ms, p95 0.99 ms
- BVI on: n=50, median 52.06 ms, p95 56.09 ms
- added: median 51.18 ms [bootstrap 95% 50.38-51.56]
- recipient reads at INVITE: positional (BVI-0) median 7.73 ms; linked (BVI-R) median 8.93 ms

## Verdicts per scenario and configuration (count of verified / not verified / fail)

| Scenario | calls | BVI-0 | BVI-R | BVI-B (strict) | BVI-B (lenient) | R - number binding | R - linked chain | R - auth. termination | R + endpoint strict |
|---|---|---|---|---|---|---|---|---|---|
| honest | 5 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 |
| rewrite | 5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 5/0/0 | 0/0/5 | 0/0/5 | 0/0/5 |
| launder | 5 | 5/0/0 | 0/0/5 | 0/0/5 | 0/0/5 | 5/0/0 | 0/0/5 | 0/0/5 | 0/0/5 |
| false_record | 5 | 0/0/5 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 0/0/5 | 5/0/0 | 5/0/0 |
| relay_session | 5 | 5/0/0 | 0/0/5 | 0/0/5 | 0/0/5 | 5/0/0 | 0/0/5 | 0/0/5 | 0/0/5 |
| missing_records | 5 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 |
| transcode_declared | 5 | 4/0/1 | 4/0/1 | 0/0/5 | 0/0/5 | 4/0/1 | 4/0/1 | 4/0/1 | 0/0/5 |
| transcode_silent | 5 | 5/0/0 | 5/0/0 | 0/0/5 | 0/0/5 | 5/0/0 | 5/0/0 | 5/0/0 | 0/0/5 |
| mobile_origin | 5 | 5/0/0 | 5/0/0 | 0/5/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 0/5/0 |
| loss5 | 5 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 |
| substitute | 5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 |
| splice3s | 5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 |
| strip | 5 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 |
| truncate | 5 | 5/0/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 5/0/0 | 0/5/0 |
| injected_bye | 5 | 5/0/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 5/0/0 | 0/5/0 |

Transcoding scenarios have no single correct answer: they measure availability (honest calls verified).

## Layer detail for BVI-0 and BVI-R (first call of each scenario)

| Scenario | received s | blocks v1/v2 | termination | route pos / linked | thresholds carrier / chain | BVI-0 | BVI-R |
|---|---|---|---|---|---|---|---|
| honest | 10.0 | 10/10 | True | pass / pass | 0.21473780487804878 / 0.21473780487804878 | verified (id pass, route pass, audio pass, BER 0.1167) | verified (id pass, route pass, audio pass, BER 0.1167) |
| rewrite | 10.0 | 10/10 | True | fail / unknown | 0.45535714285714285 / 0.45535714285714285 | fail (id pass, route fail, audio pass, BER 0.1432) | fail (id fail, route unknown, audio unverifiable, BER None) |
| launder | 10.0 | 10/10 | True | pass / unknown | 0.21473780487804878 / 0.45535714285714285 | verified (id pass, route pass, audio pass, BER 0.1402) | fail (id fail, route unknown, audio unverifiable, BER None) |
| false_record | 10.0 | 10/10 | True | fail / pass | 0.21473780487804878 / 0.21473780487804878 | fail (id pass, route fail, audio pass, BER 0.1268) | verified (id pass, route pass, audio pass, BER 0.1268) |
| relay_session | 10.0 | 10/10 | True | pass / pass | 0.21473780487804878 / 0.21473780487804878 | verified (id pass, route pass, audio pass, BER 0.0663) | fail (id fail, route pass, audio unverifiable, BER None) |
| missing_records | 10.0 | 10/10 | True | unknown / unknown | 0.45535714285714285 / 0.45535714285714285 | verified (id pass, route unknown, audio pass, BER 0.0938) | verified (id pass, route unknown, audio pass, BER 0.0938) |
| transcode_declared | 10.0 | 10/10 | True | pass / pass | 0.4035986564009664 / 0.4035986564009664 | verified (id pass, route pass, audio pass, BER 0.389) | verified (id pass, route pass, audio pass, BER 0.389) |
| transcode_silent | 10.0 | 10/10 | True | pass / unknown | 0.45535714285714285 / 0.45535714285714285 | verified (id pass, route pass, audio pass, BER 0.3648) | verified (id pass, route unknown, audio pass, BER 0.3648) |
| mobile_origin | 10.0 | 10/10 | True | pass / pass | 0.4035986564009664 / 0.4035986564009664 | verified (id pass, route pass, audio pass, BER 0.3234) | verified (id pass, route pass, audio pass, BER 0.3234) |
| loss5 | 10.0 | 10/10 | True | pass / pass | 0.21473780487804878 / 0.21473780487804878 | verified (id pass, route pass, audio pass, BER 0.1662) | verified (id pass, route pass, audio pass, BER 0.1662) |
| substitute | 10.0 | 10/10 | True | pass / pass | 0.21473780487804878 / 0.21473780487804878 | fail (id pass, route pass, audio fail, BER 0.5723) | fail (id pass, route pass, audio fail, BER 0.5723) |
| splice3s | 10.0 | 10/10 | True | pass / pass | 0.21473780487804878 / 0.21473780487804878 | fail (id pass, route pass, audio fail, BER 0.5018) | fail (id pass, route pass, audio fail, BER 0.5018) |
| strip | 10.0 | 0/0 | False | pass / pass | 0.45535714285714285 / 0.45535714285714285 | not verified (id pass, route pass, audio unverifiable, BER None) | not verified (id pass, route pass, audio unverifiable, BER None) |
| truncate | 6.0 | 6/6 | False | pass / pass | 0.21473780487804878 / 0.21473780487804878 | verified (id pass, route pass, audio pass, BER 0.113) | not verified (id pass, route pass, audio unverifiable, BER None) |
| injected_bye | 5.0 | 5/5 | False | pass / pass | 0.21473780487804878 / 0.21473780487804878 | verified (id pass, route pass, audio pass, BER 0.048) | not verified (id pass, route pass, audio unverifiable, BER None) |

## Cells that differ from the expected outcome

- none
