# Item 4 — SIP testbed (Docker, one machine)

```
caller ──INVITE──▶ p1 (hop 0) ──▶ p2 (hop 1) ──▶ p3 (hop 2) ──▶ callee      Kamailio 5.x proxies
   └──RTP G.711 + key message + digest blocks──▶ relay ──▶ callee           carrier media relay
                   p1..p3 attest on chain ──▶ bvi (Hardhat node + BVIRegistry round 5)
```

- **caller**: the originating organisation (did:bvi:testbank, with two authorised numbers). It signs the k_c key
  message with its registered Ed25519 key and streams the authenticated digest.
- **p1–p3**: Kamailio proxies. Each record-routes and, on a BVI call, writes its attestation (ID received / ID sent on)
  with its own carrier key before forwarding.
  - In the `rewrite` scenario, **p2 is compromised**. It replaces P-Asserted-Identity with the organisation's
    *other* authorised number (so Layer 1 still passes and only the route check can catch it), and it does not attest.
- **relay**: the carrier media relay. It substitutes the whole call with ASVspoof audio (`substitute`), seconds 3–6
  only (`splice3s`), or drops the key message and digest (`strip`). It never has k_c.
- **callee**: the verifying recipient (carrier p3, hop 2).
  - **At INVITE:** Layer 1 and the route check (JSON-RPC reads), then 200 OK with its one-time X25519 key.
  - **At BYE:** k_c decryption, every block tag, BER against the per-codec threshold from the held-out run (worst
    declared codec, pooled if a hop did not attest), and the verdict.
  - The scenario label is logged only. It never enters a decision.

Run: `bash round5/sip_testbed/run_testbed.sh ~/bvi_audio_data`
(200 delay calls with BVI alternating off and on, plus 5 calls × 5 scenarios with 10 s of speech; about 10 minutes
after the first build).

Outputs in `results/`:
- `summary.txt`: setup delay with and without BVI (median, p95, added delay with a bootstrap interval) and the
  verdict per scenario
- `setup_delay.csv`, `media_calls.csv`, `calls.jsonl`: raw data
- `compose.log`, including the Kamailio logs that show p2's rewrite

Limits:
- The chain is local and mines instantly, and attestations are written synchronously. On a live rollup, attestation
  would be asynchronous and the route check would run during ringing.
- The media is G.711 only.
- There is no translation scenario in the testbed (it is covered by the unit tests and the simulation).
