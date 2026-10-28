# BVI version comparison and ablation (SELFTEST: synthetic audio, NOT results)

Trials per cell: 20. Seed: 20260909. Thresholds: {"g711u": 0.215, "g711a": 0.212, "opus16": 0.316, "amr122": 0.404, "amr122_g711u": 0.394, "amr475": 0.5, "pooled": 0.455}.

## 1. Attack success (% of attack calls shown as VERIFIED; lower is better)

| Attack | BVI-0 | BVI-R | BVI-B (strict) | BVI-B (lenient) | R - number binding | R - linked chain | R - auth. termination | R + endpoint strict |
|---|---|---|---|---|---|---|---|---|
| X1 relay: session meant for another number | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| X2 caller ID rewritten, neighbours attest | 0.0 | 0.0 | 0.0 | 0.0 | 35.0 | 0.0 | 0.0 | 0.0 |
| X3 caller ID rewritten, half the carriers attest | 40.0 | 0.0 | 0.0 | 0.0 | 80.0 | 0.0 | 0.0 | 0.0 |
| X4 full carrier collusion | 95.0 | 0.0 | 0.0 | 0.0 | 95.0 | 0.0 | 0.0 | 0.0 |
| X5 off-path record laundering | 90.0 | 0.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 | 0.0 |
| X6 codec manipulation by off-path record + 1 s splice | 100.0 | 50.0 | 50.0 | 50.0 | 50.0 | 100.0 | 50.0 | 50.0 |
| X7 codec lie by on-path carrier + 1 s splice | 100.0 | 100.0 | 55.0 | 55.0 | 100.0 | 100.0 | 100.0 | 55.0 |
| X8 tail truncation (last 5 s dropped) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 |
| X9 injected BYE cuts the call | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 |
| X10 early verdict, then 3 s splice | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| X11 3 s splice | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| X12 1 s splice (short edit) | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 | 55.0 |
| X13 full voice substitution | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| X14 key message and stream stripped | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## 2. Honest calls: verified / not verified / fail (%)

| Honest scenario | BVI-0 | BVI-R | BVI-B (strict) | BVI-B (lenient) | R - number binding | R - linked chain | R - auth. termination | R + endpoint strict |
|---|---|---|---|---|---|---|---|---|
| H1 honest, landline, all carriers attest | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 |
| H2 honest, landline, half the carriers attest | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 |
| H3 honest, mobile to landline, transcoder attests | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 0.0 / 100.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 0.0 / 100.0 / 0.0 |
| H4 honest, mobile to landline, transcoder silent | 95.0 / 0.0 / 5.0 | 100.0 / 0.0 / 0.0 | 0.0 / 100.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 95.0 / 0.0 / 5.0 | 100.0 / 0.0 / 0.0 | 0.0 / 100.0 / 0.0 |
| H5 honest, VoIP (Opus) end to end | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 |
| H6 honest, declared number translation | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 |
| H7 honest, hidden AMR leg between landline endpoints | 0.0 / 0.0 / 100.0 | 100.0 / 0.0 / 0.0 | 0.0 / 0.0 / 100.0 | 0.0 / 0.0 / 100.0 | 100.0 / 0.0 / 0.0 | 0.0 / 0.0 / 100.0 | 100.0 / 0.0 / 0.0 | 0.0 / 0.0 / 100.0 |
| H8 honest call, off-path carrier writes false records | 0.0 / 0.0 / 100.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 | 0.0 / 0.0 / 100.0 | 100.0 / 0.0 / 0.0 | 100.0 / 0.0 / 0.0 |

## 3. Layer outcomes for each attack (identity fail / route pass-bot-fail / audio fail; %)

**X1 relay: session meant for another number**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| BVI-R | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| R - linked chain | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X2 caller ID rewritten, neighbours attest**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 0.0 | 0.0 | 100.0 | 5.0 | 0.0 | 0.0 | 0.0 |
| BVI-R | 100.0 | 35.0 | 0.0 | 65.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 35.0 | 0.0 | 65.0 | 0.0 | 0.0 | 0.0 | 35.0 |
| R - linked chain | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 35.0 | 0.0 | 65.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 35.0 | 0.0 | 65.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X3 caller ID rewritten, half the carriers attest**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 5.0 | 35.0 | 60.0 | 5.0 | 0.0 | 0.0 | 40.0 |
| BVI-R | 100.0 | 10.0 | 70.0 | 20.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 10.0 | 70.0 | 20.0 | 0.0 | 0.0 | 0.0 | 80.0 |
| R - linked chain | 100.0 | 5.0 | 35.0 | 60.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 10.0 | 70.0 | 20.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 10.0 | 70.0 | 20.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X4 full carrier collusion**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 5.0 | 0.0 | 0.0 | 95.0 |
| BVI-R | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 5.0 | 0.0 | 0.0 | 95.0 |
| R - linked chain | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X5 off-path record laundering**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 10.0 | 0.0 | 0.0 | 90.0 |
| BVI-R | 100.0 | 50.0 | 0.0 | 50.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 50.0 | 0.0 | 50.0 | 0.0 | 0.0 | 0.0 | 50.0 |
| R - linked chain | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 100.0 | 50.0 | 0.0 | 50.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R + endpoint strict | 100.0 | 50.0 | 0.0 | 50.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X6 codec manipulation by off-path record + 1 s splice**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 | 50.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 | 50.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 | 50.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 | 50.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 | 50.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 | 50.0 |

**X7 codec lie by on-path carrier + 1 s splice**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |

**X8 tail truncation (last 5 s dropped)**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X9 injected BYE cuts the call**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 |

**X10 early verdict, then 3 s splice**

| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |
|---|---|---|---|---|---|---|---|---|
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
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
| BVI-0 | 0.0 | 100.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| BVI-R | 0.0 | 100.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| BVI-B (strict) | 0.0 | 0.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| BVI-B (lenient) | 0.0 | 0.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| R - number binding | 0.0 | 100.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| R - linked chain | 0.0 | 100.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| R - auth. termination | 0.0 | 100.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |
| R + endpoint strict | 0.0 | 100.0 | 0.0 | 0.0 | 45.0 | 0.0 | 0.0 | 55.0 |

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
| BVI-0 | 0.331 | 486 | 6.8 |
| BVI-R | 0.359 | 578 | 6.8 |
| BVI-B (strict) | 0.341 | 578 | 2.0 |
| BVI-B (lenient) | 0.341 | 578 | 2.0 |
| R - number binding | 0.369 | 555 | 6.8 |
| R - linked chain | 0.346 | 578 | 6.8 |
| R - auth. termination | 0.352 | 564 | 6.8 |
| R + endpoint strict | 0.356 | 578 | 6.8 |
