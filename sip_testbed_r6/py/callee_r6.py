"""
Round-6 callee (verifying recipient, number +61400000001; its carrier is p3, hop 2).

At INVITE: Layer 1 + positional route (round-5 reads) and the linked route read (timed separately), two fresh
X25519 keys (v1 and v2 key messages), 200 OK.
During media: RTP (G.711 mu-law) on :40000; K/L key messages, B/C blocks and the E termination on :40002.
At BYE (real or forged): stop accepting media, then judge the call under all eight configurations (bvi_eval) from
what actually arrived. The X-Scenario header is logged as a label only and never enters a decision.
"""
import audioop, json, os, select, socket, struct, time, urllib.request
import numpy as np

import digest_auth as da
import digest_auth_v2 as d2
import sipmsg as sm
import wire
import bvi_eval as ev

BVI = os.environ.get("BVI_URL", "http://bvi:8080")
TERMINATING_HOP, OWN_NUMBER = 2, os.environ.get("OWN_NUMBER", "+61400000001")
RESULTS = os.path.join(os.environ.get("RESULTS", "/results"), "calls.jsonl")
ME = os.environ.get("CALLEE_HOST", "callee")
SIP_PORT, RTP_PORT, DIG_PORT = (int(os.environ.get(k, d)) for k, d in (("SIP_PORT", "5060"), ("RTP_PORT", "40000"), ("DIG_PORT", "40002")))
THRESHOLDS = None


def post(path, obj):
    req = urllib.request.Request(BVI + path, json.dumps(obj).encode(), {"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def get(path):
    return json.loads(urllib.request.urlopen(BVI + path, timeout=15).read())


def received_audio(pk):
    if not pk:
        return np.zeros(0)
    base, n = min(pk), max(pk) - min(pk) + 1
    pcm, prev = [], b"\x00" * 320
    for i in range(n):                                   # lost packet -> repeat the previous one
        lin = audioop.ulaw2lin(pk[base + i], 2) if (base + i) in pk else prev
        pcm.append(lin); prev = lin
    return np.frombuffer(b"".join(pcm), np.int16).astype(np.float64) / 32768.0


def finalize(call):
    inv = call["invite"]
    did, sid, pub = (bytes.fromhex(inv.get(h)[2:]) for h in ("X-BVI-DID", "X-BVI-SID", "X-BVI-PubKey"))
    onchain = bytes.fromhex(get(f"/resolve?did=0x{did.hex()}")["pubKeyHash"][2:])
    km1 = call["km"].get(b"K"); km2 = call["km"].get(b"L")
    keys = ev.open_keys(km1[0] if km1 else None, (km2[0], km2[1], km2[2]) if km2 else None,
                        call["r1"], call["r2"], did, sid, pub, onchain, call["presented"], OWN_NUMBER)
    signed_calling = km2[1] if km2 else call["presented"]
    lk = post("/verify_linked", {"did": "0x" + did.hex(), "presentedId": call["presented"], "sid": "0x" + sid.hex(),
                                 "signedCallingId": signed_calling})
    th = post("/thresholds", {"sid": "0x" + sid.hex(), "originV1": keys["v1"]["codec"],
                              "originV2": keys["v2"]["codec"] or keys["v2_nobind"]["codec"], "terminatingHop": TERMINATING_HOP})
    chain = dict(route_positional=call["l2"], route_linked=lk["bound"], route_linked_unbound=lk["unbound"],
                 carrier_theta=th["carrier"], chain_theta=th["chain"])
    y = received_audio(call["rtp"])
    res = ev.evaluate(dict(l1=call["l1"], keys=keys, sid=sid, blocks1=call["b1"], blocks2=call["b2"], term=call["term"], y=y),
                      chain, THRESHOLDS)
    rec = {"call_id": inv.get("Call-ID"), "label": inv.get("X-Scenario"), "presented_id": call["presented"],
           "l1": call["l1"], "route_positional": call["l2"], "route_linked": lk["bound"], "route_linked_unbound": lk["unbound"],
           "chain_complete": lk["complete"], "theta_carrier": th["carrier"], "theta_chain": th["chain"],
           "theta_bases": [th["carrier_basis"], th["chain_basis"]], "seconds_received": round(len(y) / 8000, 2),
           "blocks_v1": len(call["b1"]), "blocks_v2": len(call["b2"]), "termination": call["term"] is not None,
           "key_v1": keys["v1"]["why"] or "ok", "key_v2": keys["v2"]["why"] or "ok", "ended_by": call.get("ended_by"),
           "verify_ms": call.get("verify_ms"), "verify_linked_ms": call.get("verify_linked_ms"), "configs": res}
    with open(RESULTS, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"[callee] {rec['label']:18s} " + " | ".join(f"{k}: {v['outcome']}" for k, v in res.items()), flush=True)


def main():
    global THRESHOLDS
    THRESHOLDS = json.load(open(os.environ.get("THRESHOLDS", "/app/thresholds.json")))
    sip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sip.bind(("0.0.0.0", SIP_PORT))
    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); rtp.bind(("0.0.0.0", RTP_PORT))
    dig = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dig.bind(("0.0.0.0", DIG_PORT))
    calls, current = {}, None
    print("[callee] ready", flush=True)

    def done(call, why):
        if call.get("done") or call["invite"].get("X-BVI") != "1" or call["invite"].get("X-Media") != "1":
            return
        call["done"], call["ended_by"] = True, why
        try:
            finalize(call)
        except Exception as e:
            import traceback; traceback.print_exc(); print(f"[callee] finalize error: {e}", flush=True)

    while True:
        ready = select.select([sip, rtp, dig], [], [], 0.5)[0]
        if current is not None and current.get("last_media") and time.time() - current["last_media"] > 6.0:
            done(current, "media timeout"); current = None
        for s in ready:
            data, addr = s.recvfrom(65535)
            if s is rtp and current is not None:
                current["rtp"][struct.unpack("!H", data[2:4])[0]] = data[12:]; current["last_media"] = time.time()
            elif s is dig and current is not None:
                current["last_media"] = time.time(); kind = data[:1]
                if kind in (b"K", b"L"):
                    _, _, msg, calling, called = wire.unpack_key(data); current["km"][kind] = (msg, calling, called)
                elif kind in (b"B", b"C"):
                    _, idx, bits, act, tag = wire.unpack_block(data)
                    (current["b1"] if kind == b"B" else current["b2"])[idx] = (bits, act, tag)
                elif kind == b"E":
                    current["term"] = wire.unpack_end(data)
            elif s is sip:
                m = sm.parse(data)
                if not m.is_request:
                    continue
                cid = m.get("Call-ID")
                if m.method == "INVITE":
                    call = {"invite": m, "rtp": {}, "b1": {}, "b2": {}, "term": None, "km": {},
                            "presented": sm.user_of(m.get("P-Asserted-Identity", "")), "to_tag": sm.rand(8)}
                    extra = [("Contact", f"<sip:callee@{ME}:{SIP_PORT}>")]
                    if m.get("X-BVI") == "1":
                        q = {"did": m.get("X-BVI-DID"), "presentedId": call["presented"], "sid": m.get("X-BVI-SID")}
                        t0 = time.perf_counter(); v = post("/verify", q); call["verify_ms"] = (time.perf_counter() - t0) * 1000
                        t0 = time.perf_counter(); post("/verify_linked", {**q, "signedCallingId": call["presented"]})
                        call["verify_linked_ms"] = (time.perf_counter() - t0) * 1000
                        call["r1"], call["r2"] = da.Recipient(), d2.RecipientV2()
                        call.update(l1=v["l1"], l2=v["l2"])
                        extra += [("X-BVI-EpkR", "0x" + call["r1"].epk.hex()), ("X-BVI-EpkR2", "0x" + call["r2"].epk.hex()),
                                  ("X-BVI-Verify-Ms", f"{call['verify_ms']:.2f}"), ("X-BVI-Verify-Linked-Ms", f"{call['verify_linked_ms']:.2f}")]
                        for a in m.get_all("X-BVI-Attest-Ms"):
                            extra.append(("X-BVI-Attest-Ms", a))
                    sdp = b"v=0\r\no=- 0 0 IN IP4 callee\r\ns=-\r\nc=IN IP4 callee\r\nt=0 0\r\nm=audio 40000 RTP/AVP 0\r\n"
                    extra.append(("Content-Type", "application/sdp"))
                    sip.sendto(sm.response(m, 200, "OK", extra, sdp, call["to_tag"]).encode(), addr)
                    calls[cid] = call; current = call
                elif m.method == "BYE":
                    sip.sendto(sm.response(m, 200, "OK").encode(), addr)
                    call = calls.pop(cid, None)
                    if call is not None:                       # media after a BYE is no longer part of the call
                        if call is current:
                            current = None
                        done(call, "BYE")


if __name__ == "__main__":
    main()
