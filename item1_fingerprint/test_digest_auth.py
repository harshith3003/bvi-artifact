"""
test_digest_auth.py — k_c is generated per call, reaches the recipient encrypted,
and a path adversary cannot supply its own digests.

Run: python3 test_digest_auth.py
"""
import os
import time

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import digest_auth as da
import fingerprint as fp

RESULTS = []


def case(name):
    def wrap(f):
        try:
            f()
            RESULTS.append((name, "PASS", ""))
        except AssertionError as e:
            RESULTS.append((name, "FAIL", str(e)))
        return f
    return wrap


def raw(pk):
    return pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


ORG_SK = Ed25519PrivateKey.generate()
ORG_PK = raw(ORG_SK.public_key())
ONCHAIN_HASH = da.keccak256(ORG_PK)            # what register()/rotateKey() store as pubKeyHash
DID = da.keccak256(b"did:bvi:examplebank")
SID = da.keccak256(b"session-nonce" + b"+61312345678")

rng = np.random.default_rng(20260909)
audio = rng.normal(0, 0.1, 8000 * 10)
BITS, ACT = fp.sender_fingerprint(audio)


def expect_reject(fn, reason_part):
    try:
        fn()
    except ValueError as e:
        assert reason_part in str(e), f"rejected for the wrong reason: {e}"
        return
    raise AssertionError("was accepted")


@case("D0 keccak256 matches Ethereum test vectors")
def _():
    assert da.keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert da.keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"


@case("D1 honest call: recipient recovers k_c and every block tag verifies")
def _():
    r = da.Recipient()
    k_c, msg = da.Originator(ORG_SK).start_session(DID, SID, r.epk)
    assert r.open(msg, DID, SID, ORG_PK, ONCHAIN_HASH) == (k_c, da.CODEC["g711u"])
    tags = da.tag_stream(k_c, SID, BITS, ACT)
    assert all(da.verify_stream(k_c, SID, BITS, ACT, tags))
    assert k_c not in msg.ct and msg.size() == 145


@case("D2 path adversary alters digest bits in one block -> only that block fails")
def _():
    r = da.Recipient()
    k_c, msg = da.Originator(ORG_SK).start_session(DID, SID, r.epk)
    tags = da.tag_stream(k_c, SID, BITS, ACT)
    forged = BITS.copy()
    forged[3 * 50 + 7] ^= True
    ok = da.verify_stream(r.open(msg, DID, SID, ORG_PK, ONCHAIN_HASH)[0], SID, forged, ACT, tags)
    assert ok[3] is False and sum(ok) == len(ok) - 1


@case("D3 path adversary substitutes audio AND its own digests under its own key -> rejected")
def _():
    r = da.Recipient()
    mitm_sk = Ed25519PrivateKey.generate()
    _, msg = da.Originator(mitm_sk).start_session(DID, SID, r.epk)
    expect_reject(lambda: r.open(msg, DID, SID, ORG_PK, ONCHAIN_HASH), "signature invalid")
    expect_reject(lambda: r.open(msg, DID, SID, raw(mitm_sk.public_key()), ONCHAIN_HASH), "on-chain pubKeyHash")


@case("D4 path adversary swaps the recipient's epk_R for its own to learn k_c -> rejected")
def _():
    r = da.Recipient()
    attacker = da.Recipient()
    k_c, msg = da.Originator(ORG_SK).start_session(DID, SID, attacker.epk)  # originator was fooled
    assert attacker.open(msg, DID, SID, ORG_PK, ONCHAIN_HASH)[0] == k_c     # attacker learns k_c ...
    expect_reject(lambda: r.open(msg, DID, SID, ORG_PK, ONCHAIN_HASH), "signature invalid")  # ... but r refuses
    # and the attacker cannot re-wrap k_c to r without the organisation's signing key


@case("D5 key message replayed into another session -> rejected")
def _():
    r = da.Recipient()
    _, msg = da.Originator(ORG_SK).start_session(DID, SID, r.epk)
    expect_reject(lambda: r.open(msg, DID, da.keccak256(b"other-session"), ORG_PK, ONCHAIN_HASH), "signature invalid")


@case("D6 block tags from one session do not verify in another")
def _():
    r = da.Recipient()
    k_c, msg = da.Originator(ORG_SK).start_session(DID, SID, r.epk)
    tags = da.tag_stream(k_c, SID, BITS, ACT)
    assert not any(da.verify_stream(k_c, da.keccak256(b"other"), BITS, ACT, tags))


@case("D8 path adversary changes the declared codec (to raise the threshold) -> rejected")
def _():
    import dataclasses
    r = da.Recipient()
    _, msg = da.Originator(ORG_SK).start_session(DID, SID, r.epk, da.CODEC["g711u"])
    tampered = dataclasses.replace(msg, codec=da.CODEC["amr475"])
    expect_reject(lambda: r.open(tampered, DID, SID, ORG_PK, ONCHAIN_HASH), "signature invalid")


@case("D9 stripped or failing stream is 'unverifiable' (-> not verified)")
def _():
    assert da.stream_status(False, [], 10) == "unverifiable"            # key message stripped
    assert da.stream_status(True, [True] * 6, 10) == "unverifiable"     # stream stripped part-way
    assert da.stream_status(True, [True] * 9 + [False], 10) == "unverifiable"  # one tag fails
    assert da.stream_status(True, [True] * 10, 10) == "ok"


@case("D7 bandwidth: 850 + 64 bit/s fits the 1,600 bit/s RTP header-extension budget")
def _():
    assert da.TAG_BPS == 64 and fp.SPEC["bitrate_bps"] + da.TAG_BPS <= 1600


if __name__ == "__main__":
    t0 = time.perf_counter()
    for _ in range(200):
        r = da.Recipient()
        k, m = da.Originator(ORG_SK).start_session(DID, SID, r.epk)
        r.open(m, DID, SID, ORG_PK, ONCHAIN_HASH)
    setup_ms = (time.perf_counter() - t0) / 200 * 1000
    t0 = time.perf_counter()
    tags = da.tag_stream(os.urandom(32), SID, BITS, ACT)
    tag_us = (time.perf_counter() - t0) / len(tags) * 1e6
    for name, status, msg in RESULTS:
        print(f"  {status}  {name}" + (f"  -- {msg}" if msg else ""))
    print(f"\n  key setup + open (both ends, incl. pure-Python keccak): {setup_ms:.2f} ms per call (200 runs)")
    print(f"  tag per 1 s block: {tag_us:.1f} us")
    raise SystemExit(0 if all(s == "PASS" for _, s, _ in RESULTS) else 1)
