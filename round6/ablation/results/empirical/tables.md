# BVI version comparison and ablation (empirical BER samples)

Trials per cell: 1000. Seed: 20260909. Thresholds: {"g711u": 0.21473780487804878, "g711a": 0.2124839124839125, "opus16": 0.3159114583333335, "amr122": 0.4035986564009664, "amr122_g711u": 0.3936435803037276, "amr475": 0.49974702380952385, "pooled": 0.45535714285714285}.

## 1. Attack success (% of attack calls shown as VERIFIED; lower is better)

| Attack | BVI-0 | BVI-R | BVI-B (strict) | BVI-B (lenient) | R - number binding | R - linked chain | R - auth. termination | R + endpoint strict |
|---|---|---|---|---|---|---|---|---|
| X1 relay: session meant for another number | 98.6 | 0.0 | 0.0 | 0.0 | 98.6 | 0.0 | 0.0 | 0.0 |
| X2 caller ID rewritten, neighbours attest | 0.0 | 0.0 | 0.0 | 0.0 | 35.6 | 0.0 | 0.0 | 0.0 |
| X3 caller ID rewritten, half the carriers attest | 52.3 | 0.0 | 0.0 | 0.0 | 90.0 | 0.0 | 0.0 | 0.0 |
| X4 full carrier collusion | 98.5 | 0.0 | 0.0 | 0.0 | 98.5 | 0.0 | 0.0 | 0.0 |
| X5 off-path record laundering | 98.6 | 0.0 | 0.0 | 0.0 | 36.1 | 0.0 | 0.0 | 0.0 |
| X6 codec manipulation by off-path record + 1 s splice | 47.6 | 2.1 | 2.1 | 2.1 | 2.1 | 47.6 | 2.1 | 2.1 |
| X7 codec lie by on-path carrier + 1 s splice | 50.3 | 50.3 | 1.6 | 1.6 | 50.3 | 50.3 | 50.3 | 1.6 |
| X8 tail truncation (last 5 s dropped) | 98.1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 98.1 | 0.0 |
| X9 injected BYE cuts the call | 98.9 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 98.9 | 0.0 |
| X10 early verdict, then 3 s splice | 98.9 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| X11 3 s splice | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| X12 1 s splice (short edit) | 1.3 | 1.3 | 1.3 | 1.3 | 1.3 | 1.3 | 1.3 | 1.3 |
| X13 full voice substitution | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| X14 key message and stream stripped | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## 2. Honest calls: verified / not verified / fail (%)

| Honest scenario | BVI-0 | BVI-R | BVI-B (strict) | BVI-B (lenient) | R - number binding | R - linked chain | R - auth. termination | R + endpoint strict |
|---|---|---|---|---|---|---|---|---|
| H1 honest, landline, all carriers attest | 98.3 / 0.0 / 1.7 | 98.3 / 0.0 / 1.7 | 98.3 / 0.0 / 1.7 | 98.3 / 0.0 / 1.7 | 98.3 / 0.0 / 1.7 | 98.3 / 0.0 / 1.7 | 98.3 / 0.0 / 1.7 | 98.3 / 0.0 / 1.7 |
| H2 honest, landline, half the carriers attest | 99.2 / 0.0 / 0.8 | 100.0 / 0.0 / 0.0 | 99.2 / 0.0 / 0.8 | 99.2 / 0.0 / 0.8 | 100.0 / 0.0 / 0.0 | 99.2 / 0.0 / 0.8 | 100.0 / 0.0 / 0.0 | 99.2 / 0.0 / 0.8 |
| H3 honest, mobile to landline, transcoder attests | 95.1 / 0.0 / 4.9 | 95.1 / 0.0 / 4.9 | 0.0 / 100.0 / 0.0 | 96.7 / 0.0 / 3.3 | 95.1 / 0.0 / 4.9 | 95.1 / 0.0 / 4.9 | 95.1 / 0.0 / 4.9 | 0.0 / 100.0 / 0.0 |
| H4 honest, mobile to landline, transcoder silent | 93.2 / 0.0 / 6.8 | 95.0 / 0.0 / 5.0 | 0.0 / 100.0 / 0.0 | 95.0 / 0.0 / 5.0 | 95.0 / 0.0 / 5.0 | 93.2 / 0.0 / 6.8 | 95.0 / 0.0 / 5.0 | 0.0 / 100.0 / 0.0 |
| H5 honest, VoIP (Opus) end to end | 94.4 / 0.0 / 5.6 | 94.4 / 0.0 / 5.6 | 94.4 / 0.0 / 5.6 | 94.4 / 0.0 / 5.6 | 94.4 / 0.0 / 5.6 | 94.4 / 0.0 / 5.6 | 94.4 / 0.0 / 5.6 | 94.4 / 0.0 / 5.6 |
| H6 honest, declared number translation | 99.4 / 0.0 / 0.6 | 99.4 / 0.0 / 0.6 | 99.4 / 0.0 / 0.6 | 99.4 / 0.0 / 0.6 | 99.4 / 0.0 / 0.6 | 99.4 / 0.0 / 0.6 | 99.4 / 0.0 / 0.6 | 99.4 / 0.0 / 0.6 |
| H7 honest, hidden AMR leg between landline endpoints | 0.0 / 0.0 / 100.0 | 97.7 / 0.0 / 2.3 | 0.0 / 0.0 / 100.0 | 0.0 / 0.0 / 100.0 | 97.7 / 0.0 / 2.3 | 0.0 / 0.0 / 100.0 | 97.7 / 0.0 / 2.3 | 0.0 / 0.0 / 100.0 |
| H8 honest call, off-path carrier writes false records | 0.0 / 0.0 / 100.0 | 98.8 / 0.0 / 1.2 | 98.8 / 0.0 / 1.2 | 98.8 / 0.0 / 1.2 | 98.8 / 0.0 / 1.2 | 0.0 / 0.0 / 100.0 | 98.8 / 0.0 / 1.2 | 98.8 / 0.0 / 1.2 |

## 3. Layer outcomes for each attack (identity fail / route pass-bot-fail / audio fail; %)

**X1 relay: session meant for another number**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 1.4 | 0.0 | 0.0 | 98.6 |
| BVI-R | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 1.4 | 0.0 | 0.0 | 98.6 |
| R - linked chain | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X2 caller ID rewritten, neighbours attest**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 0.0 | 0.0 | 100.0 | 1.3 | 0.0 | 0.0 | 0.0 |
| BVI-R | 100.0 | 35.6 | 0.0 | 64.4 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 35.6 | 0.0 | 64.4 | 0.0 | 0.0 | 0.0 | 35.6 |
| R - linked chain | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 35.6 | 0.0 | 64.4 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 35.6 | 0.0 | 64.4 | 0.0 | 100.0 | 0.0 | 0.0 |

**X3 caller ID rewritten, half the carriers attest**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 19.3 | 33.9 | 46.8 | 1.3 | 0.0 | 0.0 | 52.3 |
| BVI-R | 100.0 | 29.1 | 60.9 | 10.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 29.1 | 60.9 | 10.0 | 0.0 | 0.0 | 0.0 | 90.0 |
| R - linked chain | 100.0 | 19.3 | 33.9 | 46.8 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 29.1 | 60.9 | 10.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 29.1 | 60.9 | 10.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X4 full carrier collusion**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 1.5 | 0.0 | 0.0 | 98.5 |
| BVI-R | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 1.5 | 0.0 | 0.0 | 98.5 |
| R - linked chain | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X5 off-path record laundering**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 1.4 | 0.0 | 0.0 | 98.6 |
| BVI-R | 100.0 | 36.1 | 0.0 | 63.9 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 36.1 | 0.0 | 63.9 | 0.0 | 0.0 | 0.0 | 36.1 |
| R - linked chain | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 36.1 | 0.0 | 63.9 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 36.1 | 0.0 | 63.9 | 0.0 | 100.0 | 0.0 | 0.0 |

**X6 codec manipulation by off-path record + 1 s splice**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 52.4 | 0.0 | 0.0 | 47.6 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 97.9 | 0.0 | 0.0 | 2.1 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 97.9 | 0.0 | 0.0 | 2.1 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 97.9 | 0.0 | 0.0 | 2.1 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 97.9 | 0.0 | 0.0 | 2.1 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 52.4 | 0.0 | 0.0 | 47.6 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 97.9 | 0.0 | 0.0 | 2.1 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 97.9 | 0.0 | 0.0 | 2.1 |

**X7 codec lie by on-path carrier + 1 s splice**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 49.7 | 0.0 | 0.0 | 50.3 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 49.7 | 0.0 | 0.0 | 50.3 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 98.4 | 0.0 | 0.0 | 1.6 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 98.4 | 0.0 | 0.0 | 1.6 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 49.7 | 0.0 | 0.0 | 50.3 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 49.7 | 0.0 | 0.0 | 50.3 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 49.7 | 0.0 | 0.0 | 50.3 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 98.4 | 0.0 | 0.0 | 1.6 |

**X8 tail truncation (last 5 s dropped)**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 1.9 | 0.0 | 0.0 | 98.1 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 1.9 | 0.0 | 0.0 | 98.1 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X9 injected BYE cuts the call**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 1.1 | 0.0 | 0.0 | 98.9 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 1.1 | 0.0 | 0.0 | 98.9 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X10 early verdict, then 3 s splice**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 1.1 | 0.0 | 0.0 | 98.9 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |

**X11 3 s splice**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |

**X12 1 s splice (short edit)**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 98.7 | 0.0 | 0.0 | 1.3 |

**X13 full voice substitution**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |

**X14 key message and stream stripped**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |

## 4. Verification overhead (median over all scenarios)

| Config | verify time (ms) | bytes per 30 s call | ledger reads |
|---|---|---|---|
| BVI-0 | 0.303 | 487 | 6.7 |
| BVI-R | 0.327 | 580 | 6.7 |
| BVI-B (strict) | 0.311 | 580 | 2.0 |
| BVI-B (lenient) | 0.315 | 580 | 2.0 |
| R - number binding | 0.338 | 557 | 6.7 |
| R - linked chain | 0.319 | 580 | 6.7 |
| R - auth. termination | 0.317 | 566 | 6.7 |
| R + endpoint strict | 0.328 | 580 | 6.7 |
