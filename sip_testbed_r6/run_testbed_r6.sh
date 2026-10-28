#!/usr/bin/env bash
# Item 3 (round 6): SIP testbed with all eight configurations judged on every call.
# Run from the bvi folder:  bash round5/sip_testbed_r6/run_testbed_r6.sh [AUDIO_DIR]
set -eo pipefail
cd "$(dirname "$0")"
export BVI_AUDIO=${1:-$HOME/bvi_audio_data}
cp ../results/item1_devclean/thresholds.json ../sip_testbed/bvi/thresholds.json       # held-out thresholds
mkdir -p results && rm -f results/*.csv results/*.jsonl results/*.log results/summary.*
echo "== build (first time: several minutes)"
docker compose build
echo "== start"
docker compose up -d
echo "== experiment: ${DELAY_CALLS:-100} delay calls, ${MEDIA_CALLS:-5} media calls x 15 scenarios"
docker compose exec -T caller python3 caller_r6.py --delay-calls "${DELAY_CALLS:-100}" --media-calls "${MEDIA_CALLS:-5}"
sleep 3
docker compose logs --no-color > results/compose.log
grep -h "REWROTE" results/compose.log | tail -5 > results/p2_rewrites.log || true
echo "== analysis"
docker compose exec -T caller python3 analyse_r6.py /results | tee results/summary.txt
docker compose down
