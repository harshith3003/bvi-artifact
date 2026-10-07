#!/usr/bin/env bash
# Round 5: v1.2 re-run on HELD-OUT data that played no part in the v1.1 -> v1.2 diagnosis:
#   LibriSpeech dev-clean speakers, and ASVspoof eval utterances disjoint from round 4.
# Usage: bash run_devclean.sh [DATA_DIR]
set -eo pipefail
cd "$(dirname "$0")"
DATA=${1:-$HOME/bvi_audio_data}
OUT=../results/item1_devclean
PY=${PY:-../.venv/bin/python3}
mkdir -p "$OUT"

bash prepare_corpus.sh "$DATA" dev-clean
ffmpeg -hide_banner -encoders 2>/dev/null | grep -Ei "opus|amr|mulaw|alaw" | tee "$OUT/ffmpeg_encoders.txt"
grep -q libopencore_amrnb "$OUT/ffmpeg_encoders.txt" || { echo "STOP: no AMR-NB encoder"; exit 1; }

echo "== unit tests"
$PY test_identity_with_digest.py | tee "$OUT/test_identity_with_digest.log"
BVI_SPEECH_DIR="$DATA/LibriSpeech/dev-clean" $PY test_pause_injection.py | tee "$OUT/test_pause_injection_speech.log"
$PY test_digest_auth.py | tee "$OUT/test_digest_auth.log"

echo "== ASVspoof utterances disjoint from round 4"
[ -d "$DATA/asvspoof_spoof_r5" ] || $PY select_asvspoof_spoof.py "$DATA/LA" "$DATA/asvspoof_spoof_r5" 390 eval \
    "$DATA/asvspoof_spoof/selection.tsv"
cp "$DATA/asvspoof_spoof_r5/selection.tsv" "$OUT/asvspoof_selection.tsv"
cp "$DATA/asvspoof_spoof/selection.tsv" "$OUT/asvspoof_selection_round4_excluded.tsv"

echo "== BER experiment (spec v1.2, unchanged; pause rule scored ON and OFF)"
$PY run_ber.py --natural "$DATA/LibriSpeech/dev-clean" --synthetic "$DATA/asvspoof_spoof_r5" \
  --out "$OUT" 2>&1 | tee "$OUT/run_ber.log"

echo "== report (bootstrap over calls; pause rule on and off)"
$PY report_item1.py "$OUT" | tee "$OUT/report.log"
