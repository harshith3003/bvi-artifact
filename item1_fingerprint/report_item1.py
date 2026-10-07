"""
report_item1.py — every item-1 number, generated from the raw per-call files.

  * thresholds chosen on CALIBRATION speakers only (99th pct of per-call max 2 s-window BER)
  * all rates on TEST speakers
  * honest false-flag intervals: cluster bootstrap over test CALLS (each resample keeps all
    conditions of a call together, because the conditions reuse the same calls), B = 10,000
  * attack detection: 95% Wilson intervals (one attack instance per call and type)
  * both the pause rule ON (the spec) and OFF (analysis only)

Usage: python3 report_item1.py RESULTS_DIR
Writes RESULTS_DIR/report.txt and RESULTS_DIR/thresholds.json
"""
import csv, json, os, sys
import numpy as np

d = sys.argv[1] if len(sys.argv) > 1 else "../results/item1_devclean"
B = int(os.environ.get("BVI_BOOT", "10000"))
man = json.load(open(os.path.join(d, "manifest.json")))
calib = set(man["calibration_speakers"])
H = list(csv.DictReader(open(os.path.join(d, "honest_raw.csv"))))
A = list(csv.DictReader(open(os.path.join(d, "attack_raw.csv"))))
ORDER = ["g711u", "g711a", "opus16", "amr122", "amr122_g711u", "amr475"]
NAME = {"g711u": "G.711 mu-law", "g711a": "G.711 A-law", "opus16": "Opus 16 kbit/s",
        "amr122": "AMR-NB 12.2", "amr122_g711u": "AMR-NB 12.2 -> G.711", "amr475": "AMR-NB 4.75"}
codecs = [c for c in ORDER if any(r["codec"] == c for r in H)]
COL = {True: "max_window_ber", False: "max_window_ber_nopause"}
lines = []
say = lambda s="": (lines.append(s), print(s))
val = lambda r, rule: float(r[COL[rule]])


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n; dd = 1 + z * z / n; c = (p + z * z / (2 * n)) / dd
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / dd
    return max(0, c - h), min(1, c + h)


def flagged(r, th, rule):
    v = val(r, rule)
    return (not np.isnan(v)) and v > th


def q99(vals):
    v = np.array([x for x in vals if not np.isnan(x)])
    return float(np.quantile(v, 0.99))


def thresholds(rule):
    t = {c: q99([val(r, rule) for r in H if r["speaker"] in calib and r["codec"] == c]) for c in codecs}
    t["pooled"] = q99([val(r, rule) for r in H if r["speaker"] in calib])
    return t


def honest_rate_bootstrap(codec, th, rule, rng):
    rows = [r for r in H if r["speaker"] not in calib and r["codec"] == codec]
    by_call = {}
    for r in rows:
        by_call.setdefault(r["call"], []).append(flagged(r, th, rule))
    calls = sorted(by_call)
    k = np.array([sum(by_call[c]) for c in calls]); n = np.array([len(by_call[c]) for c in calls])
    point = k.sum() / n.sum()
    idx = rng.integers(0, len(calls), size=(B, len(calls)))
    boot = k[idx].sum(axis=1) / n[idx].sum(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return point, lo, hi, int(k.sum()), int(n.sum()), len(calls)


def attack_rate(codec, kinds, th, rule, length=None):
    rows = [r for r in A if r["codec"] == codec and r["attack"] in kinds
            and (length is None or abs(float(r["length_s"]) - length) < 1e-9)]
    k = sum(flagged(r, th, rule) for r in rows); n = len(rows)
    lo, hi = wilson(k, n)
    return (k / n if n else float("nan")), lo, hi, k, n


T = {True: thresholds(True), False: thresholds(False)}
rng = np.random.default_rng(man["seed"])
say(f"spec {man['spec']['version']}; seed {man['seed']}; natural corpus {os.path.basename(os.path.normpath(man['natural_corpus']))}; "
    f"{man['calls']} calls of {man['call_seconds']:.0f} s, {man['speakers']} speakers "
    f"({man['calibration_calls']} calibration / {man['test_calls']} test calls, speaker-disjoint)")
say(f"synthetic: {man['synthetic_files']} ASVspoof 2019 LA eval spoofs from {man['synthetic_corpus']}")
for rule in (True, False):
    say(f"thresholds, pause rule {'ON ' if rule else 'OFF'}: pooled {T[rule]['pooled']:.3f}; " +
        ", ".join(f"{c} {T[rule][c]:.3f}" for c in codecs))

SPL = man["splice_lengths_s"]
for rule in (True, False):
    for policy in ("per-codec", "pooled"):
        say(f"\n=== pause rule {'ON (spec)' if rule else 'OFF (analysis)'}, {policy.upper()} threshold ===")
        say(f"{'codec':22s} {'theta':>6s}  honest 60 s calls wrongly flagged [cluster bootstrap 95%]")
        for c in codecs:
            th = T[rule][c] if policy == "per-codec" else T[rule]["pooled"]
            p, lo, hi, k, n, nc = honest_rate_bootstrap(c, th, rule, rng)
            say(f"{NAME[c]:22s} {th:6.3f}  {100*p:5.1f}% [{100*lo:4.1f}-{100*hi:4.1f}]  ({k}/{n} call-conditions, {nc} calls)")
        say(f"{'codec':22s} {'full nat':>9s} {'full ASV':>9s} {'pause 3s':>9s} " + " ".join(f"{'spl'+str(L):>7s}" for L in SPL) + "   >=95% | >=50%")
        for c in codecs:
            th = T[rule][c] if policy == "per-codec" else T[rule]["pooled"]
            fn = attack_rate(c, {"full_natural"}, th, rule)[0]
            fs = attack_rate(c, {"full_synthetic"}, th, rule)[0]
            pi = attack_rate(c, {"pause_inject_natural", "pause_inject_synthetic"}, th, rule)[0]
            sp = [attack_rate(c, {"splice_natural", "splice_synthetic"}, th, rule, L)[0] for L in SPL]
            s95 = next((L for L, x in zip(SPL, sp) if x >= 0.95), None); s50 = next((L for L, x in zip(SPL, sp) if x >= 0.50), None)
            say(f"{NAME[c]:22s} {100*fn:8.1f}% {100*fs:8.1f}% {100*pi:8.1f}% " + " ".join(f"{100*x:6.1f}%" for x in sp) +
                f"   {str(s95)+' s' if s95 else '>5 s'} | {str(s50)+' s' if s50 else '>5 s'}")

say("\n=== requested: AMR-NB 4.75 and the pooled policy with the pause rule OFF (Wilson 95%) ===")
req = ([("AMR-NB 4.75, per-codec", "amr475", T[False]["amr475"])] if "amr475" in codecs else []) + \
      [(f"{NAME[c]}, pooled", c, T[False]["pooled"]) for c in codecs]
for label, c, th in req:
    fn = attack_rate(c, {"full_natural"}, th, False); fs = attack_rate(c, {"full_synthetic"}, th, False)
    s3 = attack_rate(c, {"splice_natural", "splice_synthetic"}, th, False, 3.0)
    pi = attack_rate(c, {"pause_inject_natural", "pause_inject_synthetic"}, th, False)
    f = lambda t: f"{100*t[0]:5.1f}% [{100*t[1]:4.1f}-{100*t[2]:5.1f}]"
    say(f"  {label:32s} theta {th:.3f}  full natural {f(fn)}  full ASVspoof {f(fs)}  3 s splice {f(s3)}  pause inject {f(pi)}")

json.dump({"spec": man["spec"]["version"], "source": os.path.abspath(d), "rule": "pause rule ON",
           "pooled": T[True]["pooled"], **{c: T[True][c] for c in codecs}},
          open(os.path.join(d, "thresholds.json"), "w"), indent=2)
with open(os.path.join(d, "report.txt"), "w") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"\nwrote {d}/report.txt and thresholds.json")
