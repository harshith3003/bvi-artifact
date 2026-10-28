"""
wire.py: the digest-channel messages (UDP, through the carrier media relay).
  K  v1 key message      K | sid(32) | epk_o(32) | codec(1) | ct(48) | sig(64)
  L  v2 key message      L | sid | epk_o | codec | ct | sig | len|calling | len|called      (numbers in clear, signed)
  B  v1 block            B | sid | idx(4) | nframes(1) | packed bits | tag(8)
  C  v2 block            C | sid | idx(4) | nframes(1) | packed bits | tag(8)             (tag over position + count)
  E  v2 termination      E | sid | total_blocks(4) | total_frames(4) | tag(8)
"""
import struct
import numpy as np
import digest_auth as da

def pack_key(kind, sid, km, calling="", called=""):
    out = kind + sid + km.epk_o + bytes([km.codec]) + km.ct + km.sig
    if kind == b"L":
        for n in (calling, called):
            b = n.encode(); out += struct.pack("!H", len(b)) + b
    return out

def unpack_key(data):
    """-> (kind, sid, KeyMsg, calling, called)"""
    kind, sid, m = data[:1], data[1:33], data[33:]
    msg = da.KeyMsg(m[:32], m[32], m[33:81], m[81:145]); calling = called = ""
    if kind == b"L":
        rest = m[145:]; n = struct.unpack("!H", rest[:2])[0]; calling = rest[2:2 + n].decode(); rest = rest[2 + n:]
        n = struct.unpack("!H", rest[:2])[0]; called = rest[2:2 + n].decode()
    return kind, sid, msg, calling, called

def pack_block(kind, sid, idx, bits, act, tag):
    return kind + sid + struct.pack("!I", idx) + bytes([len(bits)]) + da._block_bytes(bits, act) + tag

def unpack_block(data):
    """-> (kind, idx, bits[n,16], act[n], tag)"""
    idx = struct.unpack("!I", data[33:37])[0]; n = data[37]
    b = np.unpackbits(np.frombuffer(data[38:-8], np.uint8))[: n * 17].reshape(n, 17).astype(bool)
    return data[:1], idx, b[:, :16], b[:, 16], data[-8:]

def pack_end(sid, total_blocks, total_frames, tag):
    return b"E" + sid + struct.pack("!II", total_blocks, total_frames) + tag

def unpack_end(data):
    tb, tf = struct.unpack("!II", data[33:41]); return tb, tf, data[41:49]

def block_index(data):
    return struct.unpack("!I", data[33:37])[0] if data[:1] in (b"B", b"C") else None
