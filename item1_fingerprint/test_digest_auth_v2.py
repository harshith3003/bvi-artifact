"""
test_digest_auth_v2.py: the round-6 corrections. Every attack is run against BOTH the original code (BVI-0,
digest_auth.py) and the corrected code (digest_auth_v2.py): the test asserts that BVI-0 accepts it (the
documented vulnerability) and that the correction rejects it.

Run: python3 test_digest_auth_v2.py
"""
import os, time
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import digest_auth as da
import digest_auth_v2 as d2
import fingerprint as fp

RESULTS = []
def case(name):
    def wrap(f):
        try:
            f(); RESULTS.append((name, "PASS", ""))
        except AssertionError as e:
            RESULTS.append((name, "FAIL", str(e)))
        return f
    return wrap

raw = lambda pk: pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
ORG_SK = Ed25519PrivateKey.generate(); ORG_PK = raw(ORG_SK.public_key()); ONCHAIN = da.keccak256(ORG_PK)
DID = da.keccak256(b"did:bvi:examplebank")
ORG_A, ORG_A2 = "+61312345678", "+61312340000"     # the organisation's two authorised numbers
VICTIM, MULE = "+61400000001", "+61400000999"
SID = da.keccak256(b"session-nonce" + ORG_A.encode())
rng = np.random.default_rng(20260909)
BITS, ACT = fp.sender_fingerprint(rng.normal(0, 0.1, 8000 * 10))      # 10 s -> 10 blocks
FPB = da.FRAMES_PER_BLOCK

def expect_reject(fn, part):
    try:
        fn()
    except ValueError as e:
        assert part in str(e), f"rejected for the wrong reason: {e}"; return
    raise AssertionError("was accepted")

def v2_session(called=VICTIM, calling=ORG_A):
    r = d2.RecipientV2()
    k_c, msg = d2.OriginatorV2(ORG_SK).start_session(DID, SID, r.epk, calling=calling, called=called)
    return r, k_c, msg

def v1_status(k_c, tags, bits, act):
    """BVI-0: the recipient can only expect as many blocks as arrived."""
    return da.stream_status(True, da.verify_stream(k_c, SID, bits, act, tags), len(tags))


@case("R1 honest call (v2): numbers bound, every block and the termination verify")
def _():
    r, k_c, msg = v2_session()
    assert r.open_bound(msg, DID, SID, ORG_PK, ONCHAIN, ORG_A, VICTIM, ORG_A, VICTIM) == (k_c, da.CODEC["g711u"])
    blocks, term = d2.tag_stream_v2(k_c, SID, BITS, ACT)
    assert d2.verify_stream_v2(k_c, SID, BITS, ACT, blocks, term)[0] == "ok"

@case("R2 relay: session opened to another number is accepted by BVI-0, rejected by v2")
def _():
    r1 = da.Recipient(); k1, m1 = da.Originator(ORG_SK).start_session(DID, SID, r1.epk)   # org thinks it calls MULE
    assert r1.open(m1, DID, SID, ORG_PK, ONCHAIN)[0] == k1                               # BVI-0: nothing to check
    r, k_c, msg = v2_session(called=MULE)
    expect_reject(lambda: r.open_bound(msg, DID, SID, ORG_PK, ONCHAIN, ORG_A, VICTIM, ORG_A, MULE), "called number mismatch")

@case("R3 relay variant: path adversary relabels the signed called number -> signature fails")
def _():
    r, k_c, msg = v2_session(called=MULE)
    expect_reject(lambda: r.open_bound(msg, DID, SID, ORG_PK, ONCHAIN, ORG_A, VICTIM, ORG_A, VICTIM), "signature invalid")

@case("R4 calling number rewritten in transit (even to the org's other number): rejected by v2")
def _():
    r, k_c, msg = v2_session()
    expect_reject(lambda: r.open_bound(msg, DID, SID, ORG_PK, ONCHAIN, ORG_A2, VICTIM, ORG_A, VICTIM), "calling number mismatch")

@case("R5 declared national-format translation of the calling number still verifies")
def _():
    r, k_c, msg = v2_session()
    assert r.open_bound(msg, DID, SID, ORG_PK, ONCHAIN, "03 1234 5678", VICTIM, ORG_A, VICTIM)[0] == k_c

@case("R6 tail truncation (last 3 s dropped): BVI-0 ok, v2 unverifiable, v2 without termination ok")
def _():
    r, k_c, msg = v2_session(); cut = 7 * FPB
    assert v1_status(k_c, da.tag_stream(k_c, SID, BITS, ACT)[:7], BITS[:cut], ACT[:cut]) == "ok"
    blocks, term = d2.tag_stream_v2(k_c, SID, BITS, ACT)
    assert d2.verify_stream_v2(k_c, SID, BITS[:cut], ACT[:cut], blocks[:7], None)[0] == "unverifiable"
    assert d2.verify_stream_v2(k_c, SID, BITS[:cut], ACT[:cut], blocks[:7], None, require_termination=False)[0] == "ok"

@case("R7 attacker forwards the genuine termination after dropping the tail -> counts mismatch")
def _():
    r, k_c, msg = v2_session(); cut = 7 * FPB
    blocks, term = d2.tag_stream_v2(k_c, SID, BITS, ACT)
    st, why = d2.verify_stream_v2(k_c, SID, BITS[:cut], ACT[:cut], blocks[:7], term)
    assert st == "unverifiable" and "termination says" in why, why

@case("R8 injected BYE at 4 s: BVI-0 ok, v2 unverifiable")
def _():
    r, k_c, msg = v2_session(); cut = 4 * FPB
    assert v1_status(k_c, da.tag_stream(k_c, SID, BITS, ACT)[:4], BITS[:cut], ACT[:cut]) == "ok"
    blocks, _ = d2.tag_stream_v2(k_c, SID, BITS, ACT)
    assert d2.verify_stream_v2(k_c, SID, BITS[:cut], ACT[:cut], blocks[:4], None)[0] == "unverifiable"

@case("R9 premature verdict at 5 s: BVI-0 already ok; v2 withholds until the termination")
def _():
    r, k_c, msg = v2_session(); cut = 5 * FPB
    assert v1_status(k_c, da.tag_stream(k_c, SID, BITS, ACT)[:5], BITS[:cut], ACT[:cut]) == "ok"
    blocks, term = d2.tag_stream_v2(k_c, SID, BITS, ACT)
    assert d2.verify_stream_v2(k_c, SID, BITS[:cut], ACT[:cut], blocks[:5], None)[0] == "unverifiable"
    assert d2.verify_stream_v2(k_c, SID, BITS, ACT, blocks, term)[0] == "ok"

@case("R10 forged or replayed termination is rejected")
def _():
    r, k_c, msg = v2_session(); cut = 7 * FPB
    blocks, term = d2.tag_stream_v2(k_c, SID, BITS, ACT)
    forged = (7, cut, os.urandom(8))
    assert "does not authenticate" in d2.verify_stream_v2(k_c, SID, BITS[:cut], ACT[:cut], blocks[:7], forged)[1]
    other_sid = da.keccak256(b"other-session")
    _, t_other = d2.tag_stream_v2(k_c, other_sid, BITS[:cut], ACT[:cut])
    assert "does not authenticate" in d2.verify_stream_v2(k_c, SID, BITS[:cut], ACT[:cut], blocks[:7], t_other)[1]

@case("R11 dropped middle block or reordered blocks -> a tag fails (positions are authenticated)")
def _():
    r, k_c, msg = v2_session()
    blocks, term = d2.tag_stream_v2(k_c, SID, BITS, ACT)
    keep = [i for i in range(10) if i != 4]
    bits = np.concatenate([BITS[i * FPB:(i + 1) * FPB] for i in keep]); act = np.concatenate([ACT[i * FPB:(i + 1) * FPB] for i in keep])
    assert d2.verify_stream_v2(k_c, SID, bits, act, [blocks[i] for i in keep], term)[0] == "unverifiable"
    order = [0, 1, 3, 2, 4, 5, 6, 7, 8, 9]
    bits = np.concatenate([BITS[i * FPB:(i + 1) * FPB] for i in order]); act = np.concatenate([ACT[i * FPB:(i + 1) * FPB] for i in order])
    assert d2.verify_stream_v2(k_c, SID, bits, act, [blocks[i] for i in order], term)[0] == "unverifiable"

@case("R12 bandwidth: 850 + 64 + 16 bit/s = 930 bit/s fits the 1,600 bit/s budget; termination 16 B once")
def _():
    assert fp.SPEC["bitrate_bps"] + d2.stream_overhead_bits_per_s("v2") == 930 <= 1600 and d2.END_BYTES == 16


if __name__ == "__main__":
    def timeit(fn, n=200):
        t0 = time.perf_counter()
        for _ in range(n): fn()
        return (time.perf_counter() - t0) / n * 1000
    def v1_setup():
        r = da.Recipient(); k, m = da.Originator(ORG_SK).start_session(DID, SID, r.epk); r.open(m, DID, SID, ORG_PK, ONCHAIN)
    def v2_setup():
        r, k, m = v2_session(); r.open_bound(m, DID, SID, ORG_PK, ONCHAIN, ORG_A, VICTIM, ORG_A, VICTIM)
    k = os.urandom(32); B1 = da.tag_stream(k, SID, BITS, ACT); B2, T2 = d2.tag_stream_v2(k, SID, BITS, ACT)
    for name, status, msg in RESULTS:
        print(f"  {status}  {name}" + (f"  -- {msg}" if msg else ""))
    print(f"\n  key setup + open per call: v1 {timeit(v1_setup):.2f} ms, v2 {timeit(v2_setup):.2f} ms (200 runs)")
    print(f"  verify 10 s stream: v1 {timeit(lambda: da.verify_stream(k, SID, BITS, ACT, B1), 500):.3f} ms, "
          f"v2 {timeit(lambda: d2.verify_stream_v2(k, SID, BITS, ACT, B2, T2), 500):.3f} ms")
    raise SystemExit(0 if all(s == "PASS" for _, s, _ in RESULTS) else 1)
