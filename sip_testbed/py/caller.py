"""
Caller = originating organisation (did:bvi:testbank, numbers +61312345678 and +61312340000)
and experiment driver.

  Delay experiment: N calls alternating BVI off / on (no media). Setup delay = INVITE -> 200 OK.
  Attack demo:      scenarios honest, rewrite, substitute, splice3s, strip; 10 s of LibriSpeech
                    dev-clean speech per call, sent as G.711 mu-law RTP through the carrier relay,
                    with the key message and authenticated digest blocks.

Path: caller -> p1 (hop 0) -> p2 (hop 1, compromised in 'rewrite') -> p3 (hop 2) -> callee.
"""
import argparse, csv, glob, json, os, random, socket, struct, time, urllib.request
import audioop
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import channel
import digest_auth as da
import fingerprint as fp
import sipmsg as sm

NUMBER = "+61312345678"
OTHER_NUMBER = "+61312340000"   # also authorised for the same organisation (see README: rewrite scenario)
BVI = os.environ.get("BVI_URL", "http://bvi:8080")
FIRST_HOP = (os.environ.get("FIRST_HOP", "p1"), int(os.environ.get("FIRST_HOP_PORT", "5060")))
RELAY = os.environ.get("RELAY_HOST", "relay")
RELAY_RTP, RELAY_DIG, RELAY_CTL = (RELAY, 40000), (RELAY, 40002), (RELAY, 40100)
ME, MY_PORT = os.environ.get("CALLER_HOST", "caller"), int(os.environ.get("CALLER_PORT", "5060"))
DATA = os.environ.get("DATA", "/data")
RESULTS_DIR = os.environ.get("RESULTS", "/results")
CALLEE = os.environ.get("CALLEE_HOST", "callee")
CH = lambda s: da.keccak256(s.encode())


def post(path, obj):
    req = urllib.request.Request(BVI + path, json.dumps(obj).encode(), {"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


class Caller:
    def __init__(self):
        self.sk = Ed25519PrivateKey.generate()
        self.pub = self.sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.did = bytes.fromhex(post("/setup", {"pubKey": "0x" + self.pub.hex(),
                                                 "numbers": [NUMBER, OTHER_NUMBER]})["did"][2:])
        self.sip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sip.bind(("0.0.0.0", MY_PORT))
        self.sip.settimeout(10)
        self.media = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def wait_final(self, call_id, method):
        while True:
            data, addr = self.sip.recvfrom(65535)
            m = sm.parse(data)
            if m.is_request or m.get("Call-ID") != call_id or m.cseq_method != method:
                continue
            if m.status >= 200:
                return m

    def call(self, bvi_on, scenario, audio=None, substitute=None):
        cid, tag = sm.rand(16) + "@caller", sm.rand(8)
        sid = da.keccak256(os.urandom(32) + CH(NUMBER))
        if audio is not None:
            msg = f"SCEN {scenario} {substitute or '-'}".encode()
            self.media.sendto(msg, RELAY_CTL)
            time.sleep(0.2)
        sdp = b"v=0\r\no=- 0 0 IN IP4 relay\r\ns=-\r\nc=IN IP4 relay\r\nt=0 0\r\nm=audio 40000 RTP/AVP 0\r\n"
        hs = [("Via", f"SIP/2.0/UDP {ME}:{MY_PORT};branch=z9hG4bK{sm.rand()};rport"), ("Max-Forwards", "70"),
              ("From", f"<sip:{NUMBER}@bvi.test>;tag={tag}"), ("To", "<sip:callee@bvi.test>"),
              ("Call-ID", cid), ("CSeq", "1 INVITE"), ("Contact", f"<sip:caller@{ME}:{MY_PORT}>"),
              ("P-Asserted-Identity", f"<sip:{NUMBER}@bvi.test>"),
              ("X-BVI", "1" if bvi_on else "0"), ("X-BVI-DID", "0x" + self.did.hex()),
              ("X-BVI-SID", "0x" + sid.hex()), ("X-BVI-PubKey", "0x" + self.pub.hex()),
              ("X-Scenario", scenario), ("X-Media", "1" if audio is not None else "0"),
              ("Content-Type", "application/sdp")]
        inv = sm.Msg(f"INVITE sip:callee@{CALLEE}:5060 SIP/2.0", hs, sdp)
        t0 = time.perf_counter()
        self.sip.sendto(inv.encode(), FIRST_HOP)
        ok = self.wait_final(cid, "INVITE")
        setup_ms = (time.perf_counter() - t0) * 1000
        # ACK and later BYE follow the route set (reverse of Record-Route for the UAC)
        routes = list(reversed(ok.get_all("Record-Route")))
        contact = sm.strip_brackets(ok.get("Contact"))
        to = ok.get("To")
        dlg = [("From", f"<sip:{NUMBER}@bvi.test>;tag={tag}"), ("To", to), ("Call-ID", cid)]
        nxt = sm.uri_host_port(routes[0]) if routes else sm.uri_host_port(contact)
        ack = sm.Msg(f"ACK {contact} SIP/2.0", [("Via", f"SIP/2.0/UDP {ME}:{MY_PORT};branch=z9hG4bK{sm.rand()};rport"),
                                                ("Max-Forwards", "70")] + [("Route", r) for r in routes] + dlg +
                     [("CSeq", "1 ACK")])
        self.sip.sendto(ack.encode(), nxt)
        rec = {"call_id": cid, "bvi": int(bvi_on), "scenario": scenario, "setup_ms": round(setup_ms, 3),
               "verify_ms": ok.get("X-BVI-Verify-Ms"), "callee_l1_l2": ok.get("X-BVI-Verdict-L1-L2"),
               "attest_ms": ";".join(ok.get_all("X-BVI-Attest-Ms"))}
        if audio is not None and bvi_on:
            epk_r = bytes.fromhex(ok.get("X-BVI-EpkR")[2:])
            self.stream(sid, epk_r, audio)
        bye = sm.Msg(f"BYE {contact} SIP/2.0", [("Via", f"SIP/2.0/UDP {ME}:{MY_PORT};branch=z9hG4bK{sm.rand()};rport"),
                                                ("Max-Forwards", "70")] + [("Route", r) for r in routes] + dlg +
                     [("CSeq", "2 BYE")])
        self.sip.sendto(bye.encode(), nxt)
        try:
            rec["bye"] = str(self.wait_final(cid, "BYE").status)
        except socket.timeout:
            rec["bye"] = "timeout"
        return rec

    def stream(self, sid, epk_r, audio):
        k_c, km = da.Originator(self.sk).start_session(self.did, sid, epk_r, da.CODEC["g711u"])
        self.media.sendto(b"K" + sid + km.epk_o + bytes([km.codec]) + km.ct + km.sig, RELAY_DIG)
        bits, act = fp.sender_fingerprint(audio)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        n_pkt = len(audio) // 160
        ssrc, t_next = random.getrandbits(32), time.perf_counter()
        for i in range(n_pkt):
            payload = audioop.lin2ulaw(pcm[i * 320:(i + 1) * 320], 2)
            hdr = struct.pack("!BBHII", 0x80, 0, i & 0xFFFF, i * 160, ssrc)
            self.media.sendto(hdr + payload, RELAY_RTP)
            if (i + 1) % 50 == 0 or i == n_pkt - 1:
                b = i // 50
                fb, fa = bits[b * 50:(b + 1) * 50], act[b * 50:(b + 1) * 50]
                if len(fb):
                    tag = da.block_tag(k_c, sid, b, fb, fa)
                    self.media.sendto(b"B" + sid + struct.pack("!I", b) + bytes([len(fb)]) +
                                      da._block_bytes(fb, fa) + tag, RELAY_DIG)
            t_next += 0.020
            time.sleep(max(0.0, t_next - time.perf_counter()))
        time.sleep(0.3)


def pick_audio(root, n, seconds, rng):
    files = sorted(glob.glob(os.path.join(root, "**", "*.flac"), recursive=True))
    rng.shuffle(files)
    out = []
    for f in files:
        x = channel.load_audio(f)
        if len(x) >= seconds * 8000:
            out.append((f, x[: seconds * 8000]))
        if len(out) == n:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay-calls", type=int, default=200)
    ap.add_argument("--media-calls", type=int, default=5, help="per attack scenario")
    ap.add_argument("--seconds", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260909)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    c = Caller()
    print("[caller] organisation registered; warming up", flush=True)
    for _ in range(5):
        c.call(True, "warmup"); c.call(False, "warmup")

    rows = []
    for i in range(a.delay_calls):
        on = (i % 2 == 1)
        rows.append(c.call(on, "honest"))
        if (i + 1) % 20 == 0:
            print(f"[caller] delay calls {i + 1}/{a.delay_calls}", flush=True)
    if a.delay_calls == 0:
        print("[caller] --delay-calls 0: keeping the existing setup_delay.csv", flush=True)
    else:
      with open(f"{RESULTS_DIR}/setup_delay.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["call_id", "bvi", "scenario", "setup_ms", "verify_ms", "callee_l1_l2",
                                           "attest_ms", "bye"], extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    speech = pick_audio(os.path.join(DATA, "LibriSpeech/dev-clean"), a.media_calls * 5, a.seconds, rng)
    subs = sorted(glob.glob(os.path.join(DATA, "asvspoof_spoof_r5/*.flac")))
    rng.shuffle(subs)
    media_rows, k = [], 0
    for scen in ["honest", "rewrite", "substitute", "splice3s", "strip"]:
        for j in range(a.media_calls):
            f, x = speech[k % len(speech)]; k += 1
            sub = subs[k % len(subs)] if scen in ("substitute", "splice3s") else None
            r = c.call(True, scen, audio=x, substitute=sub)
            r.update(audio=os.path.basename(f), substitute=os.path.basename(sub) if sub else "")
            media_rows.append(r)
            print(f"[caller] {scen:10s} call {j + 1}/{a.media_calls}  setup {r['setup_ms']:.1f} ms  "
                  f"L1,L2 at setup = {r['callee_l1_l2']}", flush=True)
    with open(f"{RESULTS_DIR}/media_calls.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["call_id", "bvi", "scenario", "setup_ms", "verify_ms", "callee_l1_l2",
                                           "attest_ms", "bye", "audio", "substitute"], extrasaction="ignore")
        w.writeheader(); w.writerows(media_rows)
    print("[caller] done", flush=True)


if __name__ == "__main__":
    main()
