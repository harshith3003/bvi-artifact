"""
perf_round6.py: item 6, processing overhead of the real implementation (fingerprint.py, digest_auth.py,
digest_auth_v2.py) on this machine.

Measures, per 60 s call:
  * sender fingerprint (what the organisation computes and streams)
  * recipient check: receiver_view + frame_errors over the +-2-frame alignment search + window BERs + verdict
    (exactly the comparison used in run_ber.compare, pause rule on)
  * peak memory of the recipient check (tracemalloc)
  * key message setup + open, v1 (BVI-0) and v2 (number binding)
  * stream tagging and verification for 60 s, v1 and v2
and derives the cost per second of audio, the real-time factor and how many concurrent calls one core can check.
Audio: 60 s of amplitude-modulated noise at 8 kHz with 3-5 s pauses every 10 s (timing of the STFT,
filterbank and comparison does not depend on speech content). Seed 20260909.
Run: python3 perf_round6.py [--runs 30]  ->  ../results/round6_perf/perf.json and perf.md
"""
import argparse, json, os, platform, statistics, sys, time, tracemalloc
import numpy as np
import fingerprint as fp
import digest_auth as da
import digest_auth_v2 as d2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

SR, SECONDS = 8000, 60

def call_audio(rng):
    t = np.arange(SR * SECONDS) / SR
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t) ** 2
    x = rng.normal(0, 0.1, t.size) * env
    for start in range(10, SECONDS, 10):                     # listening pauses
        x[int(start * SR):int((start + rng.uniform(3, 5)) * SR)] *= 0.01
    return x.astype(np.float64)

def recipient_check(s_bits, s_act, y, theta):
    r_bits, r_strong = fp.receiver_view(y)
    best = None
    for sh in range(-2, 3):
        err, cnt, act = fp.frame_errors(s_bits, s_act, np.roll(r_bits, sh, axis=0), np.roll(r_strong, sh), pause_rule=True)
        tot = err.sum() / max(cnt.sum(), 1)
        if best is None or tot < best[0]:
            best = (tot, err, cnt, act)
    return fp.verdict(fp.window_bers(best[1], best[2], best[3]), theta)

def timed(fn, n):
    out = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); out.append((time.perf_counter() - t0) * 1000)
    return {"median_ms": statistics.median(out), "p95_ms": float(np.percentile(out, 95)), "runs": n}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", type=int, default=30); a = ap.parse_args()
    rng = np.random.default_rng(20260909)
    x = call_audio(rng); y = x + rng.normal(0, 0.002, x.size)
    s_bits, s_act = fp.sender_fingerprint(x)
    R = {}
    R["sender_fingerprint_60s"] = timed(lambda: fp.sender_fingerprint(x), a.runs)
    R["recipient_check_60s"] = timed(lambda: recipient_check(s_bits, s_act, y, 0.215), a.runs)
    tracemalloc.start(); recipient_check(s_bits, s_act, y, 0.215); _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    R["recipient_check_peak_MB"] = peak / 1e6

    sk = Ed25519PrivateKey.generate(); pk = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    onchain = da.keccak256(pk); did = da.keccak256(b"did:bvi:examplebank"); sid = da.keccak256(b"perf-session")
    def km_v1():
        r = da.Recipient(); k, m = da.Originator(sk).start_session(did, sid, r.epk); r.open(m, did, sid, pk, onchain)
    def km_v2():
        r = d2.RecipientV2(); k, m = d2.OriginatorV2(sk).start_session(did, sid, r.epk, calling="+61312345678", called="+61400000001")
        r.open_bound(m, did, sid, pk, onchain, "+61312345678", "+61400000001", "+61312345678", "+61400000001")
    R["key_message_v1"] = timed(km_v1, 200); R["key_message_v2"] = timed(km_v2, 200)
    k = os.urandom(32)
    t1 = da.tag_stream(k, sid, s_bits, s_act); b2, term = d2.tag_stream_v2(k, sid, s_bits, s_act)
    R["stream_tag_v1_60s"] = timed(lambda: da.tag_stream(k, sid, s_bits, s_act), 100)
    R["stream_tag_v2_60s"] = timed(lambda: d2.tag_stream_v2(k, sid, s_bits, s_act), 100)
    R["stream_verify_v1_60s"] = timed(lambda: da.verify_stream(k, sid, s_bits, s_act, t1), 100)
    R["stream_verify_v2_60s"] = timed(lambda: d2.verify_stream_v2(k, sid, s_bits, s_act, b2, term), 100)

    per_s = (R["recipient_check_60s"]["median_ms"] + R["stream_verify_v2_60s"]["median_ms"]) / SECONDS
    R["derived"] = {
        "recipient_ms_per_audio_second_v2": per_s,
        "real_time_factor": per_s / 1000,
        "concurrent_calls_per_core": 1000 / per_s,
        "sender_ms_per_audio_second": R["sender_fingerprint_60s"]["median_ms"] / SECONDS,
        "stream_bits_per_s": {"v1": fp.SPEC["bitrate_bps"] + d2.stream_overhead_bits_per_s("v1"),
                              "v2": fp.SPEC["bitrate_bps"] + d2.stream_overhead_bits_per_s("v2")},
        "termination_bytes_once": d2.END_BYTES}
    R["machine"] = {"platform": platform.platform(), "processor": platform.processor(), "python": sys.version.split()[0],
                    "numpy": np.__version__, "cpu_count": os.cpu_count()}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "round6_perf"); os.makedirs(out, exist_ok=True)
    json.dump(R, open(os.path.join(out, "perf.json"), "w"), indent=2)
    D = R["derived"]
    L = ["# Round 6 performance (item 6)", "", f"Machine: {R['machine']['platform']}, {R['machine']['cpu_count']} cores; Python {R['machine']['python']}.", "",
         "| Operation | median | p95 |", "|---|---|---|"]
    for key, label in [("sender_fingerprint_60s", "Sender fingerprint, 60 s call"), ("recipient_check_60s", "Recipient content check, 60 s call"),
                       ("key_message_v1", "Key message setup + open, v1 (BVI-0)"), ("key_message_v2", "Key message setup + open, v2 (number binding)"),
                       ("stream_tag_v1_60s", "Stream tagging, 60 s, v1"), ("stream_tag_v2_60s", "Stream tagging, 60 s, v2"),
                       ("stream_verify_v1_60s", "Stream verification, 60 s, v1"), ("stream_verify_v2_60s", "Stream verification, 60 s, v2")]:
        L.append(f"| {label} | {R[key]['median_ms']:.3f} ms | {R[key]['p95_ms']:.3f} ms |")
    L += ["", f"Recipient peak memory for a 60 s check: {R['recipient_check_peak_MB']:.1f} MB.",
          f"Recipient cost per second of audio (content check + v2 stream): {D['recipient_ms_per_audio_second_v2']:.2f} ms "
          f"(real-time factor {D['real_time_factor']:.4f}; about {D['concurrent_calls_per_core']:.0f} concurrent calls per core).",
          f"Stream bandwidth: v1 {D['stream_bits_per_s']['v1']} bit/s, v2 {D['stream_bits_per_s']['v2']} bit/s, plus a {D['termination_bytes_once']}-byte termination once."]
    open(os.path.join(out, "perf.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))

if __name__ == "__main__":
    main()
