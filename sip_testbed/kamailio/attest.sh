#!/bin/sh
# attest.sh SID HOP DID IN OUT -> prints the wall time (ms) of the on-chain attestation
s=$(date +%s%3N)
curl -s -m 10 -X POST http://bvi:8080/attest -H 'content-type: application/json' \
  -d "{\"sid\":\"$1\",\"hop\":$2,\"did\":\"$3\",\"inId\":\"$4\",\"outId\":\"$5\"}" > /dev/null
e=$(date +%s%3N)
echo $((e - s))
