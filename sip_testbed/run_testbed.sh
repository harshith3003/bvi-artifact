#!/usr/bin/env bash
# Item 4: SIP testbed. Run from ~/Desktop/bvi :  bash round5/sip_testbed/run_testbed.sh [AUDIO_DIR]
set -eo pipefail
cd "$(dirname "$0")"
export BVI_AUDIO=${1:-$HOME/bvi_audio_data}
cp ../results/item1_devclean/thresholds.json bvi/thresholds.json        # held-out thresholds
mkdir -p results
if [ -n "$MEDIA_ONLY" ]; then           # keep the delay results, re-run the media scenarios only
  rm -f results/media_calls.csv results/calls.jsonl results/*.log results/summary.txt; DELAY_CALLS=0
else
  rm -f results/*.csv results/*.jsonl results/*.log results/summary.txt
fi
echo "== build (first time: several minutes)"
docker compose build
echo "== start"
docker compose up -d
echo "== experiment: ${DELAY_CALLS:-200} delay calls (BVI off/on alternating), ${MEDIA_CALLS:-5} media calls per scenario"
docker compose exec -T caller python3 caller.py --delay-calls "${DELAY_CALLS-200}" --media-calls "${MEDIA_CALLS:-5}"
sleep 2
docker compose logs --no-color > results/compose.log
grep -h "REWROTE" results/compose.log | tail -5 > results/p2_rewrites.log || true
echo "== analysis"
../.venv/bin/python3 analyse_testbed.py results | tee results/summary.txt
docker compose down
