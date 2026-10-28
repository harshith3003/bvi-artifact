"""
analyse_r6.py: summary of the round-6 SIP testbed, from the raw files only.
  setup_delay.csv  caller side, BVI off/on alternating (INVITE -> 200 OK)
  calls.jsonl      callee verdict per media call under all eight configurations
Writes summary.md next to the inputs and prints it. Expected outcomes follow SPEC.md; a cell that differs from its
expectation is marked "!" and listed, so mismatches are visible rather than averaged away.
"""
import csv, json, os, sys
from collections import Counter, defaultdict
import numpy as np

d = sys.argv[1] if len(sys.argv) > 1 else "results"
CFG = ["BVI-0", "BVI-R", "BVI-B (strict)", "BVI-B (lenient)", "R - number binding", "R - linked chain",
       "R - auth. termination", "R + endpoint strict"]
V, N, F = "verified", "not verified", "fail"
ALL = lambda o: {c: o for c in CFG}
EXPECT = {   # outcome that is correct for each configuration (honest: verified; attack: not verified or fail)
    "honest": ALL(V), "loss5": ALL(V), "missing_records": ALL(V), "transcode_declared": None, "transcode_silent": None,
    "mobile_origin": None, "false_record": {**ALL(V), "BVI-0": F, "R - linked chain": F},
    "relay_session": {**ALL(F), "BVI-0": V, "R - number binding": V},
    # without number binding, a rewrite by the silent middle carrier of a 3-hop path has no confirmable upstream
    # evidence (p1's record is unlinked), so the linked rule returns "unknown" and the call verifies
    "rewrite": {**ALL(F), "R - number binding": V}, "launder": {**ALL(F), "BVI-0": V, "R - number binding": V},
    "substitute": ALL(F), "splice3s": ALL(F), "strip": ALL(N),
    "truncate": {**ALL(N), "BVI-0": V, "R - auth. termination": V},
    "injected_bye": {**ALL(N), "BVI-0": V, "R - auth. termination": V},
}
L = ["# Round-6 SIP testbed results", ""]

p = os.path.join(d, "setup_delay.csv")
if os.path.exists(p):
    rows = list(csv.DictReader(open(p)))
    off = np.array([float(r["setup_ms"]) for r in rows if r["bvi"] == "0"]); on = np.array([float(r["setup_ms"]) for r in rows if r["bvi"] == "1"])
    rng = np.random.default_rng(20260909)
    diffs = [np.median(rng.choice(on, on.size)) - np.median(rng.choice(off, off.size)) for _ in range(10000)]
    vp = [float(r["verify_ms"]) for r in rows if r["bvi"] == "1" and r.get("verify_ms")]
    vl = [float(r["verify_linked_ms"]) for r in rows if r["bvi"] == "1" and r.get("verify_linked_ms")]
    L += ["## Call setup (INVITE -> 200 OK at the caller; 3 Kamailio hops, linked attestations, local chain)", "",
          f"- BVI off: n={off.size}, median {np.median(off):.2f} ms, p95 {np.percentile(off, 95):.2f} ms",
          f"- BVI on: n={on.size}, median {np.median(on):.2f} ms, p95 {np.percentile(on, 95):.2f} ms",
          f"- added: median {np.median(on) - np.median(off):.2f} ms [bootstrap 95% {np.percentile(diffs, 2.5):.2f}-{np.percentile(diffs, 97.5):.2f}]",
          f"- recipient reads at INVITE: positional (BVI-0) median {np.median(vp):.2f} ms; linked (BVI-R) median {np.median(vl):.2f} ms" if vp and vl else "", ""]

calls = [json.loads(l) for l in open(os.path.join(d, "calls.jsonl"))]
by = defaultdict(list)
for c in calls:
    by[c["label"]].append(c)
L += ["## Verdicts per scenario and configuration (count of verified / not verified / fail)", "",
      "| Scenario | calls | " + " | ".join(CFG) + " |", "|---|---|" + "---|" * len(CFG)]
mism = []
for scen, cs in by.items():
    cells = []
    for cfg in CFG:
        cnt = Counter(c["configs"][cfg]["outcome"] for c in cs)
        cell = f"{cnt[V]}/{cnt[N]}/{cnt[F]}"
        exp = (EXPECT.get(scen) or {}).get(cfg)
        if exp is not None and cnt[exp] != len(cs):
            cell += " !"; mism.append(f"{scen} / {cfg}: expected {exp} for all {len(cs)}, got {dict(cnt)}")
        cells.append(cell)
    L.append(f"| {scen} | {len(cs)} | " + " | ".join(cells) + " |")
L += ["", "Transcoding scenarios have no single correct answer: they measure availability (honest calls verified).", ""]
L += ["## Layer detail for BVI-0 and BVI-R (first call of each scenario)", "",
      "| Scenario | received s | blocks v1/v2 | termination | route pos / linked | thresholds carrier / chain | BVI-0 | BVI-R |", "|---|---|---|---|---|---|---|---|"]
for scen, cs in by.items():
    c = cs[0]; z, r = c["configs"]["BVI-0"], c["configs"]["BVI-R"]
    fmt = lambda x: f"{x['outcome']} (id {x['identity']}, route {x['route']}, audio {x['content']}, BER {x['max_ber']})"
    L.append(f"| {scen} | {c['seconds_received']} | {c['blocks_v1']}/{c['blocks_v2']} | {c['termination']} | {c['route_positional']} / "
             f"{c['route_linked']} | {c['theta_carrier']} / {c['theta_chain']} | {fmt(z)} | {fmt(r)} |")
L += ["", "## Cells that differ from the expected outcome", ""] + ([f"- {m}" for m in mism] or ["- none"])
out = "\n".join(L) + "\n"
open(os.path.join(d, "summary.md"), "w").write(out); print(out)
