"""
collusion_sim.py — path-tamper detection under partial participation AND collusion.

Model (replaces the earlier per-hop "chance of catching" model):
  * A path has H carriers. An in-path rewrite of the caller ID happens at a
    boundary b between carrier b-1 and carrier b (b = 1..H-1).
  * Each carrier independently: participates with prob p; colludes with prob f.
    An HONEST PARTICIPANT is a carrier that participates and does not collude,
    probability q = p * (1 - f).
  * The rewrite is caught FOR CERTAIN iff there is at least one honest
    participant on EACH side of b, and missed otherwise. No per-hop detection
    probability, no rounding.
  * Average-case adversary: b uniform on 1..H-1, chosen without knowledge of
    who participates.   Closed form:
        P_avg(H, q) = 1/(H-1) * sum_{b=1}^{H-1} (1-(1-q)^b) (1-(1-q)^(H-b))
  * Strategic adversary: knows who participates; evades unless both the first
    and last carrier are honest participants.   Closed form: q^2.
  This is the paper's existing partial-participation formula with p replaced by
  q = p(1-f): for detection, a colluder is worth exactly as much as a carrier
  that never joined.

Outcome split (tampered sessions only), path rule from the paper:
  caught -> "fail";  else >=2 attestations -> "pass" (a MISS);  else "unknown".
  Two colluder strategies, reported separately:
    silent   : colluders never attest (identical to non-participants)
    rational : colluders attest the fake ID whenever that creates no
               contradiction (i.e. when no honest participant is upstream),
               otherwise stay silent. Maximises false passes without changing
               detection. With f = 1 this reproduces C2: every carrier attests
               the fake ID and the path PASSES.

Outputs (revision/results/): collusion_detection.csv, collusion_outcomes.csv,
collusion_manifest.json, collusion_detection.png
"""
import json
import os
import platform

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SEED = 20260909
TRIALS = 200_000
H_LIST = [3, 5, 8, 12]
P_LIST = [0.25, 0.50, 0.75, 1.00]
F_LIST = [0.00, 0.25, 0.50, 0.75, 1.00]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")
os.makedirs(OUT, exist_ok=True)


def p_avg(H, q):
    b = np.arange(1, H)
    return float(np.mean((1 - (1 - q) ** b) * (1 - (1 - q) ** (H - b))))


def p_strategic(q):
    return q * q


def simulate(rng, H, p, f, n):
    participates = rng.random((n, H)) < p
    colludes = rng.random((n, H)) < f
    honest = participates & ~colludes                       # honest participants
    b = rng.integers(1, H, size=n)                          # boundary, uniform 1..H-1

    cum = np.cumsum(honest, axis=1)
    up = cum[np.arange(n), b - 1]                           # honest participants before b
    down = cum[:, -1] - up                                  # honest participants from b on
    caught = (up > 0) & (down > 0)

    strategic_caught = honest[:, 0] & honest[:, -1]

    n_coll = colludes.sum(axis=1)
    # silent colluders: only honest participants attest
    att_silent = up + down
    # rational colluders: attest fake only when no honest participant is upstream
    att_rational = np.where(up == 0, down + n_coll, up)

    def split(att):
        passed = (~caught) & (att >= 2)
        unknown = (~caught) & (att < 2)
        return caught.mean(), passed.mean(), unknown.mean()

    return caught.mean(), strategic_caught.mean(), split(att_silent), split(att_rational)


def main():
    rng = np.random.default_rng(SEED)
    det_rows, out_rows = [], []
    max_diff_avg = max_diff_str = 0.0

    for H in H_LIST:
        for p in P_LIST:
            for f in F_LIST:
                q = p * (1 - f)
                ca, cs = p_avg(H, q), p_strategic(q)
                ma, ms, sil, rat = simulate(rng, H, p, f, TRIALS)
                max_diff_avg = max(max_diff_avg, abs(ca - ma))
                max_diff_str = max(max_diff_str, abs(cs - ms))
                det_rows.append([H, p, f, q, ca, ma, abs(ca - ma), cs, ms, abs(cs - ms)])
                out_rows.append([H, p, f, "silent", *sil])
                out_rows.append([H, p, f, "rational", *rat])

    with open(os.path.join(OUT, "collusion_detection.csv"), "w") as fh:
        fh.write("H,p,f,q,avg_closed,avg_mc,avg_absdiff,strategic_closed,strategic_mc,strategic_absdiff\n")
        for r in det_rows:
            fh.write(f"{r[0]},{r[1]:.2f},{r[2]:.2f},{r[3]:.4f},{r[4]:.6f},{r[5]:.6f},{r[6]:.6f},"
                     f"{r[7]:.6f},{r[8]:.6f},{r[9]:.6f}\n")
    with open(os.path.join(OUT, "collusion_outcomes.csv"), "w") as fh:
        fh.write("H,p,f,colluder_strategy,caught_fail,missed_pass,missed_unknown\n")
        for r in out_rows:
            fh.write(f"{r[0]},{r[1]:.2f},{r[2]:.2f},{r[3]},{r[4]:.6f},{r[5]:.6f},{r[6]:.6f}\n")

    # Equivalence check: detection at (p, f) equals detection at (p*(1-f), 0)
    equiv = []
    for H in H_LIST:
        for (p, f) in [(1.0, 0.5), (0.5, 0.5), (1.0, 0.25)]:
            equiv.append({"H": H, "p": p, "f": f, "q": p * (1 - f),
                          "collusion_closed": p_avg(H, p * (1 - f)),
                          "nonparticipation_closed": p_avg(H, p * (1 - f))})

    manifest = {
        "script": "revision/sim/collusion_sim.py",
        "seed": SEED, "trials_per_cell": TRIALS,
        "grid": {"H": H_LIST, "p": P_LIST, "f": F_LIST},
        "rng": "numpy.random.default_rng (PCG64)",
        "numpy_version": np.__version__, "python_version": platform.python_version(),
        "max_absdiff_average_case": max_diff_avg,
        "max_absdiff_strategic": max_diff_str,
        "model": "caught iff >=1 honest participant on each side of the rewrite boundary; q = p(1-f)",
        "equivalence_examples": equiv,
    }
    with open(os.path.join(OUT, "collusion_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    # Figure: detection vs q (no BBCA line)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3))
    qs = np.linspace(0, 1, 101)
    for H in H_LIST:
        line, = ax1.plot(qs, [p_avg(H, q) for q in qs], label=f"H={H} (closed form)")
        pts = [r for r in det_rows if r[0] == H]
        ax1.scatter([r[3] for r in pts], [r[5] for r in pts], s=14, color=line.get_color())
    ax1.plot(qs, qs ** 2, "k--", label="strategic adversary, q² (all H)")
    ax1.set_xlabel("q = p(1−f), fraction of honest participating carriers")
    ax1.set_ylabel("P(rewrite caught)")
    ax1.set_title("Detection depends only on q (dots = simulation)")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    H = 5
    for strat, ls in [("silent", "-"), ("rational", "--")]:
        rows = [r for r in out_rows if r[0] == H and r[1] == 1.0 and r[3] == strat]
        fs_ = [r[2] for r in rows]
        ax2.plot(fs_, [r[4] for r in rows], ls, color="tab:green", label=f"caught ({strat})")
        ax2.plot(fs_, [r[5] for r in rows], ls, color="tab:red", label=f"missed, path passes ({strat})")
        ax2.plot(fs_, [r[6] for r in rows], ls, color="tab:gray", label=f"missed, unknown ({strat})")
    ax2.set_xlabel("collusion fraction f (p = 1, H = 5)")
    ax2.set_ylabel("share of tampered sessions")
    ax2.set_title("Outcome split (caught lines overlap: identical)")
    ax2.legend(fontsize=7)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "collusion_detection.png"), dpi=150)

    print(f"seed={SEED}  trials/cell={TRIALS}  cells={len(det_rows)}")
    print(f"max |closed - MC| average case = {max_diff_avg:.4f}")
    print(f"max |closed - MC| strategic    = {max_diff_str:.4f}")
    print("\nDetection, average case (closed form), p = 1.0:")
    print("   H |" + "".join(f"  f={f:.2f}" for f in F_LIST))
    for H in H_LIST:
        print(f"  {H:2d} |" + "".join(f"  {p_avg(H, 1.0 * (1 - f)):6.3f}" for f in F_LIST))
    print("\nFull collusion (f = 1), H = 5:")
    for r in out_rows:
        if r[0] == 5 and r[1] == 1.0 and r[2] == 1.0:
            print(f"  {r[3]:8s}: caught {r[4]:.3f}  missed->pass {r[5]:.3f}  missed->unknown {r[6]:.3f}")
    print("\nwrote collusion_detection.csv, collusion_outcomes.csv, collusion_manifest.json, collusion_detection.png")


if __name__ == "__main__":
    main()
