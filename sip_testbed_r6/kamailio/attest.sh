#!/bin/sh
# attest.sh SID HOP DID IN OUT SCENARIO -> wall time (ms) of the on-chain linked attestation.
# The chain service decides, from the scenario, whether this carrier takes part and which codec it declares
# (network behaviour being simulated). The recipient never sees the scenario.
s=$(date +%s%3N)
curl -s -m 10 -X POST http://bvi:8080/attest -H 'content-type: application/json' \
  -d "{\"sid\":\"$1\",\"hop\":$2,\"did\":\"$3\",\"inId\":\"$4\",\"outId\":\"$5\",\"scenario\":\"$6\"}" > /dev/null
e=$(date +%s%3N)
echo $((e - s))
