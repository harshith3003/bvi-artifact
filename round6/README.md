# BVI round 6: additional validation for the TIFS manuscript

All randomness is seeded (20260909). Every script writes its results, the exact parameters and the software
versions next to its outputs. SELFTEST outputs use synthetic audio and only prove the pipeline runs: never
report them.

## Status

| Item | What | Status |
|---|---|---|
| 5 | BVI-0 / BVI-R / BVI-B and four single-correction ablations | **Real results** (1,000 trials; rerun with 2,000 below). See RESULTS.md |
| 4 | Collusion: route length x participation x corruption, random vs targeted, vs theory | **Done** (`collusion/results/`), exact closed form matches Monte Carlo within 0.005 |
| 2 | Threshold robustness: ROC, FAR/FRR with CIs, speaker-disjoint splits, Opus | **Real results**, pause rule on and off. See RESULTS.md |
| 1 | Semantic edits (negations, numbers, names, instructions) | Plan below; needs word alignments and the fingerprint code |
| 3 | SIP testbed extensions | Plan below; needs the testbed code and the corrections ported into it |
| 6 | Performance | Harness measures verification cost; fingerprint CPU, memory and load tests in Stage 3 |

## Setup (once, on the Mac)

```bash
cd ~/Desktop && unzip bvi_round6.zip && cd round6
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Step 1. Check everything runs (2 minutes)

```bash
python3 ablation/run_ablation.py --selftest --trials 200
python3 collusion/sweep.py --trials 200000
```

## Step 2. Final runs on the Mac (about 10 minutes)

```bash
ROOT="<folder holding bvi/ and round6/>"; R5="$ROOT/bvi/round5/results/item1_devclean"
cd "$ROOT/round6" && source .venv/bin/activate
python3 thresholds/convert_round5.py "$R5" data/ber_samples.csv
python3 ablation/run_ablation.py --ber-samples data/ber_samples.csv --thresholds "$R5/thresholds.json" --trials 2000
python3 thresholds/robustness.py --ber-samples data/ber_samples.csv --thresholds "$R5/thresholds.json" --label empirical_pause_on
python3 thresholds/robustness.py --ber-samples data/ber_samples.csv --rule off --label empirical_pause_off
```

Results: `ablation/results/empirical/` (tables.md, summary.csv, per_trial.csv, plots) and
`thresholds/results/empirical/` (report.md, ROC plots, split stability, FRR by condition).

## Stage 2. Port the corrections into the real implementation

The harness is a protocol-level reference with real cryptography. The paper also needs the corrections in the
actual code, so overhead (gas for linked records, stream bytes, verification time) is measured on the system
itself, and the SIP testbed can compare the versions end to end:
- contract: carrier records gain prev/next carrier fields; the verifier applies the linked rule;
- key message v2 in `digest_auth.py`: sign the calling and called numbers, check them on receipt;
- stream v2: frame offset and count in every block tag, plus an authenticated termination record;
- feature flags matching the eight configurations, so the same tests run against every version.

Needed: the round-5 source (no audio, no node_modules):
```bash
cd ~/Desktop/bvi && zip -r ~/Desktop/round5_src.zip round5 -x "*/node_modules/*" "*/artifacts/*" "*/cache/*" "*.wav" "*.flac" "*.mp3"
```

## Stage 3 plans

**Item 1, semantic edits.** Align dev-clean with the Montreal Forced Aligner to get word timestamps. Create
same-speaker edits of 0.2 to 0.8 s: insert a negation ("not", "don't"), swap a number word, swap a proper name,
and swap an instruction verb, each with 10 ms cross-fades. Run them through the existing codec x condition
pipeline, add them to `ber_samples.csv` as `semantic_negation`, `semantic_number`, `semantic_name`,
`semantic_instruction`, and rerun Steps 3 and the ablation: the three versions differ here only through their
threshold policies. Expect detection near the floor measured for 0.5 to 1 s splices; report it as measured.

**Item 3, testbed.** Add an rtpengine (or FreeSWITCH) media server for real G.711/Opus/AMR transcoding,
`tc netem` packet loss on the relay (container needs `cap_add: NET_ADMIN`), SIPp for injected BYE and early
termination, an off-path container that writes false carrier records, and a switch for proxies that do not
attest. Run every testbed scenario under the eight configurations once Stage 2 is merged.

**Item 6, performance.** Fingerprint CPU time per second of audio and peak memory; verification time per version
(from the harness and from the ported code); gas for linked records; and a SIPp load test at increasing call rates
to measure setup delay and verification latency under load.

## Repository

Add `round6/` to the bvi-artifact repository, commit, push, and refresh the anonymous.4open.science mirror.
