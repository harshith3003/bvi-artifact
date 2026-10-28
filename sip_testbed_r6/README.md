# Round-6 SIP testbed (item 3): all eight configurations on real SIP calls

```
caller ──INVITE──▶ p1 (hop 0) ──▶ p2 (hop 1) ──▶ p3 (hop 2) ──▶ callee        Kamailio proxies, linked attestations
   └── RTP G.711 + K/L key messages + B/C blocks + E termination ──▶ relay ──▶ callee
                                         chain service: Hardhat node + BVIRegistry (attestLinked)
```

Every call carries both protocol versions (key message v1 and v2, block tags v1 and v2, the v2 termination), and
the carriers write linked records. The callee judges **each received call under all eight configurations**
(`py/bvi_eval.py`), so the versions are compared on identical audio and network events. The scenario label drives
only the simulated network and attacker; the callee never uses it.

| Scenario | Network / attacker behaviour |
|---|---|
| honest | all carriers attest, G.711 end to end |
| loss5 | the relay drops 5% of RTP packets |
| missing_records | only p2 attests |
| transcode_declared | the relay transcodes through real AMR-NB 12.2 (FFmpeg); p2 declares AMR, p3 G.711 |
| transcode_silent | the same; p2 (the transcoder) does not attest |
| mobile_origin | AMR-origin call (declared in the key message) transcoded to G.711 by p1 |
| false_record | honest call; an off-path registered carrier writes a contradicting record |
| relay_session | the session was opened by the organisation to another number |
| rewrite | p2 rewrites the caller ID to the organisation's other number and does not attest |
| launder | as rewrite, plus an off-path registered translator writes a bridging record |
| substitute / splice3s | the relay replaces the whole call / seconds 3-6 with ASVspoof speech |
| strip | the relay drops key messages, blocks and termination |
| truncate | the relay stops forwarding media, blocks and termination at 6 s |
| injected_bye | a forged BYE with the dialog identifiers reaches the callee at 5 s |

Run from the `bvi` folder (Docker Desktop running):
`bash round5/sip_testbed_r6/run_testbed_r6.sh ~/bvi_audio_data`
(100 setup-delay calls, then 5 calls x 15 scenarios with 10 s of dev-clean speech: about 25 minutes after the
first build). Outputs in `sip_testbed_r6/results/`: `summary.md` (verdict matrix, layer detail, any cell that
differs from the expected outcome), `calls.jsonl`, `setup_delay.csv`, `media_calls.csv`, `compose.log`.

Limits: one machine; the chain mines instantly and attestation is synchronous; transcoding is applied in 1 s chunks
with 200 ms of codec context (measured with Opus: honest BER 0.185 vs 0.167 for continuous encoding); the callee
always receives G.711, so its received codec is G.711.
