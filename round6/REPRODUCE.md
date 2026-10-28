# Reproducing the round-6 experiments

Everything is seeded with 20260909. Paths below assume the artefact layout:
`round5/` (implementation, from the round-5 artefact plus the round-6 files) and `round6/` (analysis).
Data: LibriSpeech dev-clean (`DATA/LibriSpeech/dev-clean`) and the round-5 held-out results
(`round5/results/item1_devclean/`, produced by `round5/item1_fingerprint/run_devclean.sh`).

## Environment
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r round6/requirements.txt          # cryptography, numpy, scipy, matplotlib
pip install openai-whisper                       # item 1 only
cd round5/registry_v2 && npm ci                  # Hardhat 2.29.1, solc 0.8.24 (contract and chain-read bench)
```
Reference machine: Apple M5 (10 cores), macOS 26.6.2, Python 3.12.10, Node 24, FFmpeg 9.0.2 with libopus and
libopencore-amrnb.

## Stage 2: corrections in the implementation (number binding, stream v2, linked records)
```bash
cd round5/item1_fingerprint
python3 test_digest_auth.py        # expect 10 PASS (round-5 D0-D9, unchanged)
python3 test_digest_auth_v2.py     # expect 12 PASS (R1-R12); each attack checked against BVI-0 and the correction
cd ../registry_v2
npx hardhat test                   # expect 108 passing (99 round-5 + 9 round-6), incl. gas of attestLinked
```

## Item 1: semantic edits
```bash
cd round5/item1_fingerprint
python3 semantic_edits.py align --natural DATA/LibriSpeech/dev-clean \
  --manifest ../results/item1_devclean/manifest.json --out ../results/round6_semantic      # Whisper base.en
python3 semantic_edits.py run --natural DATA/LibriSpeech/dev-clean \
  --manifest ../results/item1_devclean/manifest.json --thresholds ../results/item1_devclean/thresholds.json \
  --out ../results/round6_semantic --check-honest ../results/item1_devclean/honest_raw.csv
```
`--check-honest` stops unless the rebuilt calls reproduce round 5 bit-for-bit. Outputs: `semantic_raw.csv`,
`semantic_summary.md`. Whisper timings can differ slightly across Whisper versions; `alignments.json` is kept so the
edits are reproducible from it.

## Items 2 and 5: threshold robustness and the version comparison / ablation
```bash
cd round6
R5=../round5/results/item1_devclean
python3 thresholds/convert_round5.py $R5 data/ber_samples.csv     # also reads ../round6_semantic if present
python3 ablation/run_ablation.py --ber-samples data/ber_samples.csv --thresholds $R5/thresholds.json --trials 2000
python3 thresholds/robustness.py --ber-samples data/ber_samples.csv --thresholds $R5/thresholds.json --label empirical_pause_on
python3 thresholds/robustness.py --ber-samples data/ber_samples.csv --rule off --label empirical_pause_off
```
Check: the converted data reproduce thesis/paper Table 15 honest false flags (1.5 / 1.3 / 5.6 / 6.3 / 5.9 / 6.5 %).
`python3 ablation/run_ablation.py --selftest` runs the harness on synthetic audio (pipeline check only).

## Item 4: collusion and participation
```bash
cd round6 && python3 collusion/sweep.py --trials 200000     # 220 cells; prints max |Monte Carlo - closed form|
```

## Item 6: performance
```bash
cd round5/item1_fingerprint && python3 perf_round6.py               # results/round6_perf/perf.md
cd ../registry_v2 && npx hardhat test bench/round6_reads.test.js    # results/round6_perf/chain_reads.json
```

## Item 3: SIP testbed (Docker Desktop running)
```bash
bash round5/sip_testbed_r6/run_testbed_r6.sh DATA      # DATA contains LibriSpeech/dev-clean and asvspoof_spoof_r5/
```
Builds the images (static FFmpeg with AMR-NB; the build fails if the AMR encoder is missing), runs 100 setup-delay
calls and 5 calls x 15 scenarios, and writes `round5/sip_testbed_r6/results/summary.md` (verdict matrix, layer detail,
and any cell that differs from the expected outcome).

## Where each result lives
| Result | File |
|---|---|
| Ablation tables, plots | `round6/ablation/results/empirical/` |
| Threshold robustness | `round6/thresholds/results/empirical_pause_on/`, `empirical_pause_off/` |
| Collusion sweep | `round6/collusion/results/` |
| Semantic edits | `round5/results/round6_semantic/` |
| Performance | `round5/results/round6_perf/` |
| SIP testbed | `round5/sip_testbed_r6/results/` |
| Summary of all findings | `round6/RESULTS.md` |
| Definitions of the versions and ablations | `round6/SPEC.md` |
