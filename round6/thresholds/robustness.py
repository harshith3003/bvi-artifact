"""Item 2: threshold robustness across speaker-disjoint splits, codecs, noise and packet loss.

Input: ber_samples.csv with one row per (call, condition, kind):
  codec, kind, max_ber, call_id, speaker, condition
  kind: honest | splice_0.5 | splice_1 | splice_2 | splice_3 | splice_5 | full_nat | full_asv | pause_3 | semantic_*
  condition: e.g. clean_loss0, white20_loss1, babble10_loss5 (honest rows); attacks may use a single condition.

Analyses (per codec):
  1. ROC of honest vs each attack kind (per-call maximum BER as the score): AUC and EER.
  2. FAR and FRR at the operating threshold, with cluster-bootstrap 95% CIs over calls (10,000 resamples).
     FAR = attack calls accepted (BER <= theta); FRR = honest call-conditions rejected (BER > theta).
  3. Threshold stability: 200 random speaker-disjoint 50/50 splits. Theta = 99th percentile of the calibration
     half's honest per-call-condition BER; the test half gives FRR and FAR. Reports the spread of theta, FRR, FAR.
  4. FRR by condition (noise x loss) at the operating threshold.
  5. Opus diagnosis: how many calibration values determine theta, the tail shape near the 99th percentile,
     and theta's sensitivity to removing single speakers (leave-one-speaker-out).
Outputs: results/<label>/report.md, roc_<codec>.png, theta_stability.png, frr_by_condition.csv, splits.csv
"""
import argparse, csv, json, math, os, random, statistics
from collections import defaultdict
import numpy as np

def load(path):
    rows = list(csv.DictReader(open(path)))
    return rows

def roc(hon, att):
    ths = np.unique(np.concatenate([hon, att, [0.0, 1.0]]))
    frr = np.array([(hon > t).mean() for t in ths]); far = np.array([(att <= t).mean() for t in ths])
    auc = float(np.mean(att[:, None] > hon[None, :]) + 0.5 * np.mean(att[:, None] == hon[None, :]))
    i = int(np.argmin(np.abs(frr - far))); return ths, far, frr, auc, float((frr[i] + far[i]) / 2)

def cluster_boot(values_by_call, stat, B, rng):
    calls = list(values_by_call); n = len(calls); out = []
    for _ in range(B):
        pick = [calls[rng.randrange(n)] for _ in range(n)]
        vals = [v for c in pick for v in values_by_call[c]]
        out.append(stat(vals))
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ber-samples", required=True); ap.add_argument("--thresholds")
    ap.add_argument("--splits", type=int, default=200); ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260909); ap.add_argument("--label", default="empirical")
    ap.add_argument("--rule", choices=["on", "off"], default="on", help="pause rule on (max_ber) or off (max_ber_nopause)")
    a = ap.parse_args()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", a.label); os.makedirs(out, exist_ok=True)
    rows = load(a.ber_samples); rng = random.Random(a.seed)
    col = "max_ber" if a.rule == "on" or "max_ber_nopause" not in rows[0] else "max_ber_nopause"
    for r in rows: r["max_ber"] = float(r[col])
    rows = [r for r in rows if r["max_ber"] == r["max_ber"]]          # drop NaN (inconclusive) rows
    test_only = lambda rs: [r for r in rs if r.get("split", "test") == "test"]
    th = json.load(open(a.thresholds)) if a.thresholds else {}
    th = th.get("pause_on", th) if isinstance(th, dict) else {}
    if a.rule == "off": th = {}                                          # thresholds recomputed from calibration
    codecs = sorted({r["codec"] for r in rows}); kinds = sorted({r["kind"] for r in rows if r["kind"] != "honest"})
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    L = [f"# Item 2: threshold robustness ({a.label})", "", f"Splits: {a.splits}; bootstrap: {a.boot}; seed {a.seed}.", ""]
    stab, cond_rows = {}, []
    for cd in codecs:
        Hall = [r for r in rows if r["codec"] == cd and r["kind"] == "honest"]
        H = test_only(Hall); hon = np.array([r["max_ber"] for r in H])
        cal = np.array([r["max_ber"] for r in Hall if r.get("split") == "cal"])
        theta = float(th.get(cd, np.quantile(cal if len(cal) else hon, 0.99)))
        L += [f"## {cd} (operating threshold {theta:.3f})", "", "| Attack | AUC | EER | FAR at theta [95% CI] |", "|---|---|---|---|"]
        fig, ax = plt.subplots(figsize=(4.6, 4.2))
        for k in kinds:
            A = [r for r in rows if r["codec"] == cd and r["kind"] == k]
            if not A: continue
            att = np.array([r["max_ber"] for r in A])
            _, far, frr, auc, eer = roc(hon, att)
            ax.plot(far, 1 - frr, lw=1.2, label=f"{k} (AUC {auc:.3f})")
            byc = defaultdict(list)
            for r in A: byc[r["call_id"]].append(r["max_ber"])
            lo, hi = cluster_boot(byc, lambda v: float(np.mean(np.array(v) <= theta)), min(a.boot, 2000), rng)
            L.append(f"| {k} | {auc:.4f} | {100*eer:.2f}% | {100*float((att <= theta).mean()):.2f}% [{100*lo:.2f}-{100*hi:.2f}] |")
        ax.plot([0, 1], [0, 1], "k:", lw=.8); ax.set_xlabel("FAR (attack accepted)"); ax.set_ylabel("1 - FRR (honest accepted)")
        ax.set_title(f"ROC, {cd}", fontsize=9); ax.legend(fontsize=6, loc="lower right"); plt.tight_layout()
        plt.savefig(os.path.join(out, f"roc_{cd}.png"), dpi=160); plt.close()
        byc = defaultdict(list)
        for r in H: byc[r["call_id"]].append(r["max_ber"])
        lo, hi = cluster_boot(byc, lambda v: float(np.mean(np.array(v) > theta)), a.boot, rng)
        L += ["", f"FRR at theta: {100*float((hon > theta).mean()):.2f}% [{100*lo:.2f}-{100*hi:.2f}] over {len(byc)} calls x conditions.", ""]
        for cond in sorted({r.get("condition", "") for r in H}):
            v = np.array([r["max_ber"] for r in H if r.get("condition", "") == cond])
            cond_rows.append(dict(codec=cd, condition=cond, n=len(v), frr=round(float((v > theta).mean()), 4)))
        # speaker-disjoint split stability
        spk = sorted({r["speaker"] for r in Hall}); sres = []
        for s in range(a.splits):
            rr = random.Random(f"{a.seed}|{cd}|{s}"); sh = spk[:]; rr.shuffle(sh); calspk = set(sh[:len(sh) // 2])
            hc = np.array([r["max_ber"] for r in Hall if r["speaker"] in calspk]); ht = np.array([r["max_ber"] for r in Hall if r["speaker"] not in calspk])
            t = float(np.quantile(hc, 0.99)); rec = dict(split=s, theta=t, frr=float((ht > t).mean()))
            for k in kinds:
                at = np.array([r["max_ber"] for r in rows if r["codec"] == cd and r["kind"] == k and r["speaker"] not in calspk])
                if len(at): rec["far_" + k] = float((at <= t).mean())
            sres.append(rec)
        stab[cd] = sres
        ts = [x["theta"] for x in sres]; fr = [x["frr"] for x in sres]
        L += [f"Threshold over {a.splits} speaker-disjoint splits: mean {np.mean(ts):.3f}, sd {np.std(ts):.3f}, 95% range {np.percentile(ts,2.5):.3f}-{np.percentile(ts,97.5):.3f}; test FRR mean {100*np.mean(fr):.2f}% (95% range {100*np.percentile(fr,2.5):.2f}-{100*np.percentile(fr,97.5):.2f}%).", ""]
        if cd.startswith("opus"):
            n_tail = int(math.ceil(0.01 * len(cal))); top = np.sort(cal)[-max(n_tail, 5):]
            loso = []
            for s in spk:
                v = np.array([r["max_ber"] for r in Hall if r["speaker"] != s and r.get("split") == "cal"])
                if len(v): loso.append((s, float(np.quantile(v, 0.99))))
            loso.sort(key=lambda x: -abs(x[1] - theta))
            L += ["**Opus diagnosis.** The 99th percentile rests on the top "
                  f"{n_tail} of {len(cal)} calibration values: {', '.join(f'{x:.3f}' for x in top)}. "
                  f"Leave-one-speaker-out thresholds range {min(x[1] for x in loso):.3f}-{max(x[1] for x in loso):.3f}; "
                  f"most influential speakers: {', '.join(f'{s} ({t:.3f})' for s, t in loso[:3])}.", ""]
    with open(os.path.join(out, "splits.csv"), "w", newline="") as f:
        keys = sorted({k for v in stab.values() for x in v for k in x}); w = csv.DictWriter(f, fieldnames=["codec"] + keys); w.writeheader()
        for cd, v in stab.items():
            for x in v: w.writerow(dict(codec=cd, **x))
    with open(os.path.join(out, "frr_by_condition.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cond_rows[0].keys())); w.writeheader(); w.writerows(cond_rows)
    fig, ax = plt.subplots(figsize=(1.3 * len(codecs) + 2, 3.8))
    ax.boxplot([[x["theta"] for x in stab[cd]] for cd in codecs]); ax.set_xticks(range(1, len(codecs) + 1)); ax.set_xticklabels(codecs)
    ax.set_ylabel("threshold (99th pct of calibration honest BER)"); ax.set_title(f"Threshold over {a.splits} speaker-disjoint splits", fontsize=9)
    plt.xticks(fontsize=7); plt.tight_layout(); plt.savefig(os.path.join(out, "theta_stability.png"), dpi=160); plt.close()
    open(os.path.join(out, "report.md"), "w").write("\n".join(L) + "\n"); print("wrote", out)

if __name__ == "__main__":
    main()
