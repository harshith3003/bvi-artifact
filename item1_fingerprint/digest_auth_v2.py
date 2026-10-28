"""
digest_auth_v2.py: the round-6 corrections to digest_auth.py (BVI-R / BVI-B), kept beside the original so
BVI-0 stays reproducible and each correction can be switched off for the ablation.

Correction 1, number binding (key message v2)
    sig = Ed25519_sign(sk_org, "bvi-kc-v2" || did || sid || epk_R || epk_O || codec || ct
                                || len||calling || len||called)
    calling / called are canonical E.164 strings. The recipient checks calling == the presented calling number
    (canonicalised, so a declared national-format translation still matches) and called == its own number.
    Defeats relay of a session the organisation opened to a different number, and any rewrite of the calling
    number in transit, whatever the carriers write.

Correction 2, stream v2 (positions, counts, authenticated termination)
    tag_b  = HMAC-SHA256(k_c, "bvi-fp-v2" || sid || b || frame_offset || nframes || block bits)[:8]
    end    = HMAC-SHA256(k_c, "bvi-fp-end-v2" || sid || total_blocks || total_frames)[:8]
    Wire format: per block an 8-byte tag + 2-byte frame count (80 bit/s; total stream 930 bit/s, within the
    1,600 bit/s budget), plus one 16-byte termination record when the organisation ends the call.
    The verdict is final only after a valid termination whose counts match what arrived, so dropping the tail,
    injecting a BYE, or taking a verdict early cannot produce "verified".
    require_termination=False gives ablation 3 (v2 per-block checks without authenticated termination).

Statuses (both corrections): "ok" or "unverifiable" with a reason; unverifiable maps to "not verified".
"""
import hashlib, hmac, struct
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidSignature, InvalidTag
import os

from digest_auth import (KeyMsg, Recipient as RecipientV1, Originator as OriginatorV1, keccak256, _raw,
                         _wrap_key, _block_bytes, FRAMES_PER_BLOCK, TAG_BYTES, CODEC)

COUNT_BYTES = 2
END_BYTES = 8 + TAG_BYTES          # total blocks (4) + total frames (4) + tag


def canonical(num: str) -> str:
    """Canonical E.164 (Australian national format '0...' -> '+61...'); spaces removed."""
    n = num.replace(" ", "")
    return "+61" + n[1:] if n.startswith("0") else n


def _lp(s: str) -> bytes:
    b = canonical(s).encode()
    return struct.pack(">H", len(b)) + b


def _signed_bytes_v2(did, sid, epk_r, epk_o, codec, ct, calling, called):
    return b"bvi-kc-v2" + did + sid + epk_r + epk_o + bytes([codec]) + ct + _lp(calling) + _lp(called)


# ── key message ─────────────────────────────────────────────────────────────
class OriginatorV2(OriginatorV1):
    def start_session(self, did, sid, epk_r, codec=CODEC["g711u"], calling="", called=""):
        k_c = os.urandom(32)
        esk_o = X25519PrivateKey.generate(); epk_o = _raw(esk_o.public_key())
        shared = esk_o.exchange(X25519PublicKey.from_public_bytes(epk_r))
        ct = ChaCha20Poly1305(_wrap_key(shared, sid, epk_o, epk_r)).encrypt(b"\x00" * 12, k_c, did + sid)
        sig = self._sk.sign(_signed_bytes_v2(did, sid, epk_r, epk_o, codec, ct, calling, called))
        return k_c, KeyMsg(epk_o, codec, ct, sig)


class RecipientV2(RecipientV1):
    def open_bound(self, msg, did, sid, org_pubkey, onchain_pubkey_hash, presented_calling, own_number,
                   signed_calling, signed_called):
        """Key message v2. signed_calling / signed_called travel with the key message (in clear; they are
        covered by the signature). Raises ValueError with the reason, else returns (k_c, codec)."""
        if keccak256(org_pubkey) != onchain_pubkey_hash:
            raise ValueError("organisation key does not match the on-chain pubKeyHash")
        try:
            Ed25519PublicKey.from_public_bytes(org_pubkey).verify(
                msg.sig, _signed_bytes_v2(did, sid, self.epk, msg.epk_o, msg.codec, msg.ct, signed_calling, signed_called))
        except InvalidSignature:
            raise ValueError("key message signature invalid (wrong org, session, recipient key, numbers or ciphertext)")
        if canonical(signed_calling) != canonical(presented_calling):
            raise ValueError("calling number mismatch: presented number is not the one the organisation signed")
        if canonical(signed_called) != canonical(own_number):
            raise ValueError("called number mismatch: this session was opened to a different number (relay)")
        shared = self._esk.exchange(X25519PublicKey.from_public_bytes(msg.epk_o))
        try:
            k_c = ChaCha20Poly1305(_wrap_key(shared, sid, msg.epk_o, self.epk)).decrypt(b"\x00" * 12, msg.ct, did + sid)
        except InvalidTag:
            raise ValueError("k_c ciphertext does not authenticate")
        return k_c, msg.codec


# ── stream v2 ───────────────────────────────────────────────────────────────
def block_tag_v2(k_c, sid, index, offset, nframes, bits_block, act_block) -> bytes:
    m = b"bvi-fp-v2" + sid + struct.pack(">IIH", index, offset, nframes) + _block_bytes(bits_block, act_block)
    return hmac.new(k_c, m, hashlib.sha256).digest()[:TAG_BYTES]


def end_tag(k_c, sid, total_blocks, total_frames) -> bytes:
    m = b"bvi-fp-end-v2" + sid + struct.pack(">II", total_blocks, total_frames)
    return hmac.new(k_c, m, hashlib.sha256).digest()[:TAG_BYTES]


def tag_stream_v2(k_c, sid, bits, act):
    """Returns (blocks, termination). blocks: list of (nframes, tag). The last block may be partial."""
    n_frames = len(bits); blocks = []; b = 0
    for off in range(0, n_frames, FRAMES_PER_BLOCK):
        nf = min(FRAMES_PER_BLOCK, n_frames - off)
        blocks.append((nf, block_tag_v2(k_c, sid, b, off, nf, bits[off:off + nf], act[off:off + nf]))); b += 1
    return blocks, (len(blocks), n_frames, end_tag(k_c, sid, len(blocks), n_frames))


def verify_stream_v2(k_c, sid, bits, act, blocks, termination, require_termination=True):
    """Returns (status, reason). status 'ok' or 'unverifiable'.
    bits/act: what the recipient received and recomputed; blocks: received (nframes, tag) in arrival order."""
    off = 0
    for b, (nf, tag) in enumerate(blocks):
        if off + nf > len(bits):
            return "unverifiable", f"block {b} claims frames beyond the received audio"
        if not hmac.compare_digest(block_tag_v2(k_c, sid, b, off, nf, bits[off:off + nf], act[off:off + nf]), tag):
            return "unverifiable", f"block {b} tag fails (altered, reordered or misplaced)"
        off += nf
    if off != len(bits):
        return "unverifiable", "received audio extends beyond the authenticated blocks"
    if not require_termination:
        return "ok", "per-block checks only (no authenticated termination)"
    if termination is None:
        return "unverifiable", "no authenticated termination (stream cut, truncated or verdict requested early)"
    tb, tf, tg = termination
    if not hmac.compare_digest(end_tag(k_c, sid, tb, tf), tg):
        return "unverifiable", "termination record does not authenticate"
    if tb != len(blocks) or tf != off:
        return "unverifiable", f"termination says {tb} blocks / {tf} frames, received {len(blocks)} / {off}"
    return "ok", "all blocks and the termination verify"


def stream_overhead_bits_per_s(version):
    per_block = TAG_BYTES * 8 + (COUNT_BYTES * 8 if version in ("v2", "v2_noterm") else 0)
    return per_block   # one block per second
