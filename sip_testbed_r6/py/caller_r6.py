"""
Round-6 caller = originating organisation (did:bvi:testbank, numbers +61312345678 and +61312340000) + experiment driver.

Every BVI call carries BOTH protocol versions, so the recipient judges each call under all eight configurations:
  key message v1 (K) and v2 (L, signing the calling and called numbers); every 1 s fingerprint block tagged with
  v1 (B) and v2 (C) tags; the v2 termination record (E) at the end of the media.
Path: caller -> p1 (hop 0) -> p2 (hop 1, compromised in 'rewrite'/'launder') -> p3 (hop 2) -> callee.
The scenario drives only the simulated network and attacker (relay, proxies, off-path writers, forged BYE);
the callee never uses it.
"""
import argparse, audioop, csv, glob, json, os, random, socket, struct, threading, time, urllib.request
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import channel
import digest_auth as da
import digest_auth_v2 as d2
import fingerprint as fp
import sipmsg as sm
import wire

NUMBER, OTHER_NUMBER = "+61312345678", "+61312340000"
CALLEE_NUMBER, MULE_NUMBER = "+61400000001", "+61400000999"
BVI = os.environ.get("BVI_URL", "http://bvi:8080")
FIRST_HOP = (os.environ.get("FIRST_HOP", "p1"), int(os.environ.get("FIRST_HOP_PORT", "5060")))
RELAY = os.environ.get("RELAY_HOST", "relay")
_RP = int(os.environ.get("RELAY_PORT_BASE", "40000"))
RELAY_RTP, RELAY_DIG, RELAY_CTL = (RELAY, _RP), (RELAY, _RP + 2), (RELAY, _RP + 100)
ME, MY_PORT, CALLEE = os.environ.get("CALLER_HOST", "caller"), int(os.environ.get("CALLER_PORT", "5060")), os.environ.get("CALLEE_HOST", "callee")
CALLEE_SIP_PORT = int(os.environ.get("CALLEE_SIP_PORT", "5060"))
DATA, RESULTS_DIR = os.environ.get("DATA", "/data"), os.environ.get("RESULTS", "/results")
CH = lambda s: da.keccak256(s.encode())

# scenario -> network / attacker behaviour
SCENARIOS = {
    "honest":             dict(),
    "rewrite":            dict(),                                   # p2 rewrites P-Asserted-Identity, does not attest
    "launder":            dict(offpath="launder"),                  # + an off-path translator bridges p2's hop
    "false_record":       dict(offpath="false"),                    # honest call + contradicting off-path record
    "relay_session":      dict(called=MULE_NUMBER),                 # session the organisation opened to another number
    "missing_records":    dict(),                                   # only p2 attests (chain service policy)
    "transcode_declared": dict(chain="amr122"),                     # p2 transcodes through AMR-NB 12.2 and declares it
    "transcode_silent":   dict(chain="amr122"),                     # the same, p2 does not attest
    "mobile_origin":      dict(chain="amr122", origin="amr122"),    # AMR mobile origin, transcoded to G.711 by p1
    "loss5":              dict(loss=0.05),
    "substitute":         dict(sub=True),
    "splice3s":           dict(sub=True),
    "strip":              dict(),
    "truncate":           dict(trunc=6.0),                          # relay stops forwarding at 6 s
    "injected_bye":       dict(bye_at=5.0),                         # forged BYE to the callee at 5 s
}
if os.environ.get("LOCAL_TEST"):                                     # local harness test only (no AMR encoder there)
    SCENARIOS["_transcode_opus"] = dict(chain="opus16")


def post(path, obj):
    req = urllib.request.Request(BVI + path, json.dumps(obj).encode(), {"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


class Caller:
    def __init__(self):
        self.sk = Ed25519PrivateKey.generate()
        self.pub = self.sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.did = bytes.fromhex(post("/setup", {"pubKey": "0x" + self.pub.hex(), "numbers": [NUMBER, OTHER_NUMBER]})["did"][2:])
        self.sip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sip.bind(("0.0.0.0", MY_PORT)); self.sip.settimeout(15)
        self.media = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def wait_final(self, call_id, method):
        while True:
            m = sm.parse(self.sip.recvfrom(65535)[0])
            if not m.is_request and m.get("Call-ID") == call_id and m.cseq_method == method and m.status >= 200:
                return m

    def call(self, bvi_on, scenario, audio=None, substitute=None):
        cfg = SCENARIOS.get(scenario, {})
        cid, tag = sm.rand(16) + "@caller", sm.rand(8)
        sid = da.keccak256(os.urandom(32) + CH(NUMBER))
        if audio is not None:
            self.media.sendto(f"SCEN {scenario} {substitute or '-'} {cfg.get('chain', '-')} {cfg.get('loss', 0.0)} "
                              f"{cfg.get('trunc', '-')}".encode(), RELAY_CTL)
            time.sleep(0.2)
        if cfg.get("offpath"):                                       # written before the INVITE reaches the callee
            out = OTHER_NUMBER if cfg["offpath"] == "launder" else "+61399999999"
            post("/offpath", {"sid": "0x" + sid.hex(), "did": "0x" + self.did.hex(), "kind": cfg["offpath"],
                              "inId": NUMBER, "outId": out})
        sdp = b"v=0\r\no=- 0 0 IN IP4 relay\r\ns=-\r\nc=IN IP4 relay\r\nt=0 0\r\nm=audio 40000 RTP/AVP 0\r\n"
        hs = [("Via", f"SIP/2.0/UDP {ME}:{MY_PORT};branch=z9hG4bK{sm.rand()};rport"), ("Max-Forwards", "70"),
              ("From", f"<sip:{NUMBER}@bvi.test>;tag={tag}"), ("To", f"<sip:{CALLEE_NUMBER}@bvi.test>"),
              ("Call-ID", cid), ("CSeq", "1 INVITE"), ("Contact", f"<sip:caller@{ME}:{MY_PORT}>"),
              ("P-Asserted-Identity", f"<sip:{NUMBER}@bvi.test>"),
              ("X-BVI", "1" if bvi_on else "0"), ("X-BVI-DID", "0x" + self.did.hex()),
              ("X-BVI-SID", "0x" + sid.hex()), ("X-BVI-PubKey", "0x" + self.pub.hex()),
              ("X-Scenario", scenario), ("X-Media", "1" if audio is not None else "0"), ("Content-Type", "application/sdp")]
        t0 = time.perf_counter()
        self.sip.sendto(sm.Msg(f"INVITE sip:callee@{CALLEE}:5060 SIP/2.0", hs, sdp).encode(), FIRST_HOP)
        ok = self.wait_final(cid, "INVITE")
        setup_ms = (time.perf_counter() - t0) * 1000
        routes = list(reversed(ok.get_all("Record-Route"))); contact = sm.strip_brackets(ok.get("Contact"))
        dlg = [("From", f"<sip:{NUMBER}@bvi.test>;tag={tag}"), ("To", ok.get("To")), ("Call-ID", cid)]
        nxt = sm.uri_host_port(routes[0]) if routes else sm.uri_host_port(contact)
        via = lambda: ("Via", f"SIP/2.0/UDP {ME}:{MY_PORT};branch=z9hG4bK{sm.rand()};rport")
        self.sip.sendto(sm.Msg(f"ACK {contact} SIP/2.0", [via(), ("Max-Forwards", "70")] + [("Route", r) for r in routes]
                               + dlg + [("CSeq", "1 ACK")]).encode(), nxt)
        rec = {"call_id": cid, "bvi": int(bvi_on), "scenario": scenario, "setup_ms": round(setup_ms, 3),
               "verify_ms": ok.get("X-BVI-Verify-Ms"), "verify_linked_ms": ok.get("X-BVI-Verify-Linked-Ms"),
               "attest_ms": ";".join(ok.get_all("X-BVI-Attest-Ms"))}
        if audio is not None and bvi_on:
            forged = None
            if cfg.get("bye_at"):
                # in-path attacker: a BYE with the dialog's identifiers, sent straight to the callee
                bye = sm.Msg(f"BYE {contact} SIP/2.0", [via(), ("Max-Forwards", "70")] + dlg + [("CSeq", "2 BYE")])
                forged = threading.Timer(cfg["bye_at"], lambda: self.sip.sendto(bye.encode(), (CALLEE, CALLEE_SIP_PORT)))
                forged.start()
            self.stream(sid, bytes.fromhex(ok.get("X-BVI-EpkR")[2:]), bytes.fromhex(ok.get("X-BVI-EpkR2")[2:]), audio,
                        da.CODEC[cfg.get("origin", "g711u")], cfg.get("called", CALLEE_NUMBER))
            time.sleep(2.0)                                          # let the relay drain before hanging up
        bye = sm.Msg(f"BYE {contact} SIP/2.0", [via(), ("Max-Forwards", "70")] + [("Route", r) for r in routes] + dlg + [("CSeq", "3 BYE")])
        self.sip.sendto(bye.encode(), nxt)
        try:
            rec["bye"] = str(self.wait_final(cid, "BYE").status)
        except socket.timeout:
            rec["bye"] = "timeout"
        return rec

    def stream(self, sid, epk1, epk2, audio, codec, called):
        k1, km1 = da.Originator(self.sk).start_session(self.did, sid, epk1, codec)
        k2, km2 = d2.OriginatorV2(self.sk).start_session(self.did, sid, epk2, codec, calling=NUMBER, called=called)
        self.media.sendto(wire.pack_key(b"K", sid, km1), RELAY_DIG)
        self.media.sendto(wire.pack_key(b"L", sid, km2, NUMBER, called), RELAY_DIG)
        bits, act = fp.sender_fingerprint(audio)
        v2_blocks, (tb, tf, ttag) = d2.tag_stream_v2(k2, sid, bits, act)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        n_pkt = len(audio) // 160; ssrc, t_next = random.getrandbits(32), time.perf_counter()
        for i in range(n_pkt):
            hdr = struct.pack("!BBHII", 0x80, 0, i & 0xFFFF, i * 160, ssrc)
            self.media.sendto(hdr + audioop.lin2ulaw(pcm[i * 320:(i + 1) * 320], 2), RELAY_RTP)
            if (i + 1) % 50 == 0 or i == n_pkt - 1:
                b = i // 50; fb, fa = bits[b * 50:(b + 1) * 50], act[b * 50:(b + 1) * 50]
                if len(fb):
                    self.media.sendto(wire.pack_block(b"B", sid, b, fb, fa, da.block_tag(k1, sid, b, fb, fa)), RELAY_DIG)
                    self.media.sendto(wire.pack_block(b"C", sid, b, fb, fa, v2_blocks[b][1]), RELAY_DIG)
            t_next += 0.020
            time.sleep(max(0.0, t_next - time.perf_counter()))
        self.media.sendto(wire.pack_end(sid, tb, tf, ttag), RELAY_DIG)


def pick_audio(root, n, seconds, rng):
    files = sorted(glob.glob(os.path.join(root, "**", "*.flac"), recursive=True)); rng.shuffle(files); out = []
    for f in files:
        x = channel.load_audio(f)
        if len(x) >= seconds * 8000:
            out.append((f, x[: seconds * 8000]))
        if len(out) == n:
            return out
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay-calls", type=int, default=100); ap.add_argument("--media-calls", type=int, default=5)
    ap.add_argument("--seconds", type=int, default=10); ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    a = ap.parse_args(); rng = random.Random(a.seed); os.makedirs(RESULTS_DIR, exist_ok=True)
    avail = channel.available_codecs()
    if not avail.get("amr122") and not os.environ.get("LOCAL_TEST"):
        raise SystemExit("STOP: this container's FFmpeg has no AMR-NB encoder; the transcoding scenarios would be invalid")
    c = Caller(); print("[caller] organisation registered; warming up", flush=True)
    for _ in range(5):
        c.call(True, "warmup"); c.call(False, "warmup")
    rows = [c.call(i % 2 == 1, "honest") for i in range(a.delay_calls)]
    if rows:
        with open(f"{RESULTS_DIR}/setup_delay.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["call_id", "bvi", "scenario", "setup_ms", "verify_ms", "verify_linked_ms", "attest_ms", "bye"],
                               extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    scen = a.scenarios.split(",")
    speech = pick_audio(os.path.join(DATA, "LibriSpeech/dev-clean"), a.media_calls * len(scen), a.seconds, rng)
    subs = sorted(glob.glob(os.path.join(DATA, "asvspoof_spoof_r5/*.flac"))); rng.shuffle(subs)
    media, k = [], 0
    for s in scen:
        for j in range(a.media_calls):
            f, x = speech[k % len(speech)]; k += 1
            sub = subs[k % len(subs)] if SCENARIOS[s].get("sub") else None
            r = c.call(True, s, audio=x, substitute=sub)
            r.update(audio=os.path.basename(f), substitute=os.path.basename(sub) if sub else ""); media.append(r)
            print(f"[caller] {s:18s} call {j + 1}/{a.media_calls}  setup {r['setup_ms']:.1f} ms", flush=True)
            time.sleep(3.0)                                          # callee verdict before the next call
    with open(f"{RESULTS_DIR}/media_calls.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["call_id", "bvi", "scenario", "setup_ms", "verify_ms", "verify_linked_ms", "attest_ms",
                                           "bye", "audio", "substitute"], extrasaction="ignore"); w.writeheader(); w.writerows(media)
    print("[caller] done", flush=True)


if __name__ == "__main__":
    main()
