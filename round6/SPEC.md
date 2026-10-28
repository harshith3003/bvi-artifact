# Specification of the versions, ablations and scenarios

This file states exactly what the harness implements. Items marked **CONFIRM** are interpretations of the
specification that should be checked with the co-author before the final runs.

## Mechanisms

| Mechanism | BVI-0 (original) | BVI-R (corrected) | BVI-B |
|---|---|---|---|
| Key message | v1: signs did, sid, epk_R, epk_O, codec, ciphertext; numbers not bound | v2: also signs the canonical calling and called numbers; recipient checks calling = presented number and called = own number | v2 |
| Carrier records | positional rule: ordered by declared position, number transitions checked, neighbour links not checked | linked rule (below) | not used in the decision |
| Codec threshold | worst over the sender's codec and every carrier-reported codec | worst over the sender's codec and a complete valid chain ending at the recipient's carrier, else pooled | endpoint policy (below) |
| Stream | v1: per-block tags over (sid, index, bits); no authenticated end; verdict covers whatever prefix exists when it is taken | v2: per-block tags over (sid, index, frame offset, frames, bits) plus an authenticated termination over (sid, total blocks, total frames) | v2 |

**Linked rule (BVI-R).** Records are linked when each names the other as neighbour and their positions are
consecutive. Admissible evidence is every segment of two or more linked records, plus the terminating carrier's
record (the recipient knows its own carrier). Records no neighbour confirms are ignored, so they can neither
launder a rewrite nor block an honest call. Overlapping admissible records, or neighbour claims that contradict
an admissible record, fail the route. Numbers are compared within segments and across gaps between segments.
The chain is complete only if one admissible segment runs from position 1 to the terminating carrier.
- **CONFIRM 1:** cross-gap comparison is included. Without it, BVI-R without number binding would catch fewer
  straddled rewrites than BVI-0; with it, BVI-R keeps BVI-0's gap detection while resisting laundering.
- **CONFIRM 2:** isolated records (no attesting neighbour) are ignored, except the terminating carrier's.
  This is what blocks single off-path launderers, at the cost of some evidence under sparse participation.
- **CONFIRM 3:** a declared translation may change any number if the writer has the translator role.
  Restricting translations to format-only changes (same canonical number) would also stop an on-path corrupt
  translator from laundering; it can be added as one more ablation.

**Endpoint policy (BVI-B).** The sender's codec (signed in the key message) and the recipient's own received codec.
Equal: that codec's threshold. Different: the transcoding path is unknown, so the audio is "uncertain".
Strict: uncertain audio is not verified. Lenient: the pooled threshold is used instead.
- **CONFIRM 4:** "uncertain" means only that the endpoint codecs differ. A hidden lossy leg between two identical
  endpoint codecs (scenario H7) is invisible to the endpoints, so strict BVI-B applies the endpoint threshold.

**Stream v1 verdict timing.** v1 cannot tell an authenticated end from a stop, so the verdict covers the prefix
available when it is requested (X10 requests it at 10 s). v2 waits for the authenticated termination; the
no-termination ablation decides at the BYE.
- **CONFIRM 5:** an integrity problem in the stream (bad tag, gap, missing or mismatched termination) gives
  "not verified", following the earlier decision R1 that a stripped or failing stream is not verified rather
  than fail. Mismatched counts could instead be treated as fail.

## Configurations (each ablation changes one mechanism of BVI-R)

| Name | Key message | Route | Stream | Codec | Route decides |
|---|---|---|---|---|---|
| BVI-0 | v1 | positional | v1 | carrier | yes |
| BVI-R | v2 | linked | v2 | chain | yes |
| BVI-B (strict) | v2 | none | v2 | endpoint strict | no |
| BVI-B (lenient) | v2 | none | v2 | endpoint lenient | no |
| R - number binding (ablation 1) | **v1** | linked | v2 | chain | yes |
| R - linked chain (ablation 2) | v2 | **positional** | v2 | **carrier** | yes |
| R - auth. termination (ablation 3) | v2 | linked | **v2 without termination** | chain | yes |
| R + endpoint strict (ablation 4) | v2 | linked | v2 | **endpoint strict** | yes |

Ablation 2 reverts the whole original carrier-record rule (validation and codec use), which is one mechanism
in the specification. Every configuration sees identical calls and identical audio draws.

## Outcomes reported separately
- identity: pass / fail (credential, plus number binding when the key message is v2)
- route: pass / no evidence / fail / unused
- audio: pass / fail / unverifiable (stripped or failing stream) / uncertain (strict policy refuses)
- final: fail if identity fails, the route fails (when it decides) or the audio fails; not verified if the audio
  is unverifiable or uncertain; otherwise verified.

## Scenarios
Honest: H1 landline, all attest; H2 half attest; H3 mobile to landline, transcoder attests; H4 transcoder silent;
H5 Opus; H6 declared translation; H7 hidden AMR leg between landline endpoints; H8 honest call while an
off-path carrier writes a false record (availability under attack).
Attacks: X1 relay of a session meant for another number; X2 caller-ID rewrite with attesting neighbours;
X3 rewrite with half attesting; X4 full collusion; X5 off-path record laundering; X6 codec manipulation by an
off-path record plus a 1 s splice; X7 codec lie by an on-path carrier plus a 1 s splice; X8 tail truncation;
X9 injected BYE; X10 early verdict then a 3 s splice; X11 3 s splice; X12 1 s splice; X13 full substitution;
X14 stripped key message and stream. Semantic edits from item 1 will be added as further audio kinds.

## Metrics
Attack success = % of attack calls shown as verified. Honest acceptance = % verified; false rejection = % fail;
plus % not verified. Wilson 95% intervals. Overhead: verification time (real cryptography), bytes of key message
and stream per call, ledger reads. Gas for linked records must be measured on the contract (Stage 2).
