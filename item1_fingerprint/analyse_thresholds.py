"""
analyse_thresholds.py — rebuild the item-1 tables from the raw per-call files at
two threshold policies, both chosen on CALIBRATION speakers only:

  pooled    : one threshold for every codec (99th pct of calibration per-call max window BER)
  per-codec : one threshold per codec, same rule, calibration calls of that codec only

Usage: python3 analyse_thresholds.py RESULTS_DIR      (e.g. ../results/item1)
Writes RESULTS_DIR/threshold_analysis.csv and prints the summary tables.
"""
import csv, json, os, sys
import numpy as np

d = sys.argv[1] if len(sys.argv) > 1 else "../results/item1"
man = json.load(open(os.path.join(d, "manifest.json")))
calib = set(man["calibration_speakers"])
H = list(csv.DictReader(open(os.path.join(d, "honest_raw.csv"))))
A = list(csv.DictReader(open(os.path.join(d, "attack_raw.csv"))))
f = lambda r: float(r["max_window_ber"])
codecs = sorted({r["codec"] for r in H}, key=lambda c: ["g711u", "g711a", "opus16", "amr122", "amr122_g711u", "amr475"].index(c) if c in ["g711u", "g711a", "opus16", "amr122", "amr122_g711u", "amr475"] else 99)

def q99(vals):
    v = np.array([x for x in vals if not np.isnan(x)])
    return float(np.quantile(v, 0.99))

pooled = q99([f(r) for r in H if r["speaker"] in calib])
per = {c: q99([f(r) for r in H if r["speaker"] in calib and r["codec"] == c]) for c in codecs}
rate = lambda rows, th: (sum(1 for r in rows if not np.isnan(f(r)) and f(r) > th) / len(rows)) if rows else float("nan")

out = []
print(f"pooled threshold {pooled:.4f}   (manifest {man['threshold']:.4f})")
print("per-codec thresholds: " + ", ".join(f"{c} {per[c]:.3f}" for c in codecs))
print(f"\n{'codec':13s} {'policy':9s} {'theta':>6s} {'honestFF':>8s} {'full_nat':>8s} {'full_syn':>8s} {'pause3s':>8s} "
      + " ".join(f"{'spl'+str(L):>7s}" for L in [0.5, 1.0, 2.0, 3.0, 5.0]) + "   (splice = natural/ASVspoof mean)")
for c in codecs:
    hon = [r for r in H if r["speaker"] not in calib and r["codec"] == c]
    for pol, th in (("pooled", pooled), ("per-codec", per[c])):
        att = lambda kind, L=None: [r for r in A if r["codec"] == c and r["attack"] == kind
                                    and (L is None or abs(float(r["length_s"]) - L) < 1e-9)]
        spl = []
        for L in [0.5, 1.0, 2.0, 3.0, 5.0]:
            spl.append((rate(att("splice_natural", L), th) + rate(att("splice_synthetic", L), th)) / 2)
        row = [c, pol, th, rate(hon, th), rate(att("full_natural"), th), rate(att("full_synthetic"), th),
               (rate(att("pause_inject_natural"), th) + rate(att("pause_inject_synthetic"), th)) / 2] + spl
        out.append(row)
        print(f"{c:13s} {pol:9s} {th:6.3f} {row[3]:8.3f} {row[4]:8.3f} {row[5]:8.3f} {row[6]:8.3f} "
              + " ".join(f"{x:7.3f}" for x in spl))
with open(os.path.join(d, "threshold_analysis.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["codec", "policy", "threshold", "honest_call_false_flag", "full_natural", "full_synthetic",
                "pause_inject_3s", "splice_0.5", "splice_1", "splice_2", "splice_3", "splice_5"])
    w.writerows(out)
print(f"\nwrote {os.path.join(d, 'threshold_analysis.csv')}")
