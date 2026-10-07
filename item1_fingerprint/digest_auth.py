"""
digest_auth.py — per-session digest key k_c: generation, encrypted delivery,
and authentication of the fingerprint stream.

NEW in round 4. No earlier BVI code generated, delivered or used k_c; the
fingerprint stream was unauthenticated. This module is the reference
implementation the security theorem assumes.

Protocol (one call, session id sid, originating organisation did):

 1. Recipient's verifier client: fresh X25519 key pair (esk_R, epk_R) per call;
    epk_R (32 B) travels to the originator in call signalling (e.g. SIP 18x/200).
 2. Originator gateway: k_c = 32 random bytes, fresh per call.
    Fresh X25519 (esk_O, epk_O); shared = X25519(esk_O, epk_R);
    w = HKDF-SHA256(shared, salt=sid, info="bvi-kc-wrap-v1"||epk_O||epk_R);
    ct = ChaCha20-Poly1305_w(nonce=0^12, k_c, aad = did||sid)   (w is single-use)
    sig = Ed25519_sign(sk_org, "bvi-kc-v1"||did||sid||epk_R||epk_O||codec||ct)
    sends KeyMsg(epk_O, codec, ct, sig) with the credential assertion (145 B once per call).
    codec (1 byte) is the origin's declared codec, so the recipient can pick the
    content threshold; it is signed, so a path adversary cannot lower it.
 3. Recipient: keccak256(pk_org) must equal the on-chain pubKeyHash for did;
    verify sig (binds k_c to the organisation, this session and THIS recipient's
    epk_R, so a path adversary that swaps epk_R or re-wraps k_c is caught);
    derive w, decrypt k_c.
 4. Stream: for every block of 50 frames (1 s) the originator sends
    tag_b = HMAC-SHA256(k_c, "bvi-fp-v1"||sid||b||block bits)[:8]
    -> 64 bit/s on top of 850 bit/s = 914 bit/s (RTP header-extension budget 1,600).
    A block whose tag fails is rejected: the content check then reports "fail",
    because a cryptographic check found something wrong. A missing block gives no
    evidence for its frames.

k_c is never sent in the clear; only epk_O, ct, sig and the tags cross the path.
"""
import hashlib
import hmac
import os
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature, InvalidTag

FRAMES_PER_BLOCK = 50
TAG_BYTES = 8
TAG_BPS = TAG_BYTES * 8 * 50 // FRAMES_PER_BLOCK   # 64 bit/s


# ── keccak-256 (Ethereum's hash, not SHA3-256) for the on-chain pubKeyHash check ──
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
       0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
       0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
       0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _rol(v, n):
    return ((v << n) | (v >> (64 - n))) & _M if n else v


def keccak256(data: bytes) -> bytes:
    rate = 136
    msg = bytearray(data) + b"\x01"
    msg += b"\x00" * ((-len(msg)) % rate)
    msg[-1] |= 0x80
    A = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        for i in range(rate // 8):
            A[i % 5][i // 5] ^= int.from_bytes(msg[off + 8 * i: off + 8 * i + 8], "little")
        for rc in _RC:
            C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
            D = [C[(x - 1) % 5] ^ _rol(C[(x + 1) % 5], 1) for x in range(5)]
            A = [[A[x][y] ^ D[x] for y in range(5)] for x in range(5)]
            B = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    B[y][(2 * x + 3 * y) % 5] = _rol(A[x][y], _ROT[x][y])
            A = [[B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
            A[0][0] ^= rc
    return b"".join(A[i % 5][i // 5].to_bytes(8, "little") for i in range(4))


def _raw(pub) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


# ── messages ────────────────────────────────────────────────────────────────
CODEC = {"g711u": 1, "g711a": 2, "opus16": 3, "amr122": 4, "amr475": 5}   # same ids as the contract


@dataclass(frozen=True)
class KeyMsg:
    epk_o: bytes   # 32
    codec: int     # 1 byte, origin's declared codec
    ct: bytes      # 48 (32 + 16-byte Poly1305 tag)
    sig: bytes     # 64

    def size(self):
        return len(self.epk_o) + 1 + len(self.ct) + len(self.sig)


def _signed_bytes(did, sid, epk_r, epk_o, codec, ct):
    return b"bvi-kc-v1" + did + sid + epk_r + epk_o + bytes([codec]) + ct


def _wrap_key(shared, sid, epk_o, epk_r):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sid,
                info=b"bvi-kc-wrap-v1" + epk_o + epk_r).derive(shared)


class Recipient:
    def __init__(self):
        self._esk = X25519PrivateKey.generate()
        self.epk = _raw(self._esk.public_key())

    def open(self, msg: KeyMsg, did: bytes, sid: bytes, org_pubkey: bytes, onchain_pubkey_hash: bytes):
        """Returns (k_c, declared codec id) or raises ValueError with the reason."""
        if keccak256(org_pubkey) != onchain_pubkey_hash:
            raise ValueError("organisation key does not match the on-chain pubKeyHash")
        try:
            Ed25519PublicKey.from_public_bytes(org_pubkey).verify(
                msg.sig, _signed_bytes(did, sid, self.epk, msg.epk_o, msg.codec, msg.ct))
        except InvalidSignature:
            raise ValueError("key message signature invalid (wrong org, session, recipient key or ciphertext)")
        shared = self._esk.exchange(X25519PublicKey.from_public_bytes(msg.epk_o))
        try:
            k_c = ChaCha20Poly1305(_wrap_key(shared, sid, msg.epk_o, self.epk)).decrypt(
                b"\x00" * 12, msg.ct, did + sid)
            return k_c, msg.codec
        except InvalidTag:
            raise ValueError("k_c ciphertext does not authenticate")


class Originator:
    def __init__(self, org_signing_key: Ed25519PrivateKey):
        self._sk = org_signing_key

    def start_session(self, did: bytes, sid: bytes, epk_r: bytes, codec: int = CODEC["g711u"]):
        """Generate k_c for this call and the message that delivers it to epk_r."""
        k_c = os.urandom(32)
        esk_o = X25519PrivateKey.generate()
        epk_o = _raw(esk_o.public_key())
        shared = esk_o.exchange(X25519PublicKey.from_public_bytes(epk_r))
        ct = ChaCha20Poly1305(_wrap_key(shared, sid, epk_o, epk_r)).encrypt(b"\x00" * 12, k_c, did + sid)
        sig = self._sk.sign(_signed_bytes(did, sid, epk_r, epk_o, codec, ct))
        return k_c, KeyMsg(epk_o, codec, ct, sig)


# ── stream authentication ───────────────────────────────────────────────────
def _block_bytes(bits_block, act_block):
    """Pack 16 fingerprint bits + 1 activity bit per frame."""
    import numpy as np
    b = np.concatenate([np.asarray(bits_block, dtype=np.uint8),
                        np.asarray(act_block, dtype=np.uint8)[:, None]], axis=1)
    return np.packbits(b.reshape(-1)).tobytes()


def block_tag(k_c, sid, index, bits_block, act_block) -> bytes:
    m = b"bvi-fp-v1" + sid + struct.pack(">I", index) + _block_bytes(bits_block, act_block)
    return hmac.new(k_c, m, hashlib.sha256).digest()[:TAG_BYTES]


def tag_stream(k_c, sid, bits, act):
    n = len(bits) // FRAMES_PER_BLOCK
    return [block_tag(k_c, sid, b, bits[b * FRAMES_PER_BLOCK:(b + 1) * FRAMES_PER_BLOCK],
                      act[b * FRAMES_PER_BLOCK:(b + 1) * FRAMES_PER_BLOCK]) for b in range(n)]


def stream_status(key_ok, tags_ok, n_expected_blocks):
    """'ok' only if the key message verified and every expected block arrived with a
    valid tag; otherwise 'unverifiable' (stripped or failing stream -> not verified)."""
    if not key_ok or len(tags_ok) < n_expected_blocks or not all(tags_ok):
        return "unverifiable"
    return "ok"


def verify_stream(k_c, sid, bits, act, tags):
    """List of booleans, one per block: True if the block's tag verifies."""
    ok = []
    for b, t in enumerate(tags):
        exp = block_tag(k_c, sid, b, bits[b * FRAMES_PER_BLOCK:(b + 1) * FRAMES_PER_BLOCK],
                        act[b * FRAMES_PER_BLOCK:(b + 1) * FRAMES_PER_BLOCK])
        ok.append(hmac.compare_digest(exp, t))
    return ok
