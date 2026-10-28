# Round 6 results (real round-5 held-out data; final runs on the Mac)

Status: all six items complete with final results; the corrections are implemented in the real code (Stage 2).
Reproduction: REPRODUCE.md.

Data: LibriSpeech dev-clean held-out run (40 speakers, 20 calibration / 20 test, 60 test calls, 9 honest
conditions, 6 codecs), converted by `thresholds/convert_round5.py`. Check: the converted data reproduce thesis
Table 15 exactly (honest false flags 1.5 / 1.3 / 5.6 / 6.3 / 5.9 / 6.5 %). Seed 20260909.

## Item 1: semantic edits (real speech, `round5/results/round6_semantic/`)

Method: the 60 held-out test calls of round 5, rebuilt bit-identically (checked against honest_raw.csv), with word
timings from Whisper base.en (1,120 files, 20 test speakers). Same-speaker, time-preserving edits; each passed
through the six codecs at 1% loss and scored exactly as the round-5 splices (pause rule on, per-codec threshold).

| Edit (median length) | Calls | G.711 mu-law | G.711 A-law | Opus | AMR 12.2 | AMR 12.2 to G.711 | AMR 4.75 |
|---|---|---|---|---|---|---|---|
| Negation deleted, background fill (0.21 s) | 44 | 13.6 | 18.2 | 13.6 | 11.4 | 13.6 | 11.4 |
| Negation deleted, digital silence (0.20 s) | 44 | 25.0 | 25.0 | 18.2 | 15.9 | 13.6 | 13.6 |
| Negation inserted (0.20 s) | 60 | 98.3 | 96.7 | 91.7 | 90.0 | 90.0 | 71.7 |
| Number swapped (0.22 s) | 41 | 9.8 | 12.2 | 22.0 | 17.1 | 17.1 | 9.8 |
| Word swapped, name/instruction proxy (0.33 s) | 60 | 28.3 | 23.3 | 18.3 | 11.7 | 20.0 | 8.3 |

(% of edited calls detected; Wilson 95% intervals in `semantic_summary.md`; e.g. G.711 mu-law number swap
9.8% [3.9-22.5].)

Findings:
1. **Sub-second meaning-changing substitutions and deletions are largely undetected (8-28%).** At the call level
   they are barely separable from honest calls: ROC AUC 0.54-0.68 (chance = 0.5), against about 0.97 for 1 s
   splices. The fingerprint compares 2 s windows against a threshold set for 1% honest false flags, so a 0.2 s
   word moves a window's BER too little.
2. **Insertions are caught through the timing shift, not the word.** Keeping the call in sync shifts the speech up
   to the next pause; detection is 55.6% when that shift is under 0.5 s, 77.8% for 0.5-1 s and 99-100% above 1 s.
   An attacker inserting just before a pause therefore reaches the substitution regime.
3. **Deleting with digital silence is caught more often (25% vs 13.6%) only indirectly:** the recipient's gate floor
   (running minimum over 2 s) drops, so later quiet speech counts as pause violations. With the pause rule off, the
   muted deletion is detected 4.5%.
4. **No protocol correction changes this** (ablation X15-X18: 70.5-91.2% success in all eight configurations). With an
   on-path codec lie the threshold rises to 0.5 and success reaches 96.8-100% under BVI-0 and BVI-R; the endpoint
   policies keep it at the base rate (X15b-X18b).

Implication for the paper: BVI's content layer reliably catches substitution, pause injection and splices of about
1 s or longer, but not single-word edits. Detecting them needs a different detector (shorter or word-level windows,
local rather than call-level thresholds), which is future work; the limitation should be stated explicitly.

## Item 3: SIP testbed, all eight configurations on real calls (`round5/sip_testbed_r6/results/`)

Docker, one machine: caller, three Kamailio proxies writing linked attestations, a carrier media relay (real FFmpeg
AMR-NB 12.2 transcoding, packet loss, truncation, substitution), callee, local Hardhat chain with BVIRegistry incl.
attestLinked. Every call carries both protocol versions, and the callee judges each received call under all eight
configurations (identical audio and network events). 5 calls x 15 scenarios, 10 s of dev-clean speech, G.711 at the
callee. Counts are verified / not verified / fail.

| Scenario | BVI-0 | BVI-R | BVI-B strict | BVI-B lenient | R - binding | R - linked | R - termination | R + endpoint |
|---|---|---|---|---|---|---|---|---|
| honest | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 |
| 5% packet loss | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 |
| missing records (only p2 attests) | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 |
| AMR transcoding, declared | 4/0/1 | 4/0/1 | 0/0/5 | 0/0/5 | 4/0/1 | 4/0/1 | 4/0/1 | 0/0/5 |
| AMR transcoding, transcoder silent | 5/0/0 | 5/0/0 | 0/0/5 | 0/0/5 | 5/0/0 | 5/0/0 | 5/0/0 | 0/0/5 |
| mobile (AMR) origin | 5/0/0 | 5/0/0 | 0/5/0 | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | 0/5/0 |
| false off-path record (honest call) | **0/0/5** | 5/0/0 | 5/0/0 | 5/0/0 | 5/0/0 | **0/0/5** | 5/0/0 | 5/0/0 |
| caller-ID rewrite at p2 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | **5/0/0** | 0/0/5 | 0/0/5 | 0/0/5 |
| rewrite + off-path laundering | **5/0/0** | 0/0/5 | 0/0/5 | 0/0/5 | **5/0/0** | 0/0/5 | 0/0/5 | 0/0/5 |
| relay of a session for another number | **5/0/0** | 0/0/5 | 0/0/5 | 0/0/5 | **5/0/0** | 0/0/5 | 0/0/5 | 0/0/5 |
| full substitution | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 |
| 3 s splice | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 | 0/0/5 |
| key message and stream stripped | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 |
| truncation at 6 s | **5/0/0** | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | **5/0/0** | 0/5/0 |
| injected BYE at 5 s | **5/0/0** | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | 0/5/0 | **5/0/0** | 0/5/0 |

Findings (bold = attack succeeds or honest call blocked):
1. Every attack and every honest-call effect seen in simulation reproduces on real SIP signalling and real codecs:
   relay and rewrite succeed only without number binding; truncation and injected BYE only without authenticated
   termination; off-path laundering only under BVI-0; a single false off-path record blocks honest calls only under
   the original carrier-record rule.
2. Without number binding, a rewrite by the silent middle carrier of a 3-hop path is not caught by the linked rule
   either: the only upstream record (p1's) has no attesting neighbour, so it is not admissible and the route is
   "unknown". Number binding is the correction that closes it (identity fail in every v2 configuration).
3. Real AMR transcoding: BVI-0 and BVI-R verify 4/5 and 5/5 honest transcoded calls (one false flag at BER 0.389
   against theta 0.404 for the declared AMR leg); the endpoint policies fail every call with a hidden AMR leg between
   G.711 endpoints (theta 0.215), and strict BVI-B refuses mobile-origin calls (not verified) while lenient BVI-B
   verifies them via the pooled threshold. This is the availability cost measured in the ablation, now on real calls.
4. The content layer behaves as in round 5: substitution (max BER 0.57) and 3 s splices (0.50) fail in every
   configuration; 5% loss keeps honest BER at about 0.17 (verified).
Setup delay (100 calls, BVI on/off) and the positional vs linked read times at INVITE are in `summary.md`.
Limits: one machine; instant local mining (synchronous attestation); transcoding in 1 s chunks with 200 ms codec
context (Opus check: honest BER 0.185 vs 0.167 continuous).

## Item 5: version comparison and single-correction ablation
Final run on the Mac: 2,000 trials per cell, seed 20260909. Attack success = % of attack
calls shown as verified. Full tables: `ablation/results/empirical/tables.md`; per-trial data in `per_trial.csv`.

| Attack | BVI-0 | BVI-R | BVI-B strict | BVI-B lenient | R − binding | R − linked | R − termination | R + endpoint |
|---|---|---|---|---|---|---|---|---|
| Relay of a session meant for another number | 98.4 | 0 | 0 | 0 | **98.4** | 0 | 0 | 0 |
| Caller-ID rewrite, neighbours attest | 0 | 0 | 0 | 0 | **35.9** | 0 | 0 | 0 |
| Caller-ID rewrite, half of carriers attest | 50.9 | 0 | 0 | 0 | **88.6** | 0 | 0 | 0 |
| Full carrier collusion | 98.2 | 0 | 0 | 0 | **98.2** | 0 | 0 | 0 |
| Off-path record laundering | 98.5 | 0 | 0 | 0 | 35.5 | 0 | 0 | 0 |
| Off-path codec manipulation + 1 s splice | 48.0 | 2.0 | 2.0 | 2.0 | 2.0 | **48.0** | 2.0 | 2.0 |
| On-path codec lie + 1 s splice | 48.9 | **48.9** | 1.5 | 1.5 | 48.9 | 48.9 | 48.9 | 1.5 |
| Tail truncation | 98.4 | 0 | 0 | 0 | 0 | 0 | **98.4** | 0 |
| Injected BYE | 98.6 | 0 | 0 | 0 | 0 | 0 | **98.6** | 0 |
| Early verdict, then 3 s splice | 98.7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 s splice, no other attack (baseline) | 1.6 | 1.6 | 1.6 | 1.6 | 1.6 | 1.6 | 1.6 | 1.6 |
| Negation deleted (background fill) | 85.9 | 85.9 | 85.9 | 85.9 | 85.9 | 85.9 | 85.9 | 85.9 |
| ... + on-path codec lie | 100.0 | 100.0 | 87.5 | 87.5 | 100.0 | 100.0 | 100.0 | 87.5 |
| Negation inserted | 1.8 | 1.8 | 1.8 | 1.8 | 1.8 | 1.8 | 1.8 | 1.8 |
| ... + on-path codec lie | 40.9 | 40.9 | 2.1 | 2.1 | 40.9 | 40.9 | 40.9 | 2.1 |
| Number swapped | 91.2 | 91.2 | 91.2 | 91.2 | 91.2 | 91.2 | 91.2 | 91.2 |
| ... + on-path codec lie | 100.0 | 100.0 | 89.5 | 89.5 | 100.0 | 100.0 | 100.0 | 89.5 |
| Word swapped (name / instruction proxy) | 70.5 | 70.5 | 70.5 | 70.5 | 70.5 | 70.5 | 70.5 | 70.5 |
| ... + on-path codec lie | 96.8 | 96.8 | 70.3 | 70.3 | 96.8 | 96.8 | 96.8 | 70.3 |

Honest calls (% verified; from the 1,000-trial run; the 2,000-trial values are in `ablation/results/empirical/tables.md`, section 2):

| Honest scenario | BVI-0 | BVI-R | BVI-B strict | BVI-B lenient | R + endpoint |
|---|---|---|---|---|---|
| Landline, all attest | 98.3 | 98.3 | 98.3 | 98.3 | 98.3 |
| Mobile to landline, transcoder attests | 95.1 | 95.1 | **0** (not verified) | 96.7 | **0** |
| Mobile to landline, transcoder silent | 93.2 | 95.0 | **0** | 95.0 | **0** |
| Hidden AMR leg between landline endpoints | **0** | 97.7 | **0** | **0** | **0** |
| Off-path carrier writes a false record | **0** | 98.8 | 98.8 | 98.8 | 98.8 |

## Item 5b: comparison with external architectures (published results)

Direct reimplementation of these systems is impractical (proprietary infrastructure, or no released implementation),
so they are compared on their published properties and figures. The numbers come from different testbeds and
networks and are context, not a controlled comparison.

| System | Verifies | Route evidence under partial deployment | Content integrity | Recipient burden | Published overhead |
|---|---|---|---|---|---|
| STIR/SHAKEN (RFC 8224/8225, ATIS) | calling number, via the originating carrier's attestation | none (signature lost on non-IP legs) | none | carrier verification service; certificate fetch | certificate fetch about 143-327 ms per repository without caching, under 10 ms with caching (TransNexus operational statistics, 2021) |
| CIV (Wang et al., ACM TOPS 2023; draft-hao-civ-03) | possession of the calling number (challenge-response) | n/a | none | call held during verification | about 0.5 s expected, dominated by 4 DTMF digits (draft-hao-civ-03, design estimate) |
| AuthLoop (Reaves et al., USENIX Security 2016) | caller identity, in-band in the voice channel | n/a | none | in-band modem exchange | about 9 s of user time for authentication |
| AuthentiCall (Reaves et al., USENIX Security 2017) | caller identity and call content, via a central service | n/a | yes: detects 99% of tampered audio, negligible false positives | data channel and central server | at most 1.4 s added to call establishment |
| BBCA (Tas and Baktir, IEEE Access 2024) | calling number, re-checked at each hop on a permissioned PBFT ledger | requires every hop (no defined behaviour for non-participants) | none | none stated | no performance figures reported |
| **BVI-R (this work)** | organisation, session-bound; route; content | yes (linked rule; with number binding, every calling-number rewrite caught at the identity layer) | yes, keyed per call; substitution, pause injection and splices of about 1 s or longer, not single-word edits | reads only, no fees | +47.7 ms setup on the round-5 SIP testbed; recipient checks 0.23 ms per second of audio; chain reads 1.5-6.6 ms for 2-12 carriers |

Reading: BVI-R is the only design above that combines organisational identity, route evidence that tolerates partial
deployment and content integrity without a trusted central service; its setup overhead is one to two orders of
magnitude below the in-band and server-mediated content schemes. AuthentiCall's 99% tamper detection and BVI's results
are not directly comparable: its attack set and audio differ, and BVI's semantic-edit results (item 1) show that short
word-level edits are the hard case for robust-digest schemes in general.

## Stage 2: the corrections in the real implementation
- `digest_auth_v2.py` (number binding, stream v2) with `test_digest_auth_v2.py`: 12/12 pass; the original D0-D9 still
  10/10. Every attack test runs against both versions: BVI-0 accepts it, the correction rejects it.
- `BVIRegistry.sol`: new `attestLinked()` (neighbour links in a separate mapping); `attest()` unchanged.
  Contract suite: **108 passing** (99 round-5 + 9 round-6).
- On chain, the laundering attack under the eight configurations: verified only under BVI-0; under
  "R - linked chain" the route layer is laundered (route pass) but number binding fails it (identity fail).
- Gas (measured, Hardhat): attest() 211,244 first / 194,156 subsequent; attestLinked() 258,907 / 241,831,
  i.e. +47,663 / +47,675 for the two links. attest() is 12 gas above the round-5 figures (211,232 / 194,144)
  only because the larger contract changes function dispatch; its code is unchanged.
- Per-call writes: BVI-0 and BVI-R, one anchor plus one record per attesting carrier; BVI-B, the anchor only.
- Stream: 914 bit/s (v1) vs 930 bit/s (v2: 2-byte frame count per block) plus a 16-byte termination once.

## Item 6: performance (Apple M5, 10 cores, macOS 26.6.2, Python 3.12.10; `round5/results/round6_perf/`)

| Operation | median | p95 |
|---|---|---|
| Sender fingerprint, 60 s call | 12.539 ms | 13.391 ms |
| Recipient content check, 60 s call (alignment search, window BERs, verdict) | 13.808 ms | 15.486 ms |
| Key message setup + open, v1 (BVI-0) | 0.620 ms | 0.630 ms |
| Key message setup + open, v2 (number binding) | 0.622 ms | 0.634 ms |
| Stream tagging, 60 s, v1 / v2 | 0.268 / 0.284 ms | 0.320 / 0.384 ms |
| Stream verification, 60 s, v1 / v2 | 0.274 / 0.280 ms | 0.300 / 0.290 ms |

Recipient: 0.23 ms per second of audio (real-time factor 0.0002, about 4,259 concurrent calls per core); peak memory
20.1 MB for a 60 s check. Stream 914 bit/s (v1) vs 930 bit/s (v2) plus a 16-byte termination.

Chain reads of the live verdict (Hardhat in-process, 200 runs, median (p95) ms):

| Attesting carriers | BVI-B | BVI-0 | BVI-R |
|---|---|---|---|
| 1 | 0.45 (0.55) | 0.87 (1.02) | 1.06 (1.15) |
| 2 | 0.37 (0.40) | 1.12 (1.23) | 1.54 (1.78) |
| 3 | 0.36 (0.39) | 1.41 (1.48) | 2.02 (2.74) |
| 5 | 0.36 (0.40) | 1.99 (3.02) | 3.03 (5.37) |
| 8 | 0.36 (0.39) | 2.82 (3.95) | 4.48 (5.92) |
| 12 | 0.37 (0.40) | 3.97 (5.68) | 6.55 (9.29) |

BVI-B is flat (no carrier records); BVI-0 grows by about 0.27 ms per carrier and BVI-R by about 0.5 ms per carrier
(one extra links read each). The linked rule accepted every honest path (pass, complete). These reads happen
during ringing; on a public network each read adds a round trip unless batched.

Findings:
1. Each correction closes exactly the attacks it targets, and removing one reopens only those attacks.
2. Number binding is the decisive identity correction: without it, relay and full collusion succeed ~98%.
   With it, every calling-number rewrite fails at the identity layer whatever the carriers do.
3. BVI-R's remaining gap is an **on-path** carrier lying about its codec (48.9%). Only endpoint policies stop it.
4. BVI-B's gap is a **hidden lossy leg** between identical endpoint codecs: every honest call on such a path
   fails (100%), as it does under BVI-0. BVI-R handles it via the pooled fallback (2.3% false flags).
5. Strict BVI-B refuses all honest mobile-to-landline calls; lenient BVI-B keeps them (95-97%).
6. The original carrier-record rule lets a single off-path false record block every honest call.

Design suggestion arising from 3 and 4: a **codec-continuity check** (each record declares its input and output
codec, and a declared output must match the next carrier's declared input) would make an on-path codec lie
contradict an honest neighbour, while keeping BVI-R's handling of hidden legs. It can be added as a further
configuration.

## Item 2: threshold robustness
`thresholds/results/empirical_pause_on/` and `empirical_pause_off/`: ROC, FAR/FRR with cluster-bootstrap CIs,
200 speaker-disjoint splits, FRR by condition.

| Codec | Threshold spread over 200 splits, pause rule on | pause rule off |
|---|---|---|
| G.711 mu-law | 0.215 ± 0.005 | 0.214 ± 0.006 |
| G.711 A-law | 0.214 ± 0.005 | 0.212 ± 0.005 |
| Opus 16 kbit/s | **0.475 ± 0.137** (95% range 0.30-0.60) | 0.275 ± 0.005 |
| AMR-NB 12.2 | **0.535 ± 0.115** | 0.374 ± 0.005 |
| AMR-NB 12.2 to G.711 | **0.535 ± 0.106** | 0.380 ± 0.004 |
| AMR-NB 4.75 | **0.648 ± 0.094** | 0.461 ± 0.006 |

**The Opus threshold instability is caused by the pause rule, not by Opus.** The rule raises the maximum
BER in about 5% of honest Opus and AMR call-conditions but in only 1 of 1,080 G.711 call-conditions, and those
calls come from very few speakers (one speaker produces 24 of the 60 raised Opus calls; two produce over half).
46 of the 60 fell in the test half, which is why the published Opus threshold (0.316) came out low and the
held-out false-flag rate (5.6%) exceeded the 1% target. With the rule off, every codec is as stable as G.711.

Trade-off at the operating points (1 s natural splice, FAR = splices accepted): pause rule on, Opus FAR 1.7%
(AUC 0.966); pause rule off, Opus FAR 30.0% (AUC 0.838). Recommended follow-up: decouple pause violations from
the BER threshold (a separate, separately calibrated violation statistic), and calibrate on more speakers.


Honest calls wrongly flagged by noise and packet-loss condition (held-out test calls, 60 per cell, pause rule on,
per-codec threshold; `frr_by_condition.csv`):

| Condition | G.711 mu-law | G.711 A-law | Opus | AMR 12.2 | AMR 12.2 to G.711 | AMR 4.75 |
|---|---|---|---|---|---|---|
| clean, 0% loss | 0.0 | 0.0 | 8.3 | 8.3 | 8.3 | 6.7 |
| clean, 1% loss | 0.0 | 0.0 | 8.3 | 10.0 | 8.3 | 6.7 |
| clean, 5% loss | **13.3** | **10.0** | 8.3 | 11.7 | 10.0 | 6.7 |
| babble 10 dB, 0% loss | 0.0 | 0.0 | 6.7 | 8.3 | 8.3 | 10.0 |
| babble 10 dB, 1% loss | 0.0 | 0.0 | 6.7 | 8.3 | 8.3 | 10.0 |
| babble 10 dB, 5% loss | 0.0 | 0.0 | 10.0 | 10.0 | 10.0 | 11.7 |
| white 20 dB, 0% loss | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.7 |
| white 20 dB, 1% loss | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3.3 |
| white 20 dB, 5% loss | 0.0 | 1.7 | 1.7 | 0.0 | 0.0 | 1.7 |

G.711 false flags come almost entirely from 5% loss on clean speech (repetition concealment); Opus and AMR false flags
(7-12%) occur in clean and babble conditions and nearly vanish under steady white noise, which keeps the recipient's
gate floor high and so suppresses the pause-rule misfires identified above. Attacks were applied at 1% loss only.

## Item 4: collusion and participation
`collusion/results/`: 220 cells, 200,000 trials each; exact closed form matches Monte Carlo within 0.0046.
Without number binding, BVI-0's positional rule catches more straddled rewrites than BVI-R's linked rule
(the cost of ignoring unconfirmed records), but BVI-0 falls to 0% once one off-path accomplice can launder a
record. With number binding, the identity layer catches every calling-number rewrite.
