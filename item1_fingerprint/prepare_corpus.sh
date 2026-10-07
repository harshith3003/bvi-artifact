#!/usr/bin/env bash
# Downloads a LibriSpeech subset from OpenSLR. Usage: bash prepare_corpus.sh [DATA_DIR] [SUBSET]
#   SUBSET: test-clean (default, used in round 4) or dev-clean (held-out set for round 5)
set -e
DATA=${1:-$HOME/bvi_audio_data}
SUBSET=${2:-test-clean}
mkdir -p "$DATA" && cd "$DATA"
if [ ! -d "LibriSpeech/$SUBSET" ]; then
  curl -L -o "$SUBSET.tar.gz" "https://www.openslr.org/resources/12/$SUBSET.tar.gz"
  tar -xzf "$SUBSET.tar.gz"
fi
echo "Natural corpus ready: $DATA/LibriSpeech/$SUBSET  ($(ls LibriSpeech/$SUBSET | wc -l | tr -d ' ') speakers)"
