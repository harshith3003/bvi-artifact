"""
Callee (verifying recipient). Its carrier is p3, hop index 2.

At INVITE (if X-BVI: 1): live Layer 1 + route check via the BVI service (JSON-RPC reads),
fresh X25519 key for k_c delivery, then 200 OK carrying epk_R.
During media: RTP (G.711 mu-law) on :40000; key message + authenticated digest
blocks on :40002 (both arrive through the carrier media relay).
At BYE: decrypt k_c, check every block tag, compare the authenticated sender
fingerprint with what was heard (frames aligned by RTP timestamp), apply the
content threshold for the worst codec declared on the path, and write the verdict.
The X-Scenario header is logged as a label only; it never enters a decision.
"""
import audioop, hmac, json, os, select, socket, struct, time, urllib.request
import numpy as np

import digest_auth as da
import fingerprint as fp
import sipmsg as sm

BVI = os.environ.get("BVI_URL", "http://bvi:8080")
TERMINATING_HOP = 2
RESULTS = os.path.join(os.environ.get("RESULTS", "/results"), "calls.jsonl")
ME = os.environ.get("CALLEE_HOST", "callee")
SIP_PORT, RTP_PORT, DIG_PORT = (int(os.environ.get(k, d)) for k, d in (("SIP_PORT", "5060"), ("RTP_PORT", "40000"), ("DIG_PORT", "40002")))


def post(path, obj):
    req = urllib.request.Request(BVI + path, json.dumps(obj).encode(), {"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def get(path):
    return json.loads(urllib.request.urlopen(BVI + path, timeout=10).read())


def unpack_block(packed, nframes):
    bits = np.unpackbits(np.frombuffer(packed, np.uint8))[: nframes * 17].reshape(nframes, 17).astype(bool)
    return bits[:, :16], bits[:, 16]


def finalize(call):
    inv = call["invite"]
    did = bytes.fromhex(inv.get("X-BVI-DID")[2:])
    sid = bytes.fromhex(inv.get("X-BVI-SID")[2:])
    pub = bytes.fromhex(inv.get("X-BVI-PubKey")[2:])
    # received audio, placed by RTP sequence number (lost packet -> repeat previous)
    pk = call["rtp"]
    n_pkts = (max(pk) - min(pk) + 1) if pk else 0
    pcm, prev, base = [], b"\x00" * 320, min(pk) if pk else 0
    for i in range(n_pkts):
        lin = audioop.ulaw2lin(pk[base + i], 2) if (base + i) in pk else prev
        pcm.append(lin); prev = lin
    y = np.frombuffer(b"".join(pcm), dtype=np.int16).astype(np.float64) / 32768.0
    # key message + blocks
    key_ok, codec, k_c, reason = False, None, None, ""
    if call["key"] is not None:
        try:
            r = call["recipient"]
            m = call["key"]
            msg = da.KeyMsg(m[:32], m[32], m[33:81], m[81:145])
            onchain = bytes.fromhex(get(f"/resolve?did=0x{did.hex()}")["pubKeyHash"][2:])
            k_c, codec = r.open(msg, did, sid, pub, onchain)
            key_ok = True
        except Exception as e:
            reason = f"key message rejected: {e}"
    else:
        reason = "no key message (stream stripped)"
    expected_blocks = len(y) // (160 * 50) if len(y) else 0
    tags_ok, s_bits, s_act = [], [], []
    for idx in range(expected_blocks):
        b = call["blocks"].get(idx)
        if b is None or not key_ok:
            tags_ok.append(False); continue
        nfr, packed, tag = b
        bits, act = unpack_block(packed, nfr)
        tags_ok.append(hmac.compare_digest(da.block_tag(k_c, sid, idx, bits, act), tag))
        s_bits.append(bits); s_act.append(act)
    status = da.stream_status(key_ok, tags_ok, expected_blocks)
    max_w, theta, basis = None, None, None
    if status == "unverifiable":
        content = "unverifiable"
        reason = reason or "a block is missing or its tag failed"
    else:
        sb, sa = np.concatenate(s_bits), np.concatenate(s_act)
        rb, rs = fp.receiver_view(y)
        err, cnt, act = fp.frame_errors(sb, sa, rb, rs)
        wb = fp.window_bers(err, cnt, act)
        conc = wb[~np.isnan(wb)]
        th = post("/threshold", {"sid": "0x" + sid.hex(), "originCodec": codec, "terminatingHop": TERMINATING_HOP})
        theta, basis = th["theta"], th["basis"]
        if conc.size == 0:
            content = "unknown"
        else:
            max_w = float(conc.max())
            content = "fail" if max_w > theta else "pass"
    l1, l2 = call.get("l1"), call.get("l2")
    if "fail" in (l1, l2, content):
        outcome = "fail"
    elif content == "unverifiable":
        outcome = "not verified"
    else:
        outcome = "verified"
    rec = {"call_id": inv.get("Call-ID"), "label": inv.get("X-Scenario"), "presented_id": call["presented"],
           "l1": l1, "l2": l2, "route_reason": call.get("route_reason"), "content": content,
           "max_window_ber": max_w, "theta": theta, "theta_basis": basis, "origin_codec": codec,
           "blocks_expected": expected_blocks, "blocks_ok": int(sum(tags_ok)), "outcome": outcome,
           "verify_ms": call.get("verify_ms"), "note": reason}
    with open(RESULTS, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"[callee] {rec['label']:10s} L1={l1} L2={l2} content={content} "
          f"(max BER {max_w if max_w is None else round(max_w, 3)}, theta {theta}) -> {outcome}", flush=True)


def main():
    sip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sip.bind(("0.0.0.0", SIP_PORT))
    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); rtp.bind(("0.0.0.0", RTP_PORT))
    dig = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dig.bind(("0.0.0.0", DIG_PORT))
    calls, current = {}, None
    print("[callee] ready", flush=True)

    def done(call):
        # verdict once per call: on BYE, or 2 s after the media stops (whichever comes first)
        if call.get("done") or call["invite"].get("X-BVI") != "1" or call["invite"].get("X-Media") != "1":
            return
        call["done"] = True
        try:
            finalize(call)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"[callee] finalize error: {e}", flush=True)

    while True:
        ready, _, _ = select.select([sip, rtp, dig], [], [], 0.5)
        if current is not None and current.get("last_media") and time.time() - current["last_media"] > 2.0:
            done(current)
        for s in ready:
            data, addr = s.recvfrom(65535)
            if s is rtp and current is not None:
                seq = struct.unpack("!H", data[2:4])[0]
                current["rtp"][seq] = data[12:]
                current["last_media"] = time.time()
            elif s is dig and current is not None:
                current["last_media"] = time.time()
                if data[:1] == b"K":
                    current["key"] = data[33:]
                elif data[:1] == b"B":
                    idx = struct.unpack("!I", data[33:37])[0]; nfr = data[37]
                    current["blocks"][idx] = (nfr, data[38:-8], data[-8:])
            elif s is sip:
                m = sm.parse(data)
                if not m.is_request:
                    continue
                cid = m.get("Call-ID")
                if m.method == "INVITE":
                    call = {"invite": m, "rtp": {}, "blocks": {}, "key": None,
                            "presented": sm.user_of(m.get("P-Asserted-Identity", "")), "to_tag": sm.rand(8)}
                    extra = [("Contact", f"<sip:callee@{ME}:{SIP_PORT}>")]
                    if m.get("X-BVI") == "1":
                        t0 = time.perf_counter()
                        v = post("/verify", {"did": m.get("X-BVI-DID"), "presentedId": call["presented"],
                                             "sid": m.get("X-BVI-SID")})
                        call["recipient"] = da.Recipient()
                        call["verify_ms"] = (time.perf_counter() - t0) * 1000
                        call.update(l1=v["l1"], l2=v["l2"], route_reason=v["reason"])
                        extra += [("X-BVI-EpkR", "0x" + call["recipient"].epk.hex()),
                                  ("X-BVI-Verify-Ms", f"{call['verify_ms']:.2f}"),
                                  ("X-BVI-Verdict-L1-L2", f"{v['l1']},{v['l2']}")]
                        for a in m.get_all("X-BVI-Attest-Ms"):
                            extra.append(("X-BVI-Attest-Ms", a))
                    sdp = b"v=0\r\no=- 0 0 IN IP4 callee\r\ns=-\r\nc=IN IP4 callee\r\nt=0 0\r\nm=audio 40000 RTP/AVP 0\r\n"
                    extra.append(("Content-Type", "application/sdp"))
                    sip.sendto(sm.response(m, 200, "OK", extra, sdp, call["to_tag"]).encode(), addr)
                    calls[cid] = call; current = call
                elif m.method == "BYE":
                    print(f"[callee] BYE received for {cid}", flush=True)
                    sip.sendto(sm.response(m, 200, "OK").encode(), addr)
                    call = calls.pop(cid, None)
                    if call is not None:
                        done(call)
                        if call is current:
                            current = None
                # ACK: nothing to do


if __name__ == "__main__":
    main()
