#!/usr/bin/env bash
# Round 5, part A: everything that needs no audio corpus.
# Run from inside ~/Desktop/bvi :   bash round5/run_round5.sh
set -eo pipefail
cd "$(dirname "$0")"
mkdir -p results/registry_v2

echo "== Python environment (round5/.venv)"
[ -x .venv/bin/python3 ] || python3 -m venv .venv
.venv/bin/pip install -q numpy scipy matplotlib cryptography

echo "== Registry v2: install"
( cd registry_v2 && { [ -d node_modules ] || npm install --silent; } )

echo "== Registry v2: all tests"
( cd registry_v2 && npx hardhat test ) 2>&1 | tee results/registry_v2/tests.log

echo "== Registry v2: gas"
( cd registry_v2 && npx hardhat run scripts/gas_profile_v2.js ) 2>&1 | tee results/registry_v2/gas_profile.log
cp registry_v2/results/* results/registry_v2/

echo "== Item 1: unit tests (no corpus needed)"
( cd item1_fingerprint && ../.venv/bin/python3 test_identity_with_digest.py \
    && ../.venv/bin/python3 test_pause_injection.py && ../.venv/bin/python3 test_digest_auth.py ) \
  2>&1 | tee results/item1_unit_tests.log

echo ""
echo "Part A done. Part B: bash round5/item1_fingerprint/run_devclean.sh ~/bvi_audio_data"
