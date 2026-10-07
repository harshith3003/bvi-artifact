"""
analyse_testbed.py — summary of the SIP testbed run (item 4), from the raw files only.

  results/setup_delay.csv  one row per delay call (caller side): BVI off/on alternating
  results/media_calls.csv  one row per attack-scenario call (caller side)
  results/calls.jsonl      callee's final verdict per media call

Setup delay = INVITE sent -> 200 OK received at the caller. Added delay is reported as
the difference of medians and of 95th percentiles (BVI on minus off), with a bootstrap
95% interval for the median difference (B = 10,000, seed 20260909).
"""
import csv, json, os, sys
import numpy as np

d = sys.argv[1] if len(sys.argv) > 1 else "results"
rows = list(csv.DictReader(open(os.path.join(d, "setup_delay.csv"))))
off = np.array([float(r["setup_ms"]) for r in rows if r["bvi"] == "0"])
on = np.array([float(r["setup_ms"]) for r in rows if r["bvi"] == "1"])
q = lambda a, p: float(np.percentile(a, p))
rng = np.random.default_rng(20260909)
diffs = [np.median(rng.choice(on, on.size)) - np.median(rng.choice(off, off.size)) for _ in range(10_000)]

print("SIP TESTBED — call setup delay (INVITE -> 200 OK at the caller), 3 Kamailio hops, local chain")
print(f"  BVI off : n={off.size:4d}  median {np.median(off):7.2f} ms   p95 {q(off, 95):7.2f} ms")
print(f"  BVI on  : n={on.size:4d}  median {np.median(on):7.2f} ms   p95 {q(on, 95):7.2f} ms")
print(f"  added   : median {np.median(on) - np.median(off):7.2f} ms [bootstrap 95% {np.percentile(diffs, 2.5):.2f}-"
      f"{np.percentile(diffs, 97.5):.2f}]   p95 {q(on, 95) - q(off, 95):7.2f} ms")

ver = np.array([float(r["verify_ms"]) for r in rows if r["bvi"] == "1" and r["verify_ms"]])
att = {}
for r in rows:
    if r["bvi"] == "1" and r["attest_ms"]:
        for part in r["attest_ms"].split(";"):
            if "=" in part:
                hop, ms = part.split("=", 1)
                att.setdefault(hop.strip(), []).append(float(ms))
print("\n  breakdown of the added delay (BVI-on calls):")
print(f"    recipient verification (L1 + route check, JSON-RPC reads): median {np.median(ver):.2f} ms, p95 {q(ver, 95):.2f} ms")
for hop in sorted(att):
    a = np.array(att[hop])
    print(f"    hop {hop} on-chain attestation (synchronous, automine):     median {np.median(a):.2f} ms, p95 {q(a, 95):.2f} ms")

print("\nATTACK SCENARIOS (10 s of LibriSpeech dev-clean speech, G.711 mu-law; verdict by the callee)")
expect = {"honest": "verified", "rewrite": "fail", "substitute": "fail", "splice3s": "fail", "strip": "not verified"}
cj = os.path.join(d, "calls.jsonl")
if not os.path.exists(cj):
    sys.exit("  no calls.jsonl: the callee wrote no verdicts (see compose.log)")
recs = [json.loads(l) for l in open(cj) if l.strip()]
print(f"  {'scenario':11s} {'n':>2s}  {'outcomes':28s} {'L1':6s} {'route':7s} {'content':13s} {'max window BER':16s} expected")
for scen in ["honest", "rewrite", "substitute", "splice3s", "strip"]:
    rs = [r for r in recs if r["label"] == scen]
    if not rs:
        continue
    outs = {}
    for r in rs:
        outs[r["outcome"]] = outs.get(r["outcome"], 0) + 1
    bers = [r["max_window_ber"] for r in rs if r["max_window_ber"] is not None]
    rng_s = f"{min(bers):.3f}-{max(bers):.3f}" if bers else "-"
    ok = all(r["outcome"] == expect[scen] for r in rs)
    print(f"  {scen:11s} {len(rs):2d}  {', '.join(f'{k} {v}' for k, v in outs.items()):28s} "
          f"{'/'.join(sorted({r['l1'] for r in rs})):6s} {'/'.join(sorted({r['l2'] for r in rs})):7s} "
          f"{'/'.join(sorted({r['content'] for r in rs})):13s} {rng_s:16s} {expect[scen]} {'OK' if ok else 'MISMATCH'}")
th = sorted({(r["theta"], r["theta_basis"]) for r in recs if r["theta"] is not None})
for t, b in th:
    print(f"  content threshold used: {t:.3f} ({b})")
print("\nNotes: local chain with instant mining; attestations are written synchronously before each proxy\n"
      "forwards the INVITE. On a live rollup a write takes a block, so attestation must run asynchronously and\n"
      "the route check during ringing; the verification read cost above is unaffected by that.")
