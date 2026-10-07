"""
translation_sim.py — legitimate caller-ID translation and the route check (item 3).

Setting
  H carriers on the path. Each carrier independently participates with prob p
  and legitimately translates the caller ID (border controller) with prob t.
  Carrier j receives ID r_j and sends s_j; s_j != r_j iff j translates.

Two route-check schemes
  undeclared (current paper rule): a participating carrier attests the ID it
      RECEIVED. All attested IDs must agree. Any translation between the first
      and last participant makes them disagree -> "fail".
  declared (proposed): a participating carrier attests (received, sent).
      For consecutive participants i < k the verifier requires sent_i == received_k.
      A participating translator declares its change, so it never causes a fail.
      Only a NON-participating translator between two participants does.
  Both: fewer than 2 participants -> "unknown" (does not block).

Outputs, for HONEST calls (no attack):
  false-flag rate  = P(route check says "fail")       exact + Monte Carlo
  unknown rate     = P(fewer than 2 participants)
For ATTACKED calls (in-path rewrite at a uniform boundary by a non-participant,
colluders counted as non-participants): flag rate under the declared scheme,
compared with the translation-free closed form from the collusion model.

Exact values come from enumerating all 2^H participation patterns (H <= 12),
so no closed-form approximation is involved. Monte Carlo uses seed 20260909.
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
P_LIST = [0.25, 0.50, 0.75, 0.90, 1.00]
T_LIST = [0.05, 0.10, 0.25, 0.50]   # PLACEHOLDER sweep: per-carrier translation probability
F_LIST = [0.00, 0.25, 0.50]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results", "item3")
os.makedirs(OUT, exist_ok=True)


# ── exact enumeration ───────────────────────────────────────────────────────
def exact_honest(H, p, t, scheme):
    fail = unknown = 0.0
    for mask in range(1 << H):
        part = [j for j in range(H) if (mask >> j) & 1]
        w = p ** len(part) * (1 - p) ** (H - len(part))
        if len(part) < 2:
            unknown += w
            continue
        a, b = part[0], part[-1]
        if scheme == "declared":
            k = sum(1 for j in range(a + 1, b) if not (mask >> j) & 1)
        else:  # undeclared: any translation at carriers a .. b-1 changes a later attested ID
            k = b - a
        fail += w * (1 - (1 - t) ** k)
    return fail, unknown


def closed_attack_no_translation(H, q):
    b = np.arange(1, H)
    return float(np.mean((1 - (1 - q) ** b) * (1 - (1 - q) ** (H - b))))


# ── Monte Carlo ─────────────────────────────────────────────────────────────
def mc_honest(rng, H, p, t, n):
    part = rng.random((n, H)) < p
    trans = rng.random((n, H)) < t
    idx = np.arange(H)
    cnt = part.sum(axis=1)
    a = np.argmax(part, axis=1)
    b = H - 1 - np.argmax(part[:, ::-1], axis=1)
    between = (idx > a[:, None]) & (idx < b[:, None])
    span = (idx >= a[:, None]) & (idx < b[:, None])
    enough = cnt >= 2
    fail_decl = enough & np.any(trans & ~part & between, axis=1)
    fail_undecl = enough & np.any(trans & span, axis=1)
    return fail_decl.mean(), fail_undecl.mean(), (~enough).mean()


def mc_attack_declared(rng, H, p, f, t, n):
    part = rng.random((n, H)) < p
    coll = rng.random((n, H)) < f
    honest = part & ~coll                      # colluders behave as non-participants
    trans = rng.random((n, H)) < t
    bnd = rng.integers(1, H, size=n)           # rewrite between carrier bnd-1 and bnd
    idx = np.arange(H)
    up = np.any(honest & (idx < bnd[:, None]), axis=1)
    down = np.any(honest & (idx >= bnd[:, None]), axis=1)
    caught_rewrite = up & down
    cnt = honest.sum(axis=1)
    a = np.argmax(honest, axis=1)
    b = H - 1 - np.argmax(honest[:, ::-1], axis=1)
    between = (idx > a[:, None]) & (idx < b[:, None])
    trans_flag = (cnt >= 2) & np.any(trans & ~honest & between, axis=1)
    return (caught_rewrite | trans_flag).mean(), caught_rewrite.mean()


def main():
    rng = np.random.default_rng(SEED)
    honest_rows, attack_rows = [], []
    max_diff = 0.0
    for H in H_LIST:
        for p in P_LIST:
            for t in T_LIST:
                ed, unk = exact_honest(H, p, t, "declared")
                eu, _ = exact_honest(H, p, t, "undeclared")
                md, mu, munk = mc_honest(rng, H, p, t, TRIALS)
                max_diff = max(max_diff, abs(ed - md), abs(eu - mu), abs(unk - munk))
                honest_rows.append([H, p, t, ed, md, eu, mu, unk])
    for H in H_LIST:
        for p in [0.5, 0.75, 1.0]:
            for f in F_LIST:
                for t in [0.0, 0.10, 0.25]:
                    flag, rewrite_only = mc_attack_declared(rng, H, p, f, t, TRIALS)
                    closed = closed_attack_no_translation(H, p * (1 - f))
                    attack_rows.append([H, p, f, t, flag, rewrite_only, closed])

    with open(os.path.join(OUT, "translation_false_flag.csv"), "w") as fh:
        fh.write("H,p,t,declared_exact,declared_mc,undeclared_exact,undeclared_mc,unknown_exact\n")
        for r in honest_rows:
            fh.write(f"{r[0]},{r[1]:.2f},{r[2]:.2f},{r[3]:.6f},{r[4]:.6f},{r[5]:.6f},{r[6]:.6f},{r[7]:.6f}\n")
    with open(os.path.join(OUT, "translation_attack_detection.csv"), "w") as fh:
        fh.write("H,p,f,t,flag_rate_declared,rewrite_caught,closed_form_no_translation\n")
        for r in attack_rows:
            fh.write(f"{r[0]},{r[1]:.2f},{r[2]:.2f},{r[3]:.2f},{r[4]:.6f},{r[5]:.6f},{r[6]:.6f}\n")

    manifest = {
        "script": "item3_translation/translation_sim.py",
        "seed": SEED, "trials_per_cell": TRIALS,
        "grid": {"H": H_LIST, "p": P_LIST, "t": T_LIST, "f_attack": F_LIST},
        "t_note": "t (per-carrier legitimate translation probability) is a swept PLACEHOLDER; needs a sourced value.",
        "max_absdiff_exact_vs_mc": max_diff,
        "numpy_version": np.__version__, "python_version": platform.python_version(),
    }
    with open(os.path.join(OUT, "translation_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    # figure: honest false-flag vs participation, declared vs undeclared
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, t in zip(axes, [0.10, 0.25]):
        for H, c in zip(H_LIST, ["tab:blue", "tab:orange", "tab:green", "tab:red"]):
            rows = [r for r in honest_rows if r[0] == H and abs(r[2] - t) < 1e-9]
            ps = [r[1] for r in rows]
            ax.plot(ps, [r[5] for r in rows], "--", color=c, label=f"H={H} undeclared")
            ax.plot(ps, [r[3] for r in rows], "-", color=c, label=f"H={H} declared")
            ax.scatter(ps, [r[4] for r in rows], s=12, color=c)
        ax.set_title(f"Honest calls wrongly flagged, t = {t}")
        ax.set_xlabel("participation p")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("false-flag rate (dots = simulation)")
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "translation_false_flag.png"), dpi=150)

    print(f"seed={SEED} trials/cell={TRIALS}  max |exact - MC| = {max_diff:.4f}\n")
    print("Honest-call false-flag rate, t = 0.10 (declared | undeclared):")
    print("   H |" + "".join(f"      p={p:.2f}     " for p in P_LIST))
    for H in H_LIST:
        cells = [r for r in honest_rows if r[0] == H and abs(r[2] - 0.10) < 1e-9]
        print(f"  {H:2d} |" + "".join(f"  {r[3]:.3f} | {r[5]:.3f}  " for r in cells))
    print("\nAttack flag rate (declared scheme) vs translation-free closed form, H=5, p=0.75:")
    for r in attack_rows:
        if r[0] == 5 and r[1] == 0.75:
            print(f"  f={r[2]:.2f} t={r[3]:.2f}: flagged {r[4]:.3f}  rewrite caught {r[5]:.3f}  closed form {r[6]:.3f}")
    print("\nwrote translation_false_flag.csv, translation_attack_detection.csv, translation_manifest.json, translation_false_flag.png")


if __name__ == "__main__":
    main()
