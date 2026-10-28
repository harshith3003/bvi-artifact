"""Protocol mechanisms with real cryptography.

Key message (KM): delivers the per-call key k_c to the recipient.
  v1 (BVI-0): signature covers did, sid, epk_R, epk_O, codec, ciphertext. Calling/called numbers are NOT bound.
  v2 (corrected): the signature also covers the canonical calling and called numbers, and the recipient
                  checks them against the presented calling number and its own number.

Stream: one HMAC tag per 1-second block of fingerprint bits under k_c.
  v1:        tag over (sid, block index, bits). No end-of-stream authentication.
  v2:        tag over (sid, block index, frame offset, frames in block, bits) plus an authenticated
             termination record over (sid, total blocks, total frames).
  v2_noterm: v2 per-block checks, but no authenticated termination (ablation 3).
"""
import os, hmac, hashlib
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidSignature, InvalidTag

FRAMES_PER_BLOCK = 50          # 20 ms frames, 1 s blocks
TAG_BYTES = 8

def raw(pub):
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

def H(*parts):
    """Length-prefixed SHA3-256 (stands in for the contract's Keccak-256; outcome-neutral)."""
    m = hashlib.sha3_256()
    for p in parts:
        b = p if isinstance(p, bytes) else str(p).encode()
        m.update(len(b).to_bytes(4, "big")); m.update(b)
    return m.digest()

def canonical(num):
    """Canonical E.164 form, so a declared national-format translation still matches the signed number."""
    n = num.replace(" ", "")
    return "+61" + n[1:] if n.startswith("0") else n

# ------------------------------------------------------------------ organisation and recipient keys
class Org:
    def __init__(self, did, numbers):
        self.did, self.numbers = did, numbers
        self.sk = Ed25519PrivateKey.generate(); self.pk = raw(self.sk.public_key())
        self.pk_hash = H(self.pk)                   # what the registry stores

def recipient_ephemeral():
    sk = X25519PrivateKey.generate(); return sk, raw(sk.public_key())

def _kdf(shared, info):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(shared)

# ------------------------------------------------------------------ key message
@dataclass
class KeyMessage:
    version: str; did: str; sid: bytes; epk_R: bytes; epk_O: bytes; codec: str
    nonce: bytes; ct: bytes; calling: str = ""; called: str = ""; pk: bytes = b""; sig: bytes = b""

    def body(self):
        parts = [self.version, self.did, self.sid, self.epk_R, self.epk_O, self.codec, self.nonce, self.ct]
        if self.version == "v2":
            parts += [canonical(self.calling), canonical(self.called)]
        return H(*parts)

    def size(self):
        base = len(self.did) + 32 + 32 + 32 + len(self.codec) + 12 + len(self.ct) + 32 + 64
        return base + (len(canonical(self.calling)) + len(canonical(self.called)) if self.version == "v2" else 0)

def make_key_message(org, sid, epk_R, codec, calling, called, version):
    k_c = os.urandom(32)
    eph = X25519PrivateKey.generate(); epk_O = raw(eph.public_key())
    shared = eph.exchange(X25519PublicKey.from_public_bytes(epk_R))
    key = _kdf(shared, b"bvi-kc" + sid)
    nonce = os.urandom(12)
    ct = ChaCha20Poly1305(key).encrypt(nonce, k_c, sid)
    km = KeyMessage(version, org.did, sid, epk_R, epk_O, codec, nonce, ct, calling, called, org.pk)
    km.sig = org.sk.sign(km.body())
    return km, k_c

def verify_key_message(km, registry_pk_hash, sid, epk_R, sk_R, presented_calling, own_number):
    """Returns (status, k_c). status in: ok, missing, bad_key, bad_sig, bad_session, calling_mismatch, called_mismatch."""
    if km is None:
        return "missing", None
    if H(km.pk) != registry_pk_hash:
        return "bad_key", None
    try:
        Ed25519PublicKey.from_public_bytes(km.pk).verify(km.sig, km.body())
    except InvalidSignature:
        return "bad_sig", None
    if km.sid != sid or km.epk_R != epk_R:
        return "bad_session", None
    if km.version == "v2":
        if canonical(km.calling) != canonical(presented_calling):
            return "calling_mismatch", None
        if canonical(km.called) != canonical(own_number):
            return "called_mismatch", None
    shared = sk_R.exchange(X25519PublicKey.from_public_bytes(km.epk_O))
    key = _kdf(shared, b"bvi-kc" + sid)
    try:
        k_c = ChaCha20Poly1305(key).decrypt(km.nonce, km.ct, sid)
    except InvalidTag:
        return "bad_sig", None
    return "ok", k_c

# ------------------------------------------------------------------ stream
@dataclass
class Block:
    idx: int; offset: int; nframes: int; bits: bytes; tag: bytes

@dataclass
class Stream:
    version: str
    blocks: list = field(default_factory=list)
    term: tuple = None            # (total_blocks, total_frames, tag) for v2

    def overhead_bytes(self):
        per = TAG_BYTES + (2 if self.version in ("v2", "v2_noterm") else 0)   # 2-byte frame count (digest_auth_v2 wire format)
        return per * len(self.blocks) + (8 + TAG_BYTES if self.term else 0)

def _block_tag(k, version, sid, idx, offset, nframes, bits):
    if version == "v1":
        msg = H(b"blk", sid, idx, bits)
    else:
        msg = H(b"blk2", sid, idx, offset, nframes, bits)
    return hmac.new(k, msg, hashlib.sha256).digest()[:TAG_BYTES]

def make_stream(k_c, sid, seconds, version):
    st = Stream(version)
    for i in range(seconds):
        bits = os.urandom(100)                       # 800 bits of fingerprint per second
        st.blocks.append(Block(i, i * FRAMES_PER_BLOCK, FRAMES_PER_BLOCK, bits,
                               _block_tag(k_c, version, sid, i, i * FRAMES_PER_BLOCK, FRAMES_PER_BLOCK, bits)))
    if version == "v2":
        total = seconds * FRAMES_PER_BLOCK
        st.term = (seconds, total, hmac.new(k_c, H(b"end", sid, seconds, total), hashlib.sha256).digest()[:TAG_BYTES])
    return st

def verify_stream(k_c, sid, st, version, verdict_at=None):
    """Returns (status, n_blocks_evaluated).
    status: ok, bad_tag, gap, unterminated, count_mismatch.
    v1 has no notion of an authenticated end: the verdict covers whatever authenticated prefix exists
    when the verdict is taken (verdict_at seconds), which is what makes premature verification possible."""
    blocks = st.blocks if verdict_at is None else st.blocks[:verdict_at]
    expected = 0
    for b in blocks:
        if b.tag != _block_tag(k_c, version, sid, b.idx, b.offset, b.nframes, b.bits):
            return "bad_tag", expected
        if version != "v1" and (b.idx != expected or b.offset != expected * FRAMES_PER_BLOCK):
            return "gap", expected
        if version == "v1" and b.idx != expected:
            return "gap", expected
        expected += 1
    if version == "v2":
        if st.term is None:
            return "unterminated", expected
        n, total, tg = st.term
        if tg != hmac.new(k_c, H(b"end", sid, n, total), hashlib.sha256).digest()[:TAG_BYTES]:
            return "bad_tag", expected
        if n != len(st.blocks) or total != sum(b.nframes for b in st.blocks):
            return "count_mismatch", expected
    return "ok", expected
