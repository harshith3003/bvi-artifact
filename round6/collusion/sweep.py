"""Item 4: carrier collusion under partial participation.

Model (per call, per carrier, independently):
  corrupt with probability c; otherwise attests honestly with probability p, else stays silent.
  The attacker rewrites the calling identifier at one corrupt carrier. Corrupt carriers never help detection:
  attesting can only add evidence, so their best strategy is silence (a colluder is worth no more than a
  non-participant; this is checked by the scenario harness).
  random attacker:   rewrites at a uniformly chosen corrupt carrier.
  targeted attacker: knows who attests and rewrites at the corrupt carrier that is least likely to be caught.

Detection rules (route layer only, no number binding, matching BVI-0 and "R - number binding"):
  positional (BVI-0):    caught iff some honest record lies before AND some honest record lies after the rewrite.
  positional + launder:  BVI-0 when an off-path registered accomplice can fill the rewriter's position -> never caught.
  linked (BVI-R route):  as positional, but only ADMISSIBLE records count: honest records linked to an attesting
                         neighbour, plus the terminating carrier's record.
Closed form (positional, random attacker): exact, see theory_positional_random (accounts for the
  rewriter being drawn uniformly from the corrupt carriers).
Outputs: results/sweep.csv, results/summary.md, results/*.png
"""
import argparse, csv, json, os, time
import numpy as np

def simulate(H, p, c, n, rng):
    corrupt = rng.random((n, H)) < c
    honest = (~corrupt) & (rng.random((n, H)) < p)
    feasible = corrupt.any(axis=1)
    # admissible records for the linked rule
    left = np.zeros_like(honest); left[:, 1:] = honest[:, :-1]
    right = np.zeros_like(honest); right[:, :-1] = honest[:, 1:]
    adm = honest & (left | right); adm[:, -1] |= honest[:, -1]
    out = {}
    for name, ev in (("positional", honest), ("linked", adm)):
        before = np.zeros_like(ev); before[:, 1:] = np.cumsum(ev, axis=1)[:, :-1] > 0
        after = np.zeros_like(ev); after[:, :-1] = (np.cumsum(ev[:, ::-1], axis=1)[:, ::-1])[:, 1:] > 0
        catchable = before & after                                  # caught if the rewrite happens here
        # random attacker: uniform corrupt position
        score = np.where(corrupt, rng.random((n, H)), -1.0)
        k = score.argmax(axis=1)
        rand_caught = catchable[np.arange(n), k]
        # targeted attacker: caught only if every corrupt position is catchable
        targ_caught = np.all(~corrupt | catchable, axis=1)
        out[name] = (rand_caught[feasible].mean() if feasible.any() else np.nan,
                     targ_caught[feasible].mean() if feasible.any() else np.nan)
    return out, feasible.mean()

def theory_positional_random(H, p, c):
    """Exact P(caught | attack feasible) for the positional rule and a random attacker.
    The rewriter is drawn uniformly from the corrupt carriers, so each corrupt carrier is chosen with weight
    1/(1 + N), where N counts the OTHER corrupt carriers. Using 1/(1+N) = integral_0^1 t^N dt and independence:
      P = c / (1 - (1-c)^H) * sum_k integral_0^1 B(k-1, t) B(H-k, t) dt,
      B(m, t) = (1 - c + c t)^m - (s + c t)^m,   s = (1-c)(1-p)
    (B is E[t^N_block * 1{the block contains an honest attesting carrier}]). Gauss-Legendre is exact here."""
    if c <= 0: return float("nan")
    s = (1 - c) * (1 - p)
    x, w = np.polynomial.legendre.leggauss(64); t = (x + 1) / 2; w = w / 2
    B = lambda m: (1 - c + c * t) ** m - (s + c * t) ** m
    tot = sum(float(np.sum(w * B(k - 1) * B(H - k))) for k in range(1, H + 1))
    return c * tot / (1 - (1 - c) ** H)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200_000); ap.add_argument("--seed", type=int, default=20260909)
    a = ap.parse_args()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"); os.makedirs(out, exist_ok=True)
    Hs, ps, cs = [3, 5, 8, 12, 16], [round(x, 2) for x in np.linspace(0, 1, 11)], [0.05, 0.1, 0.25, 0.5]
    rows, t0 = [], time.time()
    for H in Hs:
        for c in cs:
            for p in ps:
                rng = np.random.default_rng([a.seed, H, int(c * 1000), int(p * 1000)])
                res, feas = simulate(H, p, c, a.trials, rng)
                th = theory_positional_random(H, p, c)
                rows.append(dict(H=H, c=c, p=p, attack_feasible=round(feas, 5),
                                 positional_random=round(res["positional"][0], 5), positional_random_theory=round(th, 5),
                                 positional_targeted=round(res["positional"][1], 5),
                                 linked_random=round(res["linked"][0], 5), linked_targeted=round(res["linked"][1], 5),
                                 positional_launder=0.0))
    with open(os.path.join(out, "sweep.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    err = max(abs(r["positional_random"] - r["positional_random_theory"]) for r in rows)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, 3, figsize=(13, 7.5), sharey=True)
    for ax, (H, c) in zip(axs.flat, [(5, .1), (5, .25), (5, .5), (12, .1), (12, .25), (12, .5)]):
        rs = [r for r in rows if r["H"] == H and r["c"] == c]
        P = [r["p"] for r in rs]
        ax.plot(P, [r["positional_random_theory"] for r in rs], "k--", lw=1, label="positional, random (theory)")
        ax.plot(P, [r["positional_random"] for r in rs], "o", color="#3f7bc4", ms=4, label="positional (BVI-0), random")
        ax.plot(P, [r["positional_targeted"] for r in rs], "s-", color="#7a1f2b", ms=3.5, lw=1.2, label="positional (BVI-0), targeted")
        ax.plot(P, [r["linked_random"] for r in rs], "^-", color="#2e7d5b", ms=3.5, lw=1.2, label="linked (BVI-R), random")
        ax.plot(P, [r["linked_targeted"] for r in rs], "v-", color="#a8750f", ms=3.5, lw=1.2, label="linked (BVI-R), targeted")
        ax.plot(P, [0] * len(P), ":", color="#c23b4b", lw=1.5, label="BVI-0 with off-path launderer")
        ax.set_title(f"H = {H} hops, corruption c = {c}", fontsize=9); ax.grid(alpha=.25)
    for ax in axs[1]: ax.set_xlabel("per-carrier participation p")
    for ax in axs[:, 0]: ax.set_ylabel("rewrites caught by route layer")
    axs[0, 0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Route-layer detection without number binding (Monte Carlo, %d trials per point)" % a.trials, fontsize=10)
    plt.tight_layout(); plt.savefig(os.path.join(out, "collusion_sweep.png"), dpi=170); plt.close()

    L = ["# Item 4: collusion and participation sweep", "",
         f"Trials per cell: {a.trials:,}; seed {a.seed}. Max |Monte Carlo - closed form| (positional, random): {err:.4f}.", "",
         "Detection is over feasible attacks (at least one corrupt carrier). Route layer only: with number binding (BVI-R, BVI-B), the identity layer catches every calling-number rewrite regardless of these rates.", "",
         "| H | c | p | P(attack feasible) | BVI-0 random | theory | BVI-0 targeted | BVI-R random | BVI-R targeted | BVI-0 + launderer |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["H"] in (5, 12) and r["c"] in (0.1, 0.25) and r["p"] in (0.25, 0.5, 0.75, 1.0):
            L.append(f"| {r['H']} | {r['c']} | {r['p']} | {r['attack_feasible']:.3f} | {r['positional_random']:.3f} | {r['positional_random_theory']:.3f} | {r['positional_targeted']:.3f} | {r['linked_random']:.3f} | {r['linked_targeted']:.3f} | 0 |")
    open(os.path.join(out, "summary.md"), "w").write("\n".join(L) + "\n")
    json.dump(dict(trials=a.trials, seed=a.seed, Hs=Hs, ps=ps, cs=cs, max_abs_err_theory=err, seconds=round(time.time() - t0, 1)),
              open(os.path.join(out, "run_info.json"), "w"), indent=2)
    print(f"cells {len(rows)}, max |MC - theory| = {err:.4f}, {time.time() - t0:.0f} s")

if __name__ == "__main__":
    main()
