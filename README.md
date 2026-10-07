# BVI: artifact for the paper under review

This repository has the code, tests, seeds and raw results behind the paper. Everything is the final version: the
contract and verifier the paper describes, the audio fingerprint, the route-check simulations, and the SIP testbed.

## Where each claim is checked

| Paper element | Where | How to check |
|---|---|---|
| Attack taxonomy (Table II, A1–A11) and the layer that defends each attack | `registry_v2/test/scenarios.test.js` | One test block per row, in table order. The final test fails unless every row has exactly one block and all its tests passed. |
| Composition: Layer 4 can only demote; a cryptographic failure is never overridden | `registry_v2/test/C3_G1_G2.test.js` (G1, G2) | Exhaustive check over all 48 verdict combinations |
| Route check under partial participation and collusion | `registry_v2/test/C3_G1_G2.test.js` (C3); `simulations/collusion/` | C3a–C3h on chain; simulation with seed 20260909 and 200,000 trials, closed form vs Monte Carlo |
| Declared caller-ID translations and the translator role | `simulations/translation/`; `registry_v2/test/protections.test.js` (T2) | Exact enumeration plus seeded Monte Carlo; on-chain role tests |
| Registry protections: only registered carriers attest, slots keyed by attester, organisation-only anchors keyed by (did, sid, chainid), rejection before storage | `registry_v2/test/protections.test.js` (P1–P3, C4, X4, C6, D2) | Slot and anchor squatting both fail |
| Two independent revocation principals | `registry_v2/test/revocation.test.js` | Organisation and registrar each revoke alone; only the organisation rotates its key |
| Codec-aware threshold; stripped stream gives "not verified"; anchor and ptr checked after the call | `registry_v2/test/round5.test.js` (R1–R3) | |
| Constant anchor cost; reads are gasless | `registry_v2/test/claims.test.js` | Execution gas identical across call length and hop count |
| Audio fingerprint settings | `item1_fingerprint/FINGERPRINT_SPEC.md`, `fingerprint.py` | `test_identity_with_digest.py`: bits identical to `experiments/digest/digest.py` |
| Speech injected into a pause is caught | `item1_fingerprint/test_pause_injection.py` | |
| Per-call key k_c: generation, encrypted and signed delivery, stream authentication | `item1_fingerprint/digest_auth.py`, `test_digest_auth.py` (D0–D9) | |
| BER, thresholds, false-flag rates, substitution and splice detection | `results/item1_devclean/report.txt` | Held-out speakers (LibriSpeech dev-clean). Thresholds from calibration speakers only. Bootstrap over calls. Pause rule on and off. |
| Real calls: ID rewrite, audio substitution, splice, stripping, setup delay | `sip_testbed/`, `sip_testbed/results/summary.txt` | Kamailio proxies and a media relay in Docker, against a local chain |
| Gas | `results/registry_v2/gas_summary.txt` | |

## Reproduce

Requirements: Node 20 or later, Python 3.12, ffmpeg built with libopencore_amrnb and libopus, and Docker for the testbed.

```bash
bash run_tests.sh          # 99 contract tests, gas profile, fingerprint and k_c unit tests

# translation rule tests (pure functions)
cd registry_v2 && NODE_PATH=$PWD/node_modules npx mocha ../simulations/translation/pathcheck_declared.test.js && cd ..

# simulations
python3 simulations/translation/translation_sim.py
python3 simulations/collusion/collusion_sim.py
python3 simulations/collusion/exposure_window.py

# held-out fingerprint experiment (~70 min)
bash item1_fingerprint/prepare_corpus.sh ~/bvi_audio_data dev-clean
#   ASVspoof 2019 LA: download LA.zip from https://datashare.ed.ac.uk/handle/10283/3336
#   and extract it to ~/bvi_audio_data/LA
bash item1_fingerprint/run_devclean.sh ~/bvi_audio_data

# SIP testbed (Docker running)
bash sip_testbed/run_testbed.sh ~/bvi_audio_data
```

## Data and determinism

- **Audio is not redistributed.** LibriSpeech (CC BY 4.0) is downloaded by the scripts. ASVspoof 2019 LA must be
  obtained from its source. The exact utterances used are listed in `results/item1_devclean/asvspoof_selection.tsv`;
  those listed in `asvspoof_selection_round4_excluded.tsv` were deliberately left out, because an earlier analysis
  had seen them.
- **All randomness is seeded** (20260909). The raw per-call files (`honest_raw.csv`, `attack_raw.csv`) let every
  table be rebuilt at any threshold.

## Also included

| Item | Where |
|---|---|
| Credential-check benchmark (E11) | `credential_check/` |
| Verifier chain-read latency on the final contract, in-process and over JSON-RPC | `registry_v2/scripts/verifier_latency_v2.js`, `results/registry_v2/verifier_latency_v2_*.json` |
| Exact software versions | `requirements.txt`, `registry_v2/package-lock.json`, `ENVIRONMENT.txt` |
| Earlier fingerprint runs and why the spec changed (not held-out; see the note) | `results/history/` |

Credential check (E11, 2,000 runs, honest path only):
`cd credential_check && python3 experiments/e11_credential.py --out results/e11`

Credential check (E11, 2,000 runs, honest path only):
`cd credential_check && python3 experiments/e11_credential.py --out results/e11`
