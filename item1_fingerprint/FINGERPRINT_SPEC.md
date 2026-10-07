# BVI audio fingerprint — spec `bvi-fp-v1.2`

Both the TIFS and SDLT papers should cite these settings. They are implemented in `fingerprint.py` (bits),
`digest_auth.py` (k_c and stream authentication), and recorded in every `manifest.json`.

## Fingerprint bits (unchanged from `experiments/digest/digest.py`)

`fingerprint.py` produces bits that are **bit-for-bit identical** to `digest.digest_bits()` with the default
`DigestParams()`. This is checked in `test_identity_with_digest.py`.

| Setting | Value |
|---|---|
| Sample rate | 8 kHz mono |
| Frame | 32 ms Hann window (256 samples), 20 ms hop, frames start at n·hop |
| Pre-emphasis | 0.97 |
| Bands | 17, equally spaced on the Bark scale (Traunmüller), triangular, area-normalised, 300–3400 Hz |
| Bits | 16 per frame: sign of the time difference of adjacent log band-energy differences |
| Rate | 16 × 50 = 800 bit/s |

## Added for the content check

| Setting | Value |
|---|---|
| Activity bit | 1 per frame, causal gate: level ≥ running-minimum floor (2 s) + 9 dB and ≥ −55 dBFS; a bit-frame needs both its frames active |
| Pause violation | counts as 16 bit errors when the receiver hears **sustained** clear speech (floor + 15 dB for ≥ 5 consecutive frames = 100 ms) where the sender was silent within ±2 frames (v1.2) |
| Window | BER over 2 s windows, sliding every 0.2 s |
| Conclusive window | ≥ 40 frames that are sender-active **or** violations |
| Decision | `fail` if any conclusive window BER exceeds θ; `unknown` if no window is conclusive; otherwise `pass` |
| Threshold θ | 99th percentile of the per-call maximum window BER on calibration speakers; reported both pooled over all codecs and per codec (`analyse_thresholds.py`) |
| Authentication | 64-bit HMAC-SHA256 tag under k_c per 1 s block (`digest_auth.py`) |
| Total rate | 800 + 50 (activity) + 64 (tags) = **914 bit/s**, against an RTP header-extension budget of 1,600 bit/s |

## Changes since the version sent in round 3

1. **Back to the original digest parameters.** The round-3 spec used a 64 ms window and log-spaced bands without
   saying it had changed `digest.py`. v1.1 returns to the original parameters exactly.
2. **Window rule fixed** (found in review). In v1, a window needed 40 sender-active frames, and pause violations were
   counted only after that test, so speech injected while the caller was listening was never checked. Violations
   now count towards the 40. `test_pause_injection.py` shows v1 passing an injected call and v1.1 failing it.
3. **The stream is authenticated under k_c** (`digest_auth.py`). Before this round, no code generated or used k_c.

## v1.1 → v1.2 (after the first full run)

The first full run (v1.1, kept in `results/item1/`) set a pooled threshold of 0.70, which is above chance (0.5). The raw
files showed why. No honest **window** exceeded 0.54 under any condition, yet some honest **calls** on AMR-NB and
Opus reached a maximum window BER of 0.70–0.83. That tail disappeared when white noise raised the noise floor. The
v1.1 rule was scoring single-frame codec artefacts at word onsets, and in near-silent pauses, as injected speech.

v1.2 requires the receiver's speech to be sustained (100 ms) and allows ±40 ms of slack at the sender's speech
edges. A real injection lasts seconds, so it is unaffected; `test_pause_injection.py` still fails it. The threshold
is still chosen only on calibration speakers. Both runs are reported.

## Experimental conditions (`run_ber.py`)

- **Natural speech:** LibriSpeech test-clean, 40 speakers. Calls are about 60 s and include listening pauses of
  3–5 s after every ~10 s of speech.
- **Synthetic speech:** ASVspoof 2019 LA eval spoofs, balanced over the 13 attack systems A07–A19 (main). macOS
  `say` is kept as a secondary row only.
- **Honest conditions:** G.711 μ-law and A-law, Opus 16 kbit/s, AMR-NB 12.2 and 4.75 kbit/s, and AMR-NB → G.711;
  each clean, white 20 dB and babble 10 dB; packet loss 0, 1% and 5%.
- **Attacks** (every codec, 1% loss):
  - full substitution, natural and synthetic
  - splices of 0.5, 1, 2, 3 and 5 s
  - 3 s of speech injected into a sender pause
- **Split:** speaker-disjoint calibration and test halves, seed 20260909. The threshold is chosen on calibration
  speakers only.

## Known limitations

- **Packet loss** is applied after decoding with repetition concealment, not inside each codec's own concealment.
- **Alignment** uses cross-correlation plus a ±2-frame search, standing in for RTP timestamps. For attacks this
  favours the attacker.
- **Stripping (open design question):** an adversary that strips the key message and the stream leaves the content
  check with no evidence (`unknown`).
